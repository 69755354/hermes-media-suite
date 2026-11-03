#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""两个号「播放 + 消耗」标准数据表（扁平：一作品一行）+ 费用表。

源：workflow/projects/attribution/data/douyin_natural/works_ledger.csv（播放/互动/结算）
    workflow/projects/huolong-guide/ledger/消耗台账.csv（生成消耗，0.54 元/秒）
用法：python3 two_acct_daily_report.py [--date YYYYMMDD]
输出：out/我方作品数据_<日期>.xlsx、out/费用表_<日期>.xlsx
"""
import argparse, csv, datetime, pathlib
from collections import Counter
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

PROJ = pathlib.Path("/home/ubuntu/workflow/projects/attribution")
LEDGER = PROJ / "data/douyin_natural/works_ledger.csv"
FEE = pathlib.Path("/home/ubuntu/workflow/projects/huolong-guide/ledger/消耗台账.csv")
OUT = PROJ / "out"
COLS = ["号", "作品名称", "发布时间", "播放量", "完播率", "5s完播率", "2s跳出率", "平均播放时长",
        "点赞量", "分享量", "评论量", "收藏量", "主页访问量", "粉丝增量",
        "消耗_元", "有效播放量", "已结算收益_元", "更新时间"]
W = [8, 46, 18, 10, 10, 11, 11, 13, 9, 9, 9, 9, 11, 10, 10, 12, 13, 17]


def num(v):
    if v is None or str(v).strip() in ("", "-", "--"):
        return ""
    try:
        f = float(v)
        return int(f) if f == int(f) else round(f, 6)
    except Exception:
        return v


def sty(ws, widths):
    for c in ws[1]:
        c.font = Font(bold=True)
        c.alignment = Alignment(horizontal="center")
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y%m%d"))
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    rows = [r for r in csv.DictReader(open(LEDGER, encoding="utf-8-sig")) if (r.get("作品名称") or "").strip()]
    rows.sort(key=lambda r: (r.get("号", ""), r.get("发布时间", "")))
    wb = Workbook(); ws = wb.active; ws.title = "我方作品数据"; ws.append(COLS)
    for r in rows:
        ws.append([num(r.get(c)) if c not in ("号", "作品名称", "发布时间", "更新时间") else (r.get(c) or "") for c in COLS])
    sty(ws, W)
    p1 = OUT / ("我方作品数据_" + a.date + ".xlsx"); wb.save(p1)

    fee = list(csv.reader(open(FEE, encoding="utf-8-sig")))
    head, body = fee[0], [r for r in fee[1:] if any(x.strip() for x in r)]
    cols = ["日期", "片名", "项目", "生成秒数", "段数", "单价(元/秒)", "费用(元)", "备注"]
    idx = [head.index(c) for c in cols if c in head]
    wb2 = Workbook(); ws2 = wb2.active; ws2.title = "费用表"; ws2.append([head[i] for i in idx])
    for r in body:
        ws2.append([r[i] if i < len(r) else "" for i in idx])
    sty(ws2, [17, 30, 22, 11, 8, 12, 11, 60])
    p2 = OUT / ("费用表_" + a.date + ".xlsx"); wb2.save(p2)

    tk = "生成费用(元)"
    tc = 0.0
    for r in body:
        try:
            tc += float(r[head.index(tk)])
        except Exception:
            pass
    print("作品行数=%d 费用行数=%d 生成费用合计=¥%.2f" % (len(rows), len(body), tc))
    print("号分布:", Counter(r.get("号", "?") for r in rows))
    print("OUTPUT:", p1)
    print("OUTPUT:", p2)


if __name__ == "__main__":
    main()
