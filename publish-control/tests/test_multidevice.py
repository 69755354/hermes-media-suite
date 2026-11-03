from __future__ import annotations

import importlib.util
import shutil
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MultiDeviceServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="publish-md-"))
        self.db = self.tmp / "control.db"
        import server
        self.server = server
        server.DB = str(self.db)
        server._initialized.clear()
        server.init()

        self.old = _load(
            "old_device_migration",
            ROOT / "scripts/verify_device_binding.py")
        conn = sqlite3.connect(self.db)
        conn.execute("PRAGMA foreign_keys=ON")
        self.old.migrate(conn)
        conn.close()

        self.new = _load(
            "new_device_migration",
            ROOT / "scripts/migrate_multidevice.py")
        conn = sqlite3.connect(self.db)
        conn.execute("PRAGMA foreign_keys=ON")
        self.new.migrate(conn)
        conn.close()

        customer, _, _ = server.upsert_customer({
            "customer_id": "c_multi", "name": "multi",
            "chat_id": "oc_multi", "token": "legacy-customer-token"})
        self.customer = customer

    def tearDown(self):
        self.server._initialized.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add(self, label, machine):
        return self.server.add_device(
            "c_multi", label=label, machine_code=machine)

    def test_two_devices_are_independently_active_and_revocable(self):
        a = self.add("A机", "machine-a")
        b = self.add("B机", "machine-b")
        self.assertNotEqual(a["device_id"], b["device_id"])
        self.assertNotEqual(a["token"], b["token"])
        self.assertEqual(len(self.server.list_devices("c_multi")["devices"]), 2)

        cmd, duplicate = self.server.enqueue_command(
            "c_multi", "status", {"device_id": b["device_id"]},
            device_id=b["device_id"])
        self.assertFalse(duplicate)
        self.assertEqual(cmd["device_id"], b["device_id"])

        self.assertIsNone(self.server.poll_command(
            "c_multi", device_id=a["device_id"],
            binding_epoch=a["binding_epoch"], device_token=a["token"]))
        claimed = self.server.poll_command(
            "c_multi", device_id=b["device_id"],
            binding_epoch=b["binding_epoch"], device_token=b["token"])
        self.assertEqual(claimed["command_id"], cmd["command_id"])

        self.server.isolate_device("c_multi", a["device_id"])
        with self.assertRaises(self.server.DeviceBindingError):
            self.server.poll_command(
                "c_multi", device_id=a["device_id"],
                binding_epoch=a["binding_epoch"], device_token=a["token"])
        self.assertIsNone(self.server.poll_command(
            "c_multi", device_id=b["device_id"],
            binding_epoch=b["binding_epoch"], device_token=b["token"]))
        states = {row["device_id"]: row["status"]
                  for row in self.server.list_devices("c_multi")["devices"]}
        self.assertEqual(states[a["device_id"]], "isolated")
        self.assertEqual(states[b["device_id"]], "active")

    def test_material_cannot_be_claimed_by_two_devices(self):
        a = self.add("A机", "machine-a")
        b = self.add("B机", "machine-b")
        sha = "a" * 64
        self.server.enqueue_command(
            "c_multi", "publish",
            {"device_id": a["device_id"], "material_sha256": sha},
            command_id="p-a", device_id=a["device_id"])
        with self.assertRaises(self.server.MaterialDeviceConflict):
            self.server.enqueue_command(
                "c_multi", "publish",
                {"device_id": b["device_id"], "material_sha256": sha},
                command_id="p-b", device_id=b["device_id"])

        same_device = self.server.enqueue_command(
            "c_multi", "publish",
            {"device_id": a["device_id"], "material_sha256": sha},
            command_id="p-a-2", device_id=a["device_id"])
        self.assertEqual(same_device[0]["device_id"], a["device_id"])

        other = self.server.enqueue_command(
            "c_multi", "publish",
            {"device_id": b["device_id"], "material_sha256": "b" * 64},
            command_id="p-b-2", device_id=b["device_id"])
        self.assertEqual(other[0]["device_id"], b["device_id"])

    def test_isolation_releases_failed_claim_but_not_unknown_claim(self):
        a = self.add("A机", "machine-a")
        b = self.add("B机", "machine-b")
        failed_sha = "1" * 64
        unknown_sha = "2" * 64
        failed_cmd, _ = self.server.enqueue_command(
            "c_multi", "publish",
            {"device_id": a["device_id"], "material_sha256": failed_sha},
            command_id="failed-a", device_id=a["device_id"])
        unknown_cmd, _ = self.server.enqueue_command(
            "c_multi", "publish",
            {"device_id": a["device_id"], "material_sha256": unknown_sha},
            command_id="unknown-a", device_id=a["device_id"])
        self.server.record_result(
            "c_multi", failed_cmd["command_id"], "failed",
            {"error": "test failure"}, device_id=a["device_id"],
            binding_epoch=a["binding_epoch"], device_token=a["token"])
        self.server.poll_command(
            "c_multi", device_id=a["device_id"],
            binding_epoch=a["binding_epoch"], device_token=a["token"])

        self.server.isolate_device("c_multi", a["device_id"])

        taken = self.server.enqueue_command(
            "c_multi", "publish",
            {"device_id": b["device_id"], "material_sha256": failed_sha},
            command_id="failed-b", device_id=b["device_id"])
        self.assertEqual(taken[0]["device_id"], b["device_id"])
        with self.assertRaises(self.server.MaterialDeviceConflict):
            self.server.enqueue_command(
                "c_multi", "publish",
                {"device_id": b["device_id"], "material_sha256": unknown_sha},
                command_id="unknown-b", device_id=b["device_id"])

    def test_nested_plan_piece_sha_cannot_bypass_cross_device_claim(self):
        a = self.add("A机", "machine-a")
        b = self.add("B机", "machine-b")
        sha = "e" * 64
        self.server.enqueue_command(
            "c_multi", "publish",
            {"device_id": a["device_id"],
             "plan_data": {"piece": {"sha256": sha}}},
            command_id="nested-a", device_id=a["device_id"])
        with self.assertRaises(self.server.MaterialDeviceConflict):
            self.server.enqueue_command(
                "c_multi", "publish",
                {"device_id": b["device_id"],
                 "plan": {"piece": {"sha256": sha}}},
                command_id="nested-b", device_id=b["device_id"])
        with self.assertRaises(self.server.MaterialDeviceConflict):
            self.server.enqueue_command(
                "c_multi", "publish",
                {"device_id": b["device_id"],
                 "item": {"plan_data": {"piece": {"sha256": sha}}}},
                command_id="nested-c", device_id=b["device_id"])

    def test_material_hashes_reject_malformed_nested_sha(self):
        with self.assertRaises(self.server.DeviceBindingError):
            self.server._material_hashes(
                {"plan_data": {"piece": {"sha256": "not-a-sha"}}})

    def test_switch_isolates_old_and_leaves_customer_ledger_identity(self):
        a = self.add("旧机", "machine-old")
        b = self.add("新机", "machine-new")
        result = self.server.switch_device(
            "c_multi", a["device_id"], b["device_id"])
        states = {row["device_id"]: row["status"] for row in result["devices"]}
        self.assertEqual(states[a["device_id"]], "isolated")
        self.assertEqual(states[b["device_id"]], "active")
        self.assertEqual(result["active_device_id"], b["device_id"])
        customer = self.server.get_customer("c_multi")
        self.assertEqual(customer["customer_id"], "c_multi")
        self.assertEqual(customer["active_device_id"], b["device_id"])
        self.assertGreater(customer["binding_epoch"], 0)
        with self.assertRaises(self.server.DeviceBindingError):
            self.server.poll_command(
                "c_multi", device_id=a["device_id"],
                binding_epoch=a["binding_epoch"], device_token=a["token"])

        c = self.add("第三台", "machine-third")
        self.server.enqueue_command(
            "c_multi", "status", {"device_id": b["device_id"]},
            command_id="inflight", device_id=b["device_id"])
        with self.assertRaises(self.server.DeviceBindingError):
            self.server.switch_device(
                "c_multi", b["device_id"], c["device_id"])

    def test_staged_device_token_works_before_binding_is_enabled(self):
        a = self.server.add_device(
            "c_multi", label="A机", machine_code="machine-a",
            enforce_binding=False)
        self.assertFalse(self.server.list_devices(
            "c_multi")["device_binding_enabled"])
        conn = self.server.conn()
        try:
            binding = self.server._device_guard(
                conn, "c_multi", a["device_id"], a["binding_epoch"], a["token"])
        finally:
            conn.close()
        self.assertEqual(binding["device_id"], a["device_id"])
        conn = self.server.conn()
        try:
            with self.assertRaises(self.server.DeviceBindingError):
                self.server._device_guard(
                    conn, "c_multi", a["device_id"], a["binding_epoch"],
                    "wrong-token")
        finally:
            conn.close()

        enabled = self.server.enable_device_binding("c_multi")
        self.assertTrue(enabled["device_binding_enabled"])
        conn = self.server.conn()
        try:
            with self.assertRaises(self.server.DeviceBindingError):
                self.server._device_guard(conn, "c_multi")
        finally:
            conn.close()

    def test_staged_targeting_isolates_devices_before_binding(self):
        a = self.server.add_device(
            "c_multi", label="A机", machine_code="machine-a",
            enforce_binding=False)
        b = self.server.add_device(
            "c_multi", label="B机", machine_code="machine-b",
            enforce_binding=False)
        self.assertFalse(self.server.list_devices(
            "c_multi")["device_binding_enabled"])

        cmd, _ = self.server.enqueue_command(
            "c_multi", "status", {"device_id": a["device_id"]},
            command_id="staged-a", device_id=a["device_id"])
        self.assertEqual(cmd["device_id"], a["device_id"])
        self.assertIsNone(self.server.poll_command(
            "c_multi", device_id=b["device_id"],
            binding_epoch=b["binding_epoch"], device_token=b["token"]))
        self.assertIsNone(self.server.poll_command("c_multi"))
        claimed = self.server.poll_command(
            "c_multi", device_id=a["device_id"],
            binding_epoch=a["binding_epoch"], device_token=a["token"])
        self.assertEqual(claimed["command_id"], "staged-a")

        op_id = self.server.enqueue_remote(
            "c_multi", "ping", {}, device_id=a["device_id"])
        self.assertIsNone(self.server.poll_remote(
            "c_multi", device_id=b["device_id"],
            binding_epoch=b["binding_epoch"], device_token=b["token"]))
        remote = self.server.poll_remote(
            "c_multi", device_id=a["device_id"],
            binding_epoch=a["binding_epoch"], device_token=a["token"])
        self.assertEqual(remote["id"], op_id)

        legacy, _ = self.server.enqueue_command(
            "c_multi", "status", {}, command_id="legacy-untargeted")
        self.assertIsNone(legacy["device_id"])
        # Untargeted legacy work remains claimable only by a legacy poll;
        # a device-identified poll must not silently adopt it.
        self.assertIsNone(self.server.poll_command(
            "c_multi", device_id=a["device_id"],
            binding_epoch=a["binding_epoch"], device_token=a["token"]))
        claimed = self.server.poll_command("c_multi")
        self.assertEqual(claimed["command_id"], "legacy-untargeted")

    def test_staged_single_device_can_claim_legacy_untargeted(self):
        a = self.server.add_device(
            "c_multi", label="A机", machine_code="machine-a",
            enforce_binding=False)
        op_id = self.server.enqueue_remote("c_multi", "materials", {})
        remote = self.server.poll_remote(
            "c_multi", device_id=a["device_id"],
            binding_epoch=a["binding_epoch"], device_token=a["token"])
        self.assertEqual(remote["id"], op_id)

        cmd, _ = self.server.enqueue_command(
            "c_multi", "status", {}, command_id="single-untargeted")
        self.assertIsNone(cmd["device_id"])
        claimed = self.server.poll_command(
            "c_multi", device_id=a["device_id"],
            binding_epoch=a["binding_epoch"], device_token=a["token"])
        self.assertEqual(claimed["command_id"], "single-untargeted")

    def test_default_selection_prefers_online_device(self):
        a = self.add("默认但离线", "machine-a")
        b = self.add("在线", "machine-b")
        conn = sqlite3.connect(self.db)
        conn.execute(
            "UPDATE customer_devices SET last_seen=? WHERE device_id=?",
            (time.time() - 600, a["device_id"]))
        conn.execute(
            "UPDATE customer_devices SET last_seen=? WHERE device_id=?",
            (time.time(), b["device_id"]))
        conn.commit()
        conn.close()
        selected = self.server.select_device("c_multi", require_online=True)
        self.assertEqual(selected["device_id"], b["device_id"])

    def test_remote_ops_are_delivered_only_to_target_device(self):
        a = self.add("A机", "machine-a")
        b = self.add("B机", "machine-b")
        op_id = self.server.enqueue_remote(
            "c_multi", "materials", {"schema": "publish-materials/1"},
            device_id=a["device_id"])
        self.assertIsNone(self.server.poll_remote(
            "c_multi", device_id=b["device_id"],
            binding_epoch=b["binding_epoch"], device_token=b["token"]))
        op = self.server.poll_remote(
            "c_multi", device_id=a["device_id"],
            binding_epoch=a["binding_epoch"], device_token=a["token"])
        self.assertEqual(op["id"], op_id)
        self.assertEqual(op["device_id"], a["device_id"])


class UnmigratedSchemaTests(unittest.TestCase):
    def test_device_operations_fail_closed_before_migration(self):
        import server
        tmp = Path(tempfile.mkdtemp(prefix="publish-md-schema-"))
        old_db = server.DB
        try:
            server.DB = str(tmp / "control.db")
            server._initialized.clear()
            server.init()
            server.upsert_customer({
                "customer_id": "c_old", "name": "old",
                "chat_id": "oc_old", "token": "legacy"})
            with self.assertRaises(server.DeviceBindingError) as ctx:
                server.add_device("c_old", label="A", machine_code="m-a")
            self.assertIn("migration required", str(ctx.exception))
            with self.assertRaises(server.DeviceBindingError):
                server.list_devices("c_old")
        finally:
            server.DB = old_db
            server._initialized.clear()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
