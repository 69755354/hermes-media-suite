#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""两个号「全部作品」标准表（扁平：一作品一行）+ 费用表。

两个号的采集来源不同，别混：
- 一号（漫半拍）  ：Chrome 配置 profiles/douyin        + CDP 9224
- 二号（蜡笔新小漫）：Playwright WebKit profiles/douyin-webkit
两边的产物都需拉回 inbox/，命名：作品列表导出_<YYYYMMDD>_一号.xlsx / _二号.xlsx

用法：python3 two_acct_full_report.py [--date YYYYMMDD]
输出：out/两个号全部作品_<日期>.xlsx、out/费用表_<日期>.xlsx
"""
import argparse, csv, datetime, pathlib
from collections import Counter
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

PROJ = pathlib.Path("/home/ubuntu/workflow/projects/attribution")
INBOX = PROJ / "data/douyin_natural/inbox"
OUT = PROJ / "out"
FEE = pathlib.Path("/home/ubuntu/workflow/projects/huolong-guide/ledger/消耗台账.csv")
COLS = ["号", "作品名称", "发布时间", "审核状态", "体裁", "播放量", "完播率", "5s完播率", "封面点击率",
        "2s跳出率", "平均播放时长", "点赞量", "分享量", "评论量", "收藏量", "主页访问量", "粉丝增量"]
NUM = ["播放量", "完播率", "5s完播率", "封面点击率", "2s跳出率", "平均播放时长",
       "点赞量", "分享量", "评论量", "收藏量", "主页访问量", "粉丝增量"]
W = [10, 44, 18, 11, 12, 10, 10, 11, 11, 11, 13, 9, 9, 9, 9, 11, 10]


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


def read_export(path, label):
    wb = load_workbook(path, read_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    head = [str(x).strip() if x is not None else "" for x in next(it)]
    out = []
    for r in it:
        if not r or not r[0]:
            continue
        d = dict(zip(head, r))
        row = [label] + [num(d.get(c)) if c in NUM else (str(d.get(c)).strip() if d.get(c) is not None else "")
                         for c in COLS[1:]]
        out.append(row)
    wb.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y%m%d"))
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    rows = []
    srcs = [("一号", INBOX / ("作品列表导出_" + a.date + "_一号.xlsx")),
            ("二号", INBOX / ("作品列表导出_" + a.date + "_二号.xlsx"))]
    for label, p in srcs:
        if not p.exists():
            print("缺采集文件:", p.name)
            continue
        got = read_export(p, label)
        rows += got
        pl = [float(x[5]) for x in got if str(x[5]).strip() not in ("",)]
        print("%s %s 行=%d 播放合计=%d 最高=%d" % (label, p.name, len(got), int(sum(pl)), int(max(pl)) if pl else 0))
    # 排序铁律（用户多次强调）：按主指标降序，播放量高的在最上面。禁按号/时间排。
    def _plays(r):
        try:
            return float(r[5])
        except Exception:
            return -1.0

    rows.sort(key=_plays, reverse=True)
    wb = Workbook(); ws = wb.active; ws.title = "两个号全部作品"; ws.append(COLS)
    for r in rows:
        ws.append(r)
    sty(ws, W)
    p1 = OUT / ("两个号全部作品_" + a.date + ".xlsx"); wb.save(p1)

    fee = list(csv.reader(open(FEE, encoding="utf-8-sig")))
    head, body = fee[0], [r for r in fee[1:] if any(x.strip() for x in r)]
    fcols = ["日期", "片名", "项目", "生成秒数", "段数", "单价(元/秒)", "费用(元)", "备注"]
    idx = [head.index(c) for c in fcols if c in head]
    wb2 = Workbook(); ws2 = wb2.active; ws2.title = "费用表"; ws2.append([head[i] for i in idx])
    for r in body:
        ws2.append([r[i] if i < len(r) else "" for i in idx])
    sty(ws2, [17, 30, 22, 11, 8, 12, 11, 60])
    p2 = OUT / ("费用表_" + a.date + ".xlsx"); wb2.save(p2)
    tc = 0.0
    for r in body:
        try:
            tc += float(r[head.index("生成费用(元)")])
        except Exception:
            pass
    print("总行数=%d（%s）生成费用=¥%.2f" % (len(rows), dict(Counter(r[0] for r in rows)), tc))
    print("OUTPUT:", p1); print("OUTPUT:", p2)


if __name__ == "__main__":
    main()
