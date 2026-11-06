"""bot._fetch_client_files: enumerate a customer's files instead of hardcoding names.

collect_and_report used to fetch two fixed Douyin exports named after one
customer's nicknames and a single unsuffixed Xingtu file.  On any other
customer -- or after 1.2.188 split Xingtu per account -- that silently gave
"no data" / star columns of 0.  The helper is loaded from bot.py's source so
the test does not need Feishu credentials; the "client" is a real Python
subprocess running exactly the code the bot would send.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BOT = Path(__file__).resolve().parents[1] / "feishu_publish_bot" / "bot.py"


def _load_helpers():
    tree = ast.parse(BOT.read_text(encoding="utf-8"))
    wanted = {"_ORDINAL_LABELS", "_ordinal_label", "_fetch_client_files"}
    nodes = [n for n in tree.body
             if (isinstance(n, ast.FunctionDef) and n.name in wanted)
             or (isinstance(n, ast.Assign) and any(getattr(t, "id", None) in wanted for t in n.targets))]
    ns = {"json": json}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(BOT), "exec"), ns)
    return ns


def _client(code, timeout=100):
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          encoding="utf-8", timeout=timeout)
    return proc.stdout


class FetchClientFilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ns = _load_helpers()

    def test_enumerates_every_account_file_for_the_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "星图数据_20261107_env_1.json").write_text('{"name":"a"}', encoding="utf-8")
            (d / "星图数据_20261107_env_2.json").write_text('{"name":"b"}', encoding="utf-8")
            (d / "星图数据_20261106_env_1.json").write_text('{"name":"old"}', encoding="utf-8")
            files = self.ns["_fetch_client_files"](_client, str(d / "星图数据_20261107*.json"))
        self.assertEqual([n for n, _ in files],
                         ["星图数据_20261107_env_1.json", "星图数据_20261107_env_2.json"])
        self.assertEqual([json.loads(b)["name"] for _, b in files], ["a", "b"])

    def test_no_files_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.ns["_fetch_client_files"](_client, str(Path(tmp) / "*.json")), [])

    def test_binary_and_multi_megabyte_files_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            blob = bytes(range(256)) * 12000  # ~3 MB, every byte value
            (Path(tmp) / "作品列表导出_20261107_号.json").write_bytes(blob)
            files = self.ns["_fetch_client_files"](_client, str(Path(tmp) / "作品列表导出_20261107*.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0][1], blob)

    def test_unreachable_client_gives_empty(self):
        self.assertEqual(self.ns["_fetch_client_files"](lambda code, timeout=0: "", "x*"), [])
        self.assertEqual(self.ns["_fetch_client_files"](lambda code, timeout=0: {"stdout": "FILES:!!"}, "x*"), [])

    def test_labels_are_positional_not_customer_names(self):
        lab = self.ns["_ordinal_label"]
        self.assertEqual([lab(i) for i in range(3)], ["一号", "二号", "三号"])
        self.assertEqual(lab(11), "第12号")

    def test_no_customer_nickname_left_in_report_paths(self):
        src = BOT.read_text(encoding="utf-8")
        start = src.index("def collect_and_report(")
        body = src[start:src.index("\ndef ", start + 10)]
        for nickname in ("\\u8721\\u7b14\\u65b0\\u5c0f\\u6f2b", "\\u6f2b\\u534a\\u62cd", "蜡笔新小漫", "漫半拍"):
            self.assertNotIn(nickname, body)


if __name__ == "__main__":
    unittest.main()
