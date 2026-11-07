"""The two client-side snippets must resolve the worker root, not %LOCALAPPDATA%.

INBOX_SCAN and PLAN_MAKER run on the customer PC.  Both compose the data root
as ``%LOCALAPPDATA%\\HuolongAgent\\publish-worker``; an ``or``/``+`` precedence
slip turns that into bare ``%LOCALAPPDATA%``, so the snippet globs the wrong
tree and every customer reports "no materials".  These tests execute the real
snippet lines with a fake LOCALAPPDATA and assert the resolved root.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

PUBLISH = Path(__file__).resolve().parents[1]
BOT = PUBLISH / "feishu_publish_bot" / "bot.py"


def _snippets() -> dict:
    text = BOT.read_text(encoding="utf-8")
    out = {}
    # INBOX_SCAN / PLAN_MAKER are module-level r-strings of client-side code.
    for name in ("INBOX_SCAN", "PLAN_MAKER"):
        start = text.index(name + " = r")
        head = text.index('"""', start) + 3
        tail = text.index('"""', head)
        out[name] = text[head:tail]
    return out


def _resolve(snippet: str, localappdata: str, bt_base: str | None = None) -> str:
    lines = [ln for ln in snippet.splitlines() if ln.startswith("base=")]
    code = "import os, glob, json\n" + "\n".join(lines) + "\nprint(base)"
    env = dict(os.environ, LOCALAPPDATA=localappdata)
    env.pop("BT_WORKER_BASE", None)
    if bt_base:
        env["BT_WORKER_BASE"] = bt_base
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, env=env, timeout=30)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return proc.stdout.strip()


class WorkerBasePathTests(unittest.TestCase):
    def setUp(self):
        self.snips = _snippets()

    def test_inbox_scan_resolves_worker_root(self):
        got = _resolve(self.snips["INBOX_SCAN"], r"C:\Users\example\AppData\Local")
        self.assertEqual(got, r"C:\Users\example\AppData\Local\HuolongAgent\publish-worker")

    def test_plan_maker_resolves_worker_root(self):
        got = _resolve(self.snips["PLAN_MAKER"], r"C:\Users\example\AppData\Local")
        self.assertEqual(got, r"C:\Users\example\AppData\Local\HuolongAgent\publish-worker")

    def test_bt_worker_base_still_wins(self):
        for name in ("INBOX_SCAN", "PLAN_MAKER"):
            with self.subTest(snippet=name):
                got = _resolve(self.snips[name], r"C:\Users\example\AppData\Local",
                               bt_base=r"D:\data\worker")
                self.assertEqual(got, r"D:\data\worker")

    def test_falls_back_to_home_when_localappdata_missing(self):
        code_lines = [ln for ln in self.snips["INBOX_SCAN"].splitlines()
                      if ln.startswith("base=")]
        code = "import os, glob, json\n" + "\n".join(code_lines) + "\nprint(base)"
        env = {k: v for k, v in os.environ.items() if k not in ("LOCALAPPDATA", "BT_WORKER_BASE")}
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                              text=True, env=env, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(proc.stdout.strip().endswith("HuolongAgent\\publish-worker"))


if __name__ == "__main__":
    unittest.main()
