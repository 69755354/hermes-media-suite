"""Multiple Douyin accounts on one PC: the bot must ask which one, not guess.

Guessing is what produced "发布总是发到 2 号账号": the client fell back to the
first enabled channel silently.  These tests pin the picker's parsing and the
dialog state machine that stops the batch until the customer answers.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "feishu_publish_bot"


def _load_bot():
    if str(BOT_DIR) not in sys.path:
        sys.path.insert(0, str(BOT_DIR))
    spec = importlib.util.spec_from_file_location("picker_bot", BOT_DIR / "bot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ACCOUNTS = [
    {"env_id": "env_1", "nickname": "蜡笔新小漫", "account_id": "env_1:douyin",
     "enabled": True},
    {"env_id": "env_2", "nickname": "漫半拍", "account_id": "env_2:douyin",
     "enabled": True},
]


class AccountPickerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bot = _load_bot()

    def test_number_picks_position(self):
        self.assertEqual(self.bot._pick_account("1", ACCOUNTS)["env_id"], "env_1")
        self.assertEqual(self.bot._pick_account("2", ACCOUNTS)["env_id"], "env_2")
        self.assertEqual(self.bot._pick_account("第2个", ACCOUNTS)["env_id"], "env_2")
        self.assertEqual(self.bot._pick_account("2号", ACCOUNTS)["env_id"], "env_2")

    def test_nickname_picks_account(self):
        self.assertEqual(self.bot._pick_account("漫半拍", ACCOUNTS)["env_id"], "env_2")
        self.assertEqual(self.bot._pick_account("发蜡笔新小漫", ACCOUNTS)["env_id"], "env_1")

    def test_out_of_range_and_junk_return_none(self):
        self.assertIsNone(self.bot._pick_account("3", ACCOUNTS))
        self.assertIsNone(self.bot._pick_account("0", ACCOUNTS))
        self.assertIsNone(self.bot._pick_account("随便", ACCOUNTS))
        self.assertIsNone(self.bot._pick_account("", ACCOUNTS))


class AccountDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bot = _load_bot()

    def setUp(self):
        self.saved = []
        self.replies = []
        bot = self.bot
        self._orig = (bot._dialog_save, bot._dialog_reply)
        bot._dialog_save = lambda d: self.saved.append(dict(d))
        bot._dialog_reply = lambda d, text: (self.replies.append(text), text)[1]

    def tearDown(self):
        self.bot._dialog_save, self.bot._dialog_reply = self._orig

    def test_two_accounts_blocks_and_asks(self):
        d = {"accounts": list(ACCOUNTS), "status": "awaiting_topics"}
        self.bot._mt_prepare_draft(d)
        self.assertEqual(d["status"], "awaiting_account")
        self.assertEqual(len(d["pending_accounts"]), 2)
        self.assertTrue(any("发哪个" in r for r in self.replies))
        self.assertFalse(d.get("account_env"))

    def test_single_account_does_not_ask(self):
        d = {"accounts": [ACCOUNTS[0]], "status": "awaiting_topics"}
        self.bot._mt_prepare_draft(d)
        self.assertNotEqual(d["status"], "awaiting_account")

    def test_chosen_account_is_not_asked_again(self):
        d = {"accounts": list(ACCOUNTS), "status": "awaiting_topics",
             "account_env": "env_2"}
        self.bot._mt_prepare_draft(d)
        self.assertNotEqual(d["status"], "awaiting_account")


if __name__ == "__main__":
    unittest.main()
