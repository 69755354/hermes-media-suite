#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把星图（投放消耗/收益）挂到「两个号全部作品」表上，成一张扁平表。

为何要合：星图数据≠作品数据。星图是单独一套（星图任务→有效播放/消耗/结算），
只有接了星图任务的号才有（实测只有二号 蜡笔新小漫），列口径也不同。
用户要「播放+消耗一起看」→ 两张按作品标题前缀对齐合并。

对齐规则：星图「视频标题」是截断的，用去空格前缀匹配作品名称；
同一标题有多条星图行（发布/未发布）时，取消耗最大的那条（=真发出去的那条）。

用法：python3 merge_xingtu_columns.py [--date YYYYMMDD]
输出：out/两个号作品+星图消耗_<日期>.xlsx（播放量降序）
"""
import argparse, datetime, pathlib, re
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

PROJ = pathlib.Path("/home/ubuntu/workflow/projects/attribution")
OUT = PROJ / "out"
COLS = ["号", "作品名称", "发布时间", "审核状态", "播放量", "星图任务", "星图有效播放量",
        "星图投放消耗(元)", "星图已结算收益(元)", "星图评估", "完播率", "5s完播率", "2s跳出率",
        "平均播放时长", "点赞量", "分享量", "评论量", "收藏量"]
W = [8, 42, 18, 11, 10, 12, 14, 16, 17, 10, 10, 11, 11, 13, 9, 9, 9, 9]


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def f(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y%m%d"))
    a = ap.parse_args()
    works_p = OUT / ("两个号全部作品_" + a.date + ".xlsx")
    xt_p = OUT / ("我方星图数据_" + a.date + ".xlsx")
    ws_ = load_workbook(works_p, read_only=True)[load_workbook(works_p, read_only=True).sheetnames[0]]
    works = list(ws_.iter_rows(min_row=2, values_only=True))
    xtb = load_workbook(xt_p, read_only=True)
    xts = xtb[xtb.sheetnames[0]]
    xh = [str(c).strip() for c in next(xts.iter_rows(max_row=1, values_only=True))]
    xmap = {}
    for r in xts.iter_rows(min_row=2, values_only=True):
        if not r or not r[0]:
            continue
        d = dict(zip(xh, r))
        t = norm(d.get("视频标题"))
        cur = xmap.get(t[:16])
        if cur is None or f(d.get("反推消耗(元)=已结算÷2.5%")) > f(cur.get("反推消耗(元)=已结算÷2.5%")):
            xmap[t[:16]] = d
    out = []
    hit = 0
    for w in works:
        name = norm(w[1])[:16]
        x = xmap.get(name)
        if x:
            hit += 1
        row = [w[0], w[1], w[2], w[3], w[5],
               x.get("任务", "") if x else "",
               x.get("有效播放量", "") if x else "-",
               x.get("反推消耗(元)=已结算÷2.5%", "") if x else "-",
               x.get("已结算收益(元)", "") if x else "-",
               x.get("视频评估", "") if x else "",
               w[6], w[7], w[9], w[10], w[11], w[12], w[13], w[14]]
        out.append(row)
    out.sort(key=lambda r: f(r[4]), reverse=True)
    wb = Workbook(); ws = wb.active; ws.title = "两个号作品+星图消耗"; ws.append(COLS)
    for r in out:
        ws.append(r)
    for c in ws[1]:
        c.font = Font(bold=True); c.alignment = Alignment(horizontal="center")
    for i, wd in enumerate(W, 1):
        ws.column_dimensions[get_column_letter(i)].width = wd
    ws.freeze_panes = "A2"
    p = OUT / ("两个号作品+星图消耗_" + a.date + ".xlsx")
    wb.save(p)
    tot = sum(f(r[7]) for r in out if isinstance(r[7], str) and r[7] not in ("-", ""))
    print("作品行=%d 星图命中=%d 投放消耗合计=¥%.2f" % (len(out), hit, tot))
    print("OUTPUT:", p)


if __name__ == "__main__":
    main()
