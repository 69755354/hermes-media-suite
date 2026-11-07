"""scripts/recycle_client_ledger.py must never recycle a reservation that a
publish may still be using.

While a publish is in fill, its ledger entry is RESERVED -- indistinguishable
from a zombie left by a crash.  Recycling it there would let the same material
be published twice.  Guards under test: in-flight commands block --apply, young
reservations are left alone, and the client re-checks state and age itself.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "client"
SCRIPT = ROOT / "scripts" / "recycle_client_ledger.py"
sys.path.insert(0, str(CLIENT / "agent"))


def _load():
    spec = importlib.util.spec_from_file_location("recycle_client_ledger", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ts(minutes_ago):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%S%z")


ACCOUNT = "env_1:douyin"


def _entries():
    return {
        "old": {"state": "RESERVED", "reservation_schema": 2, "reserved_at": _ts(120), "account_id": ACCOUNT},
        "young": {"state": "RESERVED", "reservation_schema": 2, "reserved_at": _ts(5), "account_id": ACCOUNT},
        "clicked": {"state": "SUBMIT_INTENT", "reservation_schema": 2, "reserved_at": _ts(120), "account_id": ACCOUNT},
        "legacy": {"state": "RESERVED", "reservation_schema": 1, "reserved_at": _ts(120), "account_id": ACCOUNT},
        "other": {"state": "RESERVED", "reservation_schema": 2, "reserved_at": _ts(120), "account_id": "env_2:douyin"},
        "done": {"state": "SUBMIT_INTENT", "publish_confirmed": True, "reserved_at": _ts(120), "account_id": ACCOUNT},
    }


class ClassifyTests(unittest.TestCase):
    def test_only_old_schema2_reserved_is_recyclable(self):
        mod = _load()
        rec, manual, young = mod.classify(_entries(), ACCOUNT, min_age_min=30)
        self.assertEqual([k for k, _, _ in rec], ["old"])
        self.assertEqual(sorted(k for k, _, _ in manual), ["clicked", "legacy"])
        self.assertEqual([k for k, _, _ in young], ["young"])

    def test_unparseable_time_is_never_recyclable(self):
        mod = _load()
        rec, _, young = mod.classify({"x": {"state": "RESERVED", "reservation_schema": 2,
                                            "reserved_at": "garbage", "account_id": ACCOUNT}}, ACCOUNT)
        self.assertEqual(rec, [])
        self.assertEqual(len(young), 1)

    def test_no_hardcoded_windows_user(self):
        self.assertNotIn("Users\\huang", SCRIPT.read_text(encoding="utf-8"))


class InflightTests(unittest.TestCase):
    def _db(self, rows_cmd=(), rows_ops=()):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        con = sqlite3.connect(tmp.name)
        con.execute("CREATE TABLE commands(id TEXT, customer_id TEXT, kind TEXT, status TEXT)")
        con.execute("CREATE TABLE remote_ops(id TEXT, customer_id TEXT, op TEXT, status TEXT)")
        con.executemany("INSERT INTO commands VALUES(?,?,?,?)", rows_cmd)
        con.executemany("INSERT INTO remote_ops VALUES(?,?,?,?)", rows_ops)
        con.commit()
        con.close()
        return tmp.name

    def test_running_publish_and_exec_are_inflight(self):
        mod = _load()
        db = self._db([("c1", "cust", "publish", "running"), ("c2", "cust", "publish", "done"),
                       ("c3", "other", "publish", "running")],
                      [("o1", "cust", "exec", "running"), ("o2", "cust", "read", "running"),
                       ("o3", "cust", "exec", "done")])
        busy = mod.inflight(db, "cust")
        self.assertEqual(sorted(r[1] for r in busy), ["c1", "o1"])

    def test_idle_customer(self):
        mod = _load()
        self.assertEqual(mod.inflight(self._db([("c1", "cust", "publish", "done")]), "cust"), [])


class ApplyRefusesWhileInflightTests(unittest.TestCase):
    def test_apply_writes_nothing_when_a_publish_is_running(self):
        mod = _load()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "control.db"
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE commands(id TEXT, customer_id TEXT, kind TEXT, status TEXT)")
            con.execute("CREATE TABLE remote_ops(id TEXT, customer_id TEXT, op TEXT, status TEXT)")
            con.execute("INSERT INTO commands VALUES('c1','cust','publish','running')")
            con.commit()
            con.close()
            sent = []
            ledger = base64.b64encode(json.dumps({"entries": _entries()}).encode()).decode()

            def enqueue(customer, op, args, device=""):
                sent.append(op)
                return op

            fake = types.SimpleNamespace(DB=str(db), enqueue=enqueue,
                                         wait=lambda op_id, timeout=90: ("done", {"ok": True, "base64": ledger}))
            sys.modules["remote_pc"] = fake
            self.addCleanup(sys.modules.pop, "remote_pc", None)
            rc = mod.main(["--customer", "cust", "--apply"])
        self.assertEqual(rc, 4)
        self.assertEqual(sent, ["read"])  # no write, no exec


class RemoteScriptTests(unittest.TestCase):
    """Run the exact script the operator uploads, against the real Stage2Ledger."""

    def test_client_side_recheck(self):
        mod = _load()
        from winport.stage2_ledger import Stage2Ledger
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "customers" / "cust" / "run"
            run.mkdir(parents=True)
            led = Stage2Ledger(run / "stage2-ledger.json")
            for k in ("old", "raced", "clicked"):
                led.reserve(k, account_id=ACCOUNT)
            led.mark_submit_intent("clicked") if hasattr(led, "mark_submit_intent") else None
            data = json.loads((run / "stage2-ledger.json").read_text(encoding="utf-8"))
            data["entries"]["old"]["reserved_at"] = _ts(120)
            data["entries"]["raced"]["reserved_at"] = _ts(1)  # a publish just took it
            (run / "stage2-ledger.json").write_text(json.dumps(data), encoding="utf-8")
            (run / mod.KEYS_FILENAME).write_text(json.dumps({"keys": ["old", "raced", "clicked"],
                                                             "min_age_min": 30}), encoding="utf-8")
            (run / "recycle_ledger.py").write_text(mod.REMOTE_SCRIPT, encoding="utf-8")
            proc = subprocess.run([sys.executable, str(run / "recycle_ledger.py")], cwd=str(CLIENT),
                                  capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = {r["key"]: r for r in json.loads(proc.stdout.strip().splitlines()[-1])["results"]}
            left = json.loads((run / "stage2-ledger.json").read_text(encoding="utf-8"))["entries"]
        self.assertTrue(out["old"]["recycled"])
        self.assertFalse(out["raced"]["recycled"])
        self.assertFalse(out["clicked"]["recycled"])
        self.assertNotIn("old", left)
        self.assertIn("raced", left)
        self.assertIn("clicked", left)


if __name__ == "__main__":
    unittest.main()
