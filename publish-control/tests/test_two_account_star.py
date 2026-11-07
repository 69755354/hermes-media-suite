"""Regression: every Douyin account must get its own Xingtu numbers.

1.2.188 started collecting Xingtu once per account and writing one file per
account (``星图数据_<YYYYMMDD>_<env_id>.json``).  The readers were left on the
old single-file assumption:

* ``report_two_account.build`` used only ``star_files[-1]`` (one account) and
  globbed the day as ``YYYY-MM-DD`` while the collectors write ``YYYYMMDD``;
* ``build_two_account_table.py`` accepted a single ``--star`` file.

Either way one account's "星图有效播放" stayed 0 -- the bug 1.2.188 set out to
fix.  These tests pin the behaviour end to end on the file contracts.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "client"
sys.path.insert(0, str(CLIENT / "agent"))

from winport import report_two_account  # noqa: E402

TABLE_TOOL = ROOT.parent / "video-team" / "tools" / "build_two_account_table.py"
DAY = "20261107"


def _douyin(name, titles):
    return {"account_name": name,
            "records": [{"作品名称": t, "播放量": 100 + i, "发布时间": "2026-11-07 10:00"}
                        for i, t in enumerate(titles)]}


def _star(items):
    return {"name": "x", "items": [{"item_name": t, "valid_play": vv, "share_amount": share}
                                   for t, vv, share in items]}


class TwoAccountStarReportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.layout = SimpleNamespace(out_xingtu=base / "xingtu",
                                      out_douyin=base / "douyin",
                                      out_reports=base / "reports")
        for p in (self.layout.out_xingtu, self.layout.out_douyin):
            p.mkdir(parents=True)
        # Exactly what the 1.2.188 collectors write for two accounts.
        (self.layout.out_douyin / f"作品列表导出_{DAY}_env_1.json").write_text(
            json.dumps(_douyin("漫半拍", ["A1 第一集", "A2 第二集"]), ensure_ascii=False), encoding="utf-8")
        (self.layout.out_douyin / f"作品列表导出_{DAY}_env_2.json").write_text(
            json.dumps(_douyin("剧场二号", ["B1 第一集"]), ensure_ascii=False), encoding="utf-8")
        (self.layout.out_xingtu / f"星图数据_{DAY}_env_1.json").write_text(
            json.dumps(_star([("A1 第一集", 1000, 3.5), ("A2 第二集", 500, 1.0)]), ensure_ascii=False),
            encoding="utf-8")
        (self.layout.out_xingtu / f"星图数据_{DAY}_env_2.json").write_text(
            json.dumps(_star([("B1 第一集", 777, 2.0)]), ensure_ascii=False), encoding="utf-8")

    def _rows(self, out):
        sys.path.insert(0, str(CLIENT / "agent"))
        from winport.minimal_xlsx import read_xlsx  # noqa: E402
        return read_xlsx(out)

    def test_both_accounts_get_star_numbers(self):
        res = report_two_account.build(self.layout, day=DAY)
        self.assertEqual(res["valid"], 1000 + 500 + 777)
        self.assertAlmostEqual(res["share"], 6.5)

    def test_collector_day_format_without_explicit_day(self):
        # cmd_collect_all passes args.day=None to both collectors and the
        # report; the collectors then write YYYYMMDD.
        res = report_two_account.build(self.layout, day=None, today=DAY)
        self.assertEqual(res["valid"], 2277)

    def test_dashed_day_is_accepted(self):
        res = report_two_account.build(self.layout, day="2026-11-07")
        self.assertEqual(res["valid"], 2277)

    def test_legacy_single_file_still_works(self):
        for p in self.layout.out_xingtu.glob("*.json"):
            p.unlink()
        (self.layout.out_xingtu / f"星图数据_{DAY}.json").write_text(
            json.dumps(_star([("A1 第一集", 9, 0.5)]), ensure_ascii=False), encoding="utf-8")
        res = report_two_account.build(self.layout, day=DAY)
        self.assertEqual(res["valid"], 9)

    def test_same_item_in_two_files_counted_once(self):
        # A rerun on the same day rewrites the same account file; a stale
        # unsuffixed file from 1.2.177 may also sit next to the new ones.
        (self.layout.out_xingtu / f"星图数据_{DAY}.json").write_text(
            json.dumps(_star([("A1 第一集", 1000, 3.5)]), ensure_ascii=False), encoding="utf-8")
        res = report_two_account.build(self.layout, day=DAY)
        self.assertEqual(res["valid"], 2277)


@unittest.skipUnless(TABLE_TOOL.exists(), "video-team table tool not in tree")
class TableToolMultiStarTests(unittest.TestCase):
    def test_table_tool_accepts_one_star_file_per_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            d1, d2 = t / "d1.json", t / "d2.json"
            s1, s2 = t / "s1.json", t / "s2.json"
            d1.write_text(json.dumps(_douyin("漫半拍", ["A1 第一集"]), ensure_ascii=False), encoding="utf-8")
            d2.write_text(json.dumps(_douyin("剧场二号", ["B1 第一集"]), ensure_ascii=False), encoding="utf-8")
            s1.write_text(json.dumps(_star([("A1 第一集", 1000, 3.5)]), ensure_ascii=False), encoding="utf-8")
            s2.write_text(json.dumps(_star([("B1 第一集", 777, 2.0)]), ensure_ascii=False), encoding="utf-8")
            out = t / "t.xlsx"
            proc = subprocess.run([sys.executable, str(TABLE_TOOL), "--douyin", str(d1), str(d2),
                                   "--star", str(s1), str(s2), "--out", str(out)],
                                  capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            summary = json.loads(proc.stdout.strip().splitlines()[-1])
            self.assertEqual(summary.get("valid"), 1777, proc.stdout)


if __name__ == "__main__":
    unittest.main()
