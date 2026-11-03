#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文案风格检查器 v1 —— 句式库/违禁清单的自动执行版。
用法: python3 check_copy_style.py <定稿.md> [--json]
只做机械判定，不替代人工审美。分数不过仍需人过一遍。
"""
import re, sys, json, itertools

PATTERNS = [
    ("A1","不是…而是/不是A是B", r"不是[^。；，]{0,20}[，,]?\s*是[^。；]{0,20}"),
    ("A2","不仅…而且", r"不仅[^。]{0,30}(而且|还|也)"),
    ("A4","首先/其次/再次", r"(首先|其次|再次|最后一点)，"),
    ("A5","AI连接词", r"(此外|值得注意|综上所述|总而言之|进而|因而)"),
    ("A6","双重否定", r"不是不|并非不|不得不说是"),
]
BAD_WORDS = {
    "程度虚词": ["有效","显著","彻底","快速","立刻见效","立竿见影","瞬间"],
    "形容词堆叠": ["温和不刺激","清新持久","深层呵护","专业配方","全方位","深层清洁","轻柔护理"],
    "医疗动词": ["治疗","治愈","消炎","修复牙本质","杀菌","处方","医用级"],
    "横向对比": ["吊打","完胜","唯一","最好","第一品牌"],
    "催促吼叫": ["赶紧","马上","手慢无","错过就没","最后一天","抓紧"],
    "极限词": ["顶级","国家级","最先进","最强","销量第一"],
}
IGNORE = ["冷酸灵","生物活性玻璃陶瓷","重组角蛋白","双11","双十一","抖音","牙膏","抗敏"]

def parse(md):
    items, cur = [], None
    for line in md.splitlines():
        h = re.match(r"^##\s*(.+?)\s*$", line)
        if h and (re.match(r"^[ABC]\d", h.group(1)) or "方向" in h.group(1)):
            cur = {"title": h.group(1), "hook":"", "body":[]}
            items.append(cur); continue
        if cur is None: continue
        m = re.match(r"^\*\*【1[^】]*】\*\*\s*(.+)$", line.strip())
        if m: cur["hook"] = m.group(1).strip(); continue
        if line.strip(): cur["body"].append(line.strip())
    return items

def check(items):
    rep, total_deduct = [], 0
    for it in items:
        name = it["title"].split("｜")[0]
        body = [re.sub(r"\*\*【[^】]*】\*\*", "", b) for b in it["body"]]
        prose = it["hook"] + " " + " ".join(body)
        hits = []
        warns = []
        for pid, label, pat in PATTERNS:
            for m in re.finditer(pat, prose):
                hits.append((pid, label, m.group(0)[:24]))
        if len(hits) >= 1 and hits[0][0] == "A1":
            warns.append(hits.pop(0))
        sents = [x.strip() for x in re.split(r"[。！？；\n]", prose) if len(x.strip()) > 3]
        for a,b,c in zip(sents, sents[1:], sents[2:]):
            if a[:2].strip() and a[:2]==b[:2]==c[:2]: hits.append(("A3","三句同头排比",a[:12]))
        for cat, words in BAD_WORDS.items():
            for w in words:
                for mm in re.finditer(w, prose):
                    pre = prose[max(0, mm.start()-3):mm.start()]
                    if w in ("马上","赶紧") and re.search(r"别|不|勿|没", pre): continue
                    hits.append((cat, "违禁词", mm.group(0)))
        if "！" in prose: hits.append(("C","感叹号","！"))
        fd = prose.count("——")
        if fd >= 2: hits.append(("A7","破折号泛滥", "%d处" % fd))
        hl = len(re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]","",it["hook"]))
        if hl > 25: hits.append(("C","钩子超25字",f"{hl}字"))
        seg2 = seg3 = ""
        for b in it["body"]:
            if "【2" in b: seg2 = re.sub(r"\*\*【[^】]*】\*\*", "", b)
            if "【3" in b: seg3 = re.sub(r"\*\*【[^】]*】\*\*", "", b)
        if seg2:
            jargon = re.findall(r"生物活性玻璃陶瓷|重组角蛋白|氟化亚锡|硝酸钾|氯化锶|牙本质小管", seg2)
            if len(jargon) >= 3: hits.append(("C","专业名词堆积",f"{len(jargon)}个"))
        if seg3:
            verbs = re.findall(r"刷|挤|舔|漱|含|压|停|换|吹|喝|咬|拍|试|看|翻|放|搁|配|囤|拆|留|摸|照|比|选|挑|记|挂|收|上|拿|擦|冲|泡|贴", seg3)
            if len(verbs) < 2: hits.append(("C","第3段缺可执行动作",f"动词{len(verbs)}个"))
        deduct = min(len(hits)*6, 60)
        total_deduct += deduct
        rep.append({"name":name,"hook":it["hook"],"hook_len":hl,"hits":hits,"warns":warns,"deduct":deduct})

    ng = {}
    for r, it in zip(rep, items):
        t = it["hook"] + "".join(it["body"])
        for w in IGNORE: t = t.replace(w,"")
        t = re.sub(r"[^\u4e00-\u9fa5]","",t)
        ng[r["name"]] = set(t[i:i+8] for i in range(len(t)-7))
    dups = []
    for (a,sa),(b,sb) in itertools.combinations(ng.items(),2):
        if not sa or not sb: continue
        inter = len(sa.intersection(sb)); rate = inter/min(len(sa),len(sb))
        if rate > 0.10: dups.append((a,b,round(rate*100,1)))
    avg = 100 - total_deduct//max(len(rep),1)
    score = max(0, avg - min(len(dups)*5, 30))
    return rep, dups, score

def main():
    p = sys.argv[1]
    md = open(p, encoding="utf-8").read()
    items = parse(md)
    rep, dups, score = check(items)
    verdict = "可用" if score>=90 else ("小修" if score>=75 else "重写")
    print("文件: %s" % p)
    print("解析条数: %d   综合得分: %d/100   %s" % (len(items), score, verdict))
    print("="*72)
    for r in rep:
        flag = "OK " if not r["hits"] else "!! "
        print("%s%-5s 钩子%2d字 扣%2d  %s" % (flag, r["name"], r["hook_len"], r["deduct"], r["hook"][:34]))
        for h in r["hits"]:
            print("      · [%s] %s: %s" % (h[0], h[1], h[2]))
        for h in r.get("warns", []):
            print("      ~ 提示(不扣分) [%s] %s: 每条片限1次" % (h[0], h[1]))
    print("="*72)
    if dups:
        print("重复度过高 %d 对:" % len(dups))
        for a,b,rate in dups[:20]: print("  %s × %s  重合 %s%%" % (a,b,rate))
    else:
        print("重复度: 全部 ≤10% 合格")
    if "--json" in sys.argv:
        print(json.dumps({"score":score,"items":rep,"dups":dups}, ensure_ascii=False))

if __name__ == "__main__":
    main()
