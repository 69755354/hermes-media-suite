#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""火龙漫剧三类文案·对话逻辑自检（2026-10-11 用户要求：不能每次靠人指出）
用法: python3 check_dialog_logic.py <文案.md>
判据全部来自 2026-10-11 用户当场指出的 5 类硬伤 + 首句口径。
"""
import re, sys, collections

BASE_Q = re.compile(r'(开会员|会员费|要钱|花钱|收费|交钱|解锁|弹窗|弹东西|单买|缴费|加钱|扣钱|续费)')
DEVICE_PAIRS = ("拉人", "做任务", "任务", "新人")
SELLWORD = re.compile(r'(不用|不需要|免费|不花钱|不收费|有，|海量|资源)')

def load_items(path):
    s = open(path, encoding="utf-8").read()
    items = []
    for b in re.split(r'\n### ', s)[1:]:
        head = b.split("\n")[0].strip()
        m = re.match(r'(免费|激励|种草)-\d+', head)
        if not m:
            continue
        lines = []
        for ln in b.split("\n"):
            t = re.match(r'\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|', ln)
            if t and t.group(2).strip() in ("甲", "乙"):
                lines.append((int(t.group(1)), t.group(2).strip(), t.group(3).strip()))
        if lines:
            items.append((head, lines))
    return items

def check(path):
    fails = []
    items = load_items(path)
    if not items:
        return ["读不到条目（检查表格格式：| 句 | 说话人 | 口播文案 |）"], 0
    for head, lines in items:
        typ = head.split("-")[0]
        spk = {s for _, s, _ in lines}
        if spk - {"甲", "乙"} or len(spk) < 2:
            fails.append(f"{head}：说话人异常 {spk}（必须只有甲、乙）")
        f1 = lines[0][2]
        # ① 首句禁「攒火龙币」当钩子（激励类）
        if typ == "激励" and re.search(r'^.{0,6}(看剧.{0,4}攒火龙币|攒火龙币)', f1):
            fails.append(f"{head}：首句用「攒火龙币」开头（实测平均播放≤4.4s，禁用）→ {f1[:24]}")
        # ② 首句已宣告「不花钱/全会看/自动联播」→ 后续禁问基础问题
        declared = re.search(r'(不花|免费|白看|白刷|自动联播|不用手点|看到大结局|看完了|看完整部)', f1)
        if declared:
            for i, s, txt in lines[1:]:
                if s == "甲" and BASE_Q.search(txt) and re.search(r'(吗|吧|不\？|\?)', txt):
                    fails.append(f"{head}：首句已宣告「{declared.group(1)}」，甲第{i}句又问基础问题 → {txt[:26]}")
        # ③ 连续「质疑机制 → 报卖点」清单化
        qa = [(i, s, t) for i, s, t in lines]
        streak = 0
        for k in range(len(qa) - 1):
            i, s, t = qa[k]; j, s2, t2 = qa[k + 1]
            if s == "甲" and s2 == "乙" and any(w in t for w in DEVICE_PAIRS) and SELLWORD.search(t2):
                streak += 1
                if streak >= 3:
                    fails.append(f"{head}：出现连续 3 组以上「质疑机制→报卖点」清单式问答（从第{i}句起）")
                    break
            else:
                streak = 0
        # ④ 空问句当主问句
        empties = [(i, t) for i, s, t in lines if s == "甲" and len(t) <= 8 and re.search(r'(真的|假的|有这好事|这你都知道|真的假的)', t)]
        if len(empties) > 1:
            fails.append(f"{head}：零信息量空问句 {len(empties)} 处（≤1 处）→ " + " / ".join(t for _, t in empties))
        # ⑤ 句式机械：乙以「不用」开头超过 2 次
        n = sum(1 for _, s, t in lines if s == "乙" and t.startswith("不用"))
        if n > 2:
            fails.append(f"{head}：乙以「不用」开头 {n} 次（≤2 次）")

        # ⑦ 甲问基础问题必须承接乙上一句（对齐高消耗参考 A/C：甲只对乙刚说的话追问/确认）
        for k in range(1, len(lines) - 1):
            i, s1, t1 = lines[k]
            if s1 != "甲":
                continue
            if not BASE_Q.search(t1):
                continue
            prev = " ".join(t for _, sp, t in lines[max(0, k - 2):k] if sp == "乙")
            key = [w for w in ("会员", "花钱", "收费", "交钱", "解锁", "弹窗") if w in t1]
            if key and not any((w in prev) or (w in ("会员", "花钱", "收费", "交钱") and re.search(r'不花|免费|不用|不收费|一分', prev)) for w in key):
                fails.append(f"{head}：甲第{i}句问「{'/'.join(key)}」但乙上文没提过（问与上文脱节，参考片是顺着追问）→ {t1[:24]}")
        # ⑥ 落点
        if "点击左下方下载火龙漫剧" not in lines[-1][2] + " ".join(t for _, _, t in lines[-2:]):
            fails.append(f"{head}：末句缺落点「点击左下方下载火龙漫剧」")
    # ⑧ 跨条重复检测：同类 8 条内，任何一句原文出现 ≥2 次即不合格
    # 白名单：优矩固定 4 句话术 + 落点句（口径要求原句照用，允许重复）
    FIXED = ("新人看剧5分钟后满0.3元就能提现", "累计签到后可提现",
             "看剧就能攒火龙币，火龙币可通过做任务兑换收益", "新人累计签到还有额外火龙币奖励",
             "点击左下方下载火龙漫剧")
    def exempt(t):
        return any(k in t for k in FIXED)
    seen = collections.defaultdict(list)
    for head, lines in items:
        typ = head.split("-")[0]
        for i, sp, t in lines:
            seen[(typ, t.strip())].append(head)
    for (typ, t), heads in seen.items():
        if exempt(t):
            continue
        if len(heads) >= 2:
            fails.append(f"{typ}类：同一句在 {len(heads)} 条里重复出现 → 「{t[:26]}」（{','.join(h.split('｜')[0] for h in heads)}）")
    # ⑨ 收尾句模板重复：同名条目的倒数第 2 句（甲收尾）在同类重复 ≥2 次
    tails = collections.defaultdict(list)
    for head, lines in items:
        typ = head.split("-")[0]
        if len(lines) >= 2:
            tails[(typ, lines[-2][2].strip())].append(head)
    for (typ, t), heads in tails.items():
        if exempt(t):
            continue
        if len(heads) >= 2 and len(t) <= 14:
            fails.append(f"{typ}类：收尾句一个句式用了 {len(heads)} 次 → 「{t[:20]}」")

    # ⑩ 收尾前缀重复：末句去掉落点关键词后的前缀在同类里重复
    pre = collections.defaultdict(list)
    for head, lines in items:
        typ = head.split("-")[0]
        tail = lines[-1][2].replace("点击左下方下载火龙漫剧", "").strip("，,。 ")
        if tail:
            pre[(typ, tail)].append(head)
    for (typ, t), heads in pre.items():
        if len(heads) >= 2:
            fails.append(f"{typ}类：落点前的收尾话术重复 {len(heads)} 次 → 「{t[:24]}」")
    # ⑪ 结构骨架重复：同类两条逐句对齐，说话人一致且前 6 字相同的句位 ≥4 → 判为同一模子
    bytype = collections.defaultdict(list)
    for head, lines in items:
        bytype[head.split("-")[0]].append((head, lines))
    for typ, group in bytype.items():
        for a in range(len(group)):
            for b in range(a + 1, len(group)):
                (h1, l1), (h2, l2) = group[a], group[b]
                same = 0
                for (i1, s1, t1), (i2, s2, t2) in zip(l1, l2):
                    if s1 == s2 and t1[:6] == t2[:6]:
                        same += 1
                if same >= 4:
                    fails.append(f"{typ}类：{h1.split('｜')[0]} 与 {h2.split('｜')[0]} 结构骨架重复（{same} 个句位相同模板）")

    # ⑬ 乙句过碎 + ⑭ 中段没有堆料段（参考片中段＝甲一句→乙连说 3~5 句）
    for head, lines in items:
        yi = [x[2] for x in lines if x[1] == "乙"]
        if yi and sum(len(t) for t in yi) / len(yi) < 14:
            fails.append(f"{head.split('｜')[0]}：乙句过碎（平均 {sum(len(t) for t in yi)/len(yi):.1f} 字 <14），中段要一口气把信息说完")
        runs, cur = [], 0
        for x in lines:
            if x[1] == "乙":
                cur += 1
            else:
                if cur: runs.append(cur)
                cur = 0
        if cur: runs.append(cur)
        if runs and max(runs) < 2:
            fails.append(f"{head.split('｜')[0]}：全程一人一句严格交替，没有「乙连说 2 句以上」的堆料段（参考片中段是甲一句→乙连说 3~5 句）")
    # ⑮ 优矩红线（原文行 327）：贬低竞争对手/抹黑竞品 —— 只许中性说「之前用的平台要花钱」
    BAD = re.compile(r'(弹付款|催缴|别家|上一家|一集一集让你|套路|割韭菜|骗人|黑心|坑人)')
    for head, lines in items:
        for x in lines:
            if BAD.search(x[2]):
                fails.append(f"{head.split('｜')[0]}：涉嫌贬低竞品（优矩红线 行327）→「{x[2][:26]}」")
    # ⑯ 乙不得凭空知道甲的旧平台（甲没点名，乙就不能用「那套/那家」去接）——参考片做法是直接给替代方案
    REFBAD = re.compile(r'(那套|那家|它家|你用的那个|之前那|那个平台)')
    for head, lines in items:
        for x in lines:
            if x[1] == "乙" and REFBAD.search(x[2]):
                fails.append(f"{head.split('｜')[0]}：乙凭空指代甲的旧平台（甲没点名却用「{REFBAD.search(x[2]).group(1)}」）→「{x[2][:24]}」")
    # ⑰ 品牌名必须由「先知道它的人」说出：甲开场是体验/结果型（没提痛点、没提品牌）时，乙不得第一个说出「火龙漫剧」
    PAIN = re.compile(r"(烦|卡住|打断|麻烦|气死|最烦|受够|白刷|浪费|老被)")
    for head, lines in items:
        f1 = lines[0][2]
        who = [x[1] for x in lines if "火龙漫剧" in x[2]]
        if who and who[0] == "乙" and not PAIN.search(f1):
            fails.append(f"{head.split('｜')[0]}：乙凭空知道品牌名（甲首句「{f1[:14]}」没提痛点也没提品牌，乙却先说火龙漫剧）")
    # ⑱ 骨架②里：甲讲体验不提品牌时，乙必须先问「那你用什么/在哪看」，甲才能说出品牌（照参考片③）
    ASK = re.compile(r"(那你|你在|你用的|在哪|用的什么|用什么|哪个平台)")
    for head, lines in items:
        f1 = lines[0][2]
        who = [(i, x[1]) for i, x in enumerate(lines) if "火龙漫剧" in x[2]]
        if who and who[0][1] == "甲" and not PAIN.search(f1):
            bi = who[0][0]
            asked = any(x[1] == "乙" and ASK.search(x[2]) for x in lines[1:bi])
            if not asked:
                fails.append(f"{head.split('｜')[0]}：甲说品牌前没人问过（参考片③是乙先问「那你用什么追剧」，甲才说）")
    return fails, len(items)

if __name__ == "__main__":
    p = sys.argv[1]
    fails, n = check(p)
    print(f"条目数：{n}")
    if fails:
        print(f"❌ 未通过 {len(fails)} 项：")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("✅ 全部通过（双人/身份一致/无清单化/无空问句/句式不机械/落点齐全）")
