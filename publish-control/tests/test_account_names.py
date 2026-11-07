"""account_names cache: nickname per environment, nothing else."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "client" / "agent"))
from winport import account_names  # noqa: E402


class AccountNamesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.layout = SimpleNamespace(run=Path(tmp.name) / "run")

    def test_roundtrip_and_unchanged(self):
        self.assertTrue(account_names.record(self.layout, "env_1", "漫半拍"))
        self.assertFalse(account_names.record(self.layout, "env_1", "漫半拍"))
        self.assertTrue(account_names.record(self.layout, "env_1", "新昵称"))
        self.assertEqual(account_names.load(self.layout)["env_1"]["nickname"], "新昵称")

    def test_only_nickname_and_time_are_stored(self):
        account_names.record(self.layout, "env_2", "x" * 50)
        entry = account_names.load(self.layout)["env_2"]
        self.assertEqual(set(entry), {"nickname", "updated"})
        self.assertEqual(len(entry["nickname"]), 24)

    def test_blank_input_and_corrupt_file(self):
        self.assertFalse(account_names.record(self.layout, "", "a"))
        self.assertFalse(account_names.record(self.layout, "env_1", "  "))
        (self.layout.run).mkdir(parents=True, exist_ok=True)
        (self.layout.run / account_names.FILENAME).write_text("{not json", encoding="utf-8")
        self.assertEqual(account_names.load(self.layout), {})
        self.assertTrue(account_names.record(self.layout, "env_1", "恢复"))
        self.assertEqual(json.loads((self.layout.run / account_names.FILENAME).read_text(encoding="utf-8"))
                         ["env_1"]["nickname"], "恢复")


if __name__ == "__main__":
    unittest.main()
