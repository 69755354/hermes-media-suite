#!/usr/bin/env python3
"""两个号作品 + 星图 → 老板表（固定 20 列格式）。

用法:
  python3 build_two_account_table.py --douyin 一号.json 二号.json --star 星图数据.json --out 表.xlsx

约定（2026-10-20 用户拍板，必须照做）:
- 20 列: 号|作品名称|发布时间|审核状态|播放量|星图有效播放|分成(元)|预估收益(元)|体裁|
  完播率|5s完播率|封面点击率|2s跳出率|平均播放时长|点赞量|分享量|评论量|收藏量|主页访问量|粉丝增量
- 号 写「一号」「二号」，不写账号名和 ID
- 预估收益 列按参考表口径填 0
- 按播放量降序；末行「合计」第二格写「共N行（一号X/二号Y）」
- 抖音侧列取作品列表导出 records（16 列原样），星图侧按标题匹配 item_name
- 星图里有钱但抖音列表没有的作品，单独补一行（号按星图账号，播放量 0）
"""
import argparse, json, re
from openpyxl import Workbook

HEADERS = ["号","作品名称","发布时间","审核状态","播放量","星图有效播放","分成(元)","预估收益(元)","体裁",
           "完播率","5s完播率","封面点击率","2s跳出率","平均播放时长","点赞量","分享量","评论量","收藏量",
           "主页访问量","粉丝增量"]

def norm(t): return re.sub(r"\s+", "", str(t or ""))
def num(v):
    try: return float(str(v).replace(",", "").strip())
    except Exception: return 0.0

def load(path):
    d = json.load(open(path, encoding="utf-8"))
    return d.get("records") if isinstance(d, dict) and "records" in d else (d.get("items") or d)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--douyin", nargs="+", required=True, help="按 一号 二号 顺序给导出 JSON")
    ap.add_argument("--star", default=None)
    ap.add_argument("--labels", default=None, help="按文件顺序给号名，如 二号 或 一号,二号")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    labels = (a.labels.split(",") if a.labels else ["一号", "二号"])
    while len(labels) < len(a.douyin):
        labels.append("二号")
    star = load(a.star) if a.star else []
    pool = [{"title": norm(s.get("item_name")), "raw": s.get("item_name"),
             "vv": num(s.get("valid_play")),
             "share": num(s.get("share_amount") or s.get("author_reward_amount")), "used": False}
            for s in star]
    rows = []
    for idx, path in enumerate(a.douyin[:2]):
        for r in load(path):
            t = norm(r.get("作品名称")); m = None
            ex = [c for c in pool if not c["used"] and c["title"] == t]
            if ex: m = ex[0]
            else:
                sm = [c for c in pool if not c["used"] and t[:14] and c["title"][:14] == t[:14]]
                if len(sm) == 1: m = sm[0]
            if m: m["used"] = True
            rows.append([labels[idx], r.get("作品名称", ""), r.get("发布时间", ""), r.get("审核状态", ""),
                         num(r.get("播放量")), m["vv"] if m else 0, m["share"] if m else 0.0, 0,
                         r.get("体裁", ""), num(r.get("完播率")), num(r.get("5s完播率")),
                         r.get("封面点击率", ""), num(r.get("2s跳出率")), num(r.get("平均播放时长")),
                         num(r.get("点赞量")), num(r.get("分享量")), num(r.get("评论量")),
                         num(r.get("收藏量")), num(r.get("主页访问量")), num(r.get("粉丝增量"))])
    for c in [x for x in pool if not x["used"] and (x["share"] > 0 or x["vv"] > 0)]:
        rows.append([labels[0] if len(labels) == 1 else "二号", c["raw"], "", "", 0, c["vv"], c["share"], 0, "", "", "", "", "", "", "", "", "", "", "", ""])
    rows.sort(key=lambda x: x[4], reverse=True)
    h1 = sum(1 for r in rows if r[0] == "一号")
    wb = Workbook(); ws = wb.active; ws.title = "两个号作品+星图"
    ws.append(HEADERS)
    for r in rows: ws.append(r)
    ws.append(["合计", f"共{len(rows)}行（一号{h1}/二号{len(rows)-h1}）", "", "",
               sum(r[4] for r in rows), sum(r[5] for r in rows),
               round(sum(r[6] for r in rows), 2), 0, "", "", "", "", "", "", "", "", "", "", "", ""])
    wb.save(a.out)
    print(json.dumps({"rows": len(rows), "一": h1, "二": len(rows)-h1,
                      "play": sum(r[4] for r in rows), "valid": sum(r[5] for r in rows),
                      "share": round(sum(r[6] for r in rows), 2)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
