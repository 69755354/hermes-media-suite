"""Regression: Xingtu data must be collected once per logged-in account.

The 1.2.188 bug: collect ran on the first environment only, so account 2's
Xingtu columns were always zero in the boss table.  These tests pin the shape
of that loop: one call per enabled environment, each with its own debug port
and its own output file suffix, and one failing account must not wipe the rest.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

CLIENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLIENT))

from agent.winport import cli  # noqa: E402
from agent.winport.collect_xingtu import write_outputs  # noqa: E402


class _FakeLayout:
    def __init__(self, tmp):
        self.out_xingtu = Path(tmp) / "out" / "xingtu"
        self.logs = Path(tmp) / "logs"


def _args(**over):
    base = dict(day="20261107", report_only=False, collect_only=True,
                skip_douyin=True, skip_xingtu=False, program=None, data=None,
                out=None)
    base.update(over)
    return SimpleNamespace(**base)


class MultiAccountXingtuCollectTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="collect-multi-")
        self.calls = []
        self.envs = [
            {"env_id": "env_1", "enabled": True, "debug_port": 9224,
             "platforms": ["douyin"]},
            {"env_id": "env_2", "enabled": True, "debug_port": 9225,
             "platforms": ["douyin"]},
        ]
        self._saved = {}

    def tearDown(self):
        for name, mod in self._saved.items():
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod

    def _install(self, failing=()):
        real = sys.modules.get("agent.winport.collect_xingtu")
        self._saved["agent.winport.collect_xingtu"] = real

        def fake_collect(layout, port=None, day=None, suffix=""):
            self.calls.append({"port": port, "suffix": suffix, "day": day})
            if port in failing:
                raise RuntimeError("account %s offline" % port)
            return {"data": {"name": "acct-%s" % port, "task_count": 2,
                             "item_count": 5, "granularity": "day"},
                    "outputs": {"json": "/x/star%s.json" % suffix}}

        stub = types.ModuleType("agent.winport.collect_xingtu")
        stub.collect_via_cdp = fake_collect
        sys.modules["agent.winport.collect_xingtu"] = stub
        cli._layout = lambda args: _FakeLayout(self.tmp)
        cli._envs = lambda layout: list(self.envs)

    def test_collects_every_enabled_account_with_own_suffix(self):
        self._install()
        rc = cli.cmd_collect_all(_args())
        self.assertEqual(rc, 0)
        self.assertEqual([c["port"] for c in self.calls], [9224, 9225])
        self.assertEqual([c["suffix"] for c in self.calls], ["_env_1", "_env_2"])
        # the collected payload is printed as JSON; the call log is the assertion
        self.assertEqual(len(self.calls), 2)

    def test_one_account_failure_keeps_the_other(self):
        self._install(failing=(9225,))
        rc = cli.cmd_collect_all(_args())
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.calls), 2)

    def test_all_accounts_failing_is_reported_as_failure(self):
        self._install(failing=(9224, 9225))
        rc = cli.cmd_collect_all(_args())
        self.assertNotEqual(rc, 0)


class XingtuOutputSuffixTests(unittest.TestCase):
    def test_two_accounts_write_two_files(self):
        import tempfile
        layout = _FakeLayout(tempfile.mkdtemp(prefix="collect-out-"))
        a = write_outputs(layout, {"account": "a"}, day="20261107", suffix="_env_1")
        b = write_outputs(layout, {"account": "b"}, day="20261107", suffix="_env_2")
        self.assertNotEqual(a["json"], b["json"])
        self.assertTrue(a["json"].endswith("星图数据_20261107_env_1.json"))
        self.assertTrue(b["json"].endswith("星图数据_20261107_env_2.json"))
        self.assertTrue(Path(a["json"]).is_file() and Path(b["json"]).is_file())

    def test_no_suffix_keeps_legacy_name(self):
        import tempfile
        layout = _FakeLayout(tempfile.mkdtemp(prefix="collect-out2-"))
        out = write_outputs(layout, {"account": "a"}, day="20261107")
        self.assertTrue(out["json"].endswith("星图数据_20261107.json"))


if __name__ == "__main__":
    unittest.main()
