"""Multi-account dialog: choosing which Douyin account to publish to.

Loaded from bot.py's source so no Feishu credentials are needed.
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

BOT = Path(__file__).resolve().parents[1] / "feishu_publish_bot" / "bot.py"


def _load():
    tree = ast.parse(BOT.read_text(encoding="utf-8"))
    wanted = {"_CN_DIGITS", "_pick_account", "_selectable_accounts", "_mt_prepare_draft"}
    nodes = [n for n in tree.body
             if (isinstance(n, ast.FunctionDef) and n.name in wanted)
             or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) in wanted for t in n.targets))]
    saved, replies = [], []
    ns = {"re": re,
          "_dialog_save": lambda d: saved.append(dict(d)),
          "_dialog_reply": lambda d, text: replies.append(text) or text}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(BOT), "exec"), ns)
    return ns, saved, replies


def _acc(env, nick, logged_in=True, enabled=True):
    return {"env_id": env, "account_id": env + ":douyin", "nickname": nick,
            "logged_in": logged_in, "enabled": enabled}


class PickAccountTests(unittest.TestCase):
    def setUp(self):
        self.ns, _, _ = _load()
        self.pick = self.ns["_pick_account"]
        self.accs = [_acc("env_1", "小漫"), _acc("env_2", "小漫剧场"), _acc("env_3", "漫半拍")]

    def test_longer_name_wins_over_its_prefix(self):
        self.assertEqual(self.pick("小漫剧场", self.accs)["env_id"], "env_2")
        self.assertEqual(self.pick("发小漫剧场那个", self.accs)["env_id"], "env_2")

    def test_exact_short_name(self):
        self.assertEqual(self.pick("小漫", self.accs)["env_id"], "env_1")

    def test_numbers_arabic_and_chinese(self):
        for text, env in (("2", "env_2"), ("第3个", "env_3"), ("二号", "env_2"),
                          ("第一个", "env_1"), ("1号账号", "env_1"), (" 3 ", "env_3")):
            self.assertEqual(self.pick(text, self.accs)["env_id"], env, text)

    def test_out_of_range_or_unclear_is_none(self):
        for text in ("9", "第十个", "随便", "", "抖音"):
            self.assertIsNone(self.pick(text, self.accs), text)

    def test_ambiguous_same_length_is_none(self):
        accs = [_acc("env_1", "剧场A"), _acc("env_2", "剧场B")]
        self.assertIsNone(self.pick("剧场A和剧场B", accs))


class SelectableAccountsTests(unittest.TestCase):
    def setUp(self):
        self.ns, self.saved, self.replies = _load()

    def _draft(self, accounts, **kw):
        d = {"accounts": accounts, "status": "awaiting_topics", "topics_answered": True,
             "selected": [1], "confirmed_title": "标题", "max_length": 30}
        d.update(kw)
        return d

    def test_empty_profiles_do_not_count(self):
        sel = self.ns["_selectable_accounts"]({"accounts": [_acc("env_1", "A"), _acc("env_2", "B", logged_in=False),
                                                            _acc("env_3", "C", enabled=False)]})
        self.assertEqual([a["env_id"] for a in sel], ["env_1"])

    def test_old_clients_without_logged_in_field(self):
        accs = [{"env_id": "env_1", "nickname": "A"}, {"env_id": "env_2", "nickname": "B"}]
        self.assertEqual(len(self.ns["_selectable_accounts"]({"accounts": accs})), 2)

    def test_one_logged_in_account_is_chosen_without_asking(self):
        d = self._draft([_acc("env_1", "A", logged_in=False), _acc("env_2", "B")])
        try:
            self.ns["_mt_prepare_draft"](d)
        except Exception:
            pass  # later steps need the full bot; the choice is made first
        self.assertEqual(d.get("account_env"), "env_2")
        self.assertNotEqual(d.get("status"), "awaiting_account")

    def test_two_logged_in_accounts_are_asked(self):
        d = self._draft([_acc("env_1", "A"), _acc("env_2", "B")])
        reply = self.ns["_mt_prepare_draft"](d)
        self.assertEqual(d["status"], "awaiting_account")
        self.assertIn("2 个抖音号", reply)


if __name__ == "__main__":
    unittest.main()
