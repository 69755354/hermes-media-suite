#!/usr/bin/env python3
"""既有正文合规红线与知识库检查。"""
import os, re, sys

GUARD_DIR = os.environ.get("WORKFLOW_GUARD_DIR") or os.path.join(
    os.environ.get("HERMES_HOME", os.path.join(os.path.expanduser("~"), ".hermes")), "guard")
ALERT_LOG = os.path.join(GUARD_DIR, "security_alerts.log")

# 广告法第九条极限词（规格库V3.0合规红线物理化，2026-08-03）
# 用组合词避免单字误杀（「最」单独出现≠违规，禁的是「最好/最佳/最强」等最高级）
LIMIT_WORDS = ["最好", "最佳", "最优", "最强", "最高级", "最低价", "最便宜", "最优惠", "顶级", "100%见效", "100%有效", "永久", "万能", "唯一", "绝对", "根治", "包治", "保本", "稳赚", "保上岸", "包就业", "国家级", "全网第一", "第一品牌", "销量第一"]
# 排除词：不是极限词用法的场景
LIMIT_EXCLUDE = ["第一人称", "第一时间", "第一步", "第一句", "第一次", "第一天", "第一个", "第一课", "最后一", "最后"]

# 高危特征词预警库（2026-08-03，软硬分层：只告警不熔断——避免语义误杀）
# 🟡 风险预警（恐吓营销/封建迷信/私域导流/AI未标注）——命中→日志标记+告警，不BLOCKED
WARN_WORDS = [
    "破财", "漏财", "招灾", "煞气", "灾祸", "霉运", "不吉", "转运", "化解", "开光", "消灾",  # 封建迷信
    "不买就", "不消费就", "错过就亏", "再不XX就晚了",  # 恐吓式营销（部分）
    "加我微信", "加v", "私我", "扫码加", "进群领", "加群",  # 私域导流
]

# 🔴 玄学牟利组合拦截（2026-08-03 升级：组合匹配避免误杀批判/辟谣）
# 例：「招财水晶都是骗人的」=玄学+否定→放行（辟谣合法）；「招财水晶开光了快来请」=玄学+牟利→BLOCKED
ZENXUE_WORDS = ["招财水晶", "开光", "转运珠", "化煞", "风水摆件", "消灾", "算命", "八字", "塔罗", "招财猫", "貔貅", "辟邪", "保平安符"]
ZENXUE_MOULI = ["购买", "请一个", "请一尊", "链接", "下单", "付费", "私信", "扫码", "优惠", "结缘", "供奉", "请回家", "点击", "售价", "原价", "加购", "付了", "花了", "转账", "交钱", "汇款", "买了", "付款"]
ZENXUE_FOUDING = ["骗人", "迷信", "假的", "别信", "智商税", "不推荐", "都是骗", "不可信", "伪科学", "没有用", "无用", "坑", "收割", "割韭菜", "别买"]

# 🔴 封建迷信分层管控（2026-08-03 定稿：高危熔断 + 普通名词强制评审）
# 高危迷信行为词组：描述超自然力量+解决方案+诱导付费/焦虑，几乎无合规场景 → 直接BLOCKED
METAPHYSICS_HIGH = ["改运", "消灾", "化解灾厄", "辟邪", "符咒", "做法事", "跳大神", "付费占卜", "预测祸福", "斩断烂桃花", "磁场治病", "开光法物", "请符", "驱邪", "镇宅", "招魂", "转运法", "因果报应化解", "前世今生化解"]
# 普通玄学名词：可能是批判科普/文化现象，也可能是宣扬迷信 → 打 risk_metaphysics 标签强制评审，不直接熔断
METAPHYSICS_NORMAL = ["八字", "塔罗", "星盘", "风水", "生肖运势", "五行", "星座运势", "紫微", "面相", "手相", "命理", "占卜", "算命"]

# 🔴 送客词拦截（2026-08-08 用户定案：全行业禁止将目标用户导向第三方免费替代服务）
# 底层逻辑：客户做自媒体为了获客，把读者导向第三方免费服务 = 送客（替别人做嫁衣）
# 默认全行业 BLOCKED；客户明确要求时，项目目录放 _豁免送客词.flag 才放行
# ⚠️ 只收「第三方免费替代服务」特征词——客户自己的转化渠道（自己的店铺/企微/预约入口）不是送客，禁收
SEND_AWAY_WORDS = [
    # 心理/健康类（实证送客词，2026-08-08 二次纠正后定案）
    "心理援助热线", "400-161-9995", "12356", "全国心理援助", "心理危机干预热线",
    "免费心理援助", "公益心理热线", "心理求助热线",
    # 健康/医美类
    "免费在线问诊平台", "官方挂号", "政府免费筛查",
    # 教育类
    "政府免费培训", "国家免费课程",
    # 通用第三方公益服务
    "公益免费咨询热线", "官方救助热线",
]
SEND_AWAY_FLAG = "_豁免送客词.flag"  # 客户明确要求时在项目目录创建此文件 → 跳过送客词检查

def log_blocked(msg):
    with open(ALERT_LOG, "a") as f:
        f.write(f"[data_source_gate] {msg}\n")

def check_body(proj):
    """正文合规红线检测（node4_body）：
    文件路由匹配（2026-08-03 修复）：不做死文件名——扫项目目录所有「节点4_*.md」+口播链路文案文件，
    保证极限词硬规则全链路生效（含口播独立链路）"""
    import glob
    problems = []
    # 路由匹配：全链路节点4产物 + 口播链路文案
    patterns = [
        os.path.join(proj, "节点4_*.md"),
        os.path.join(proj, "节点5_*.md"),
        os.path.join(proj, "文案*.md"),
        os.path.join(proj, "口播文案*.md"),
        os.path.join(proj, "*口播*.md"),
        os.path.join(proj, "artifacts", "copy", "*.md"),
    ]
    files = set()
    for pat in patterns:
        files.update(glob.glob(pat))
    for p in sorted(files):
        content = open(p, encoding="utf-8", errors="ignore").read()
        fname = os.path.basename(p)
        # 极限词检测（广告法第九条）
        for w in LIMIT_WORDS:
            if w in content and not any(x in content for x in LIMIT_EXCLUDE):
                idx = content.find(w)
                ctx = content[max(0, idx-20):idx+20].replace('\n', ' ')
                problems.append(f"[{fname}] 极限词「{w}」: ...{ctx}...")
        # 🟡 高危特征词预警（只告警不阻断——语义依赖上下文，硬拦会误杀）
        for w in WARN_WORDS:
            if w in content:
                idx = content.find(w)
                ctx = content[max(0, idx-15):idx+15].replace('\n', ' ')
                log_blocked(f"WARN[{fname}] 高危特征词「{w}」: ...{ctx}...（仅告警，需人工评审确认）")
        # 🔴 玄学牟利组合拦截：玄学词+牟利信号（无否定信号）→ BLOCKED；玄学+否定→放行（辟谣）
        for z in ZENXUE_WORDS:
            if z in content:
                has_mouli = any(m in content for m in ZENXUE_MOULI)
                has_fouding = any(f in content for f in ZENXUE_FOUDING)
                if has_mouli and not has_fouding:
                    idx = content.find(z)
                    ctx = content[max(0, idx-15):idx+30].replace('\n', ' ')
                    problems.append(f"[{fname}] 玄学牟利「{z}」: ...{ctx}...（含购买/付费信号且无否定语境）")
                elif has_fouding:
                    log_blocked(f"OK[{fname}] 玄学批判/辟谣「{z}」（含否定词，放行）")
        # 🔴 封建迷信高危行为词组：直接熔断（无合规场景）
        for h in METAPHYSICS_HIGH:
            if h in content:
                idx = content.find(h)
                ctx = content[max(0, idx-15):idx+30].replace('\n', ' ')
                problems.append(f"[{fname}] 迷信高危词组「{h}」: ...{ctx}...（超自然+方案+诱导，无合规场景）")
        # 🟡 普通玄学名词：打 risk_metaphysics 标签强制评审（不熔断——可能是批判科普）
        for n in METAPHYSICS_NORMAL:
            if n in content:
                log_blocked(f"RISK[{fname}] 玄学名词「{n}」→ risk_metaphysics 标签：强制合规评审（批判科普放行/宣扬迷信拦截）")
        # 🔴 送客词拦截（全行业，2026-08-08 用户定案）：默认 BLOCKED，客户明确要求=flag 豁免
        if not os.path.exists(os.path.join(proj, SEND_AWAY_FLAG)):
            for s in SEND_AWAY_WORDS:
                if s in content:
                    idx = content.find(s)
                    ctx = content[max(0, idx-15):idx+30].replace('\\n', ' ')
                    problems.append(f"[{fname}] 送客词「{s}」: ...{ctx}...（将用户导向第三方免费服务=送客，全行业禁止；客户明确要求→项目目录放 _豁免送客词.flag）")
    return problems


def check_kb_ref(proj):
    """知识库引用检查（2026-08-09 新增物理卡点：node4_kb）：
    文案产出必须引用行业知识库——项目目录要有 _知识库引用.md，
    记录：读了哪篇行业文档 + 引用了什么要点。缺文件或引用文档不存在 → BLOCKED。
    """
    problems = []
    kb_file = os.path.join(proj, "_知识库引用.md")
    if not os.path.exists(kb_file):
        problems.append("缺 _知识库引用.md——文案产出前必须先读行业知识库文档（industry-index.md 按行业查表）并记录引用要点。示例格式见 wiki 索引铁律。")
        return problems
    content = open(kb_file, encoding="utf-8", errors="ignore").read()
    # 检查是否记录了「读取文档」
    import re
    docs = re.findall(r"industry-[a-z-]+\.md|xiaohongshu-industry-[a-z-]+\.md|kuaishou-industry\.md|wechat-public-account-industry\.md", content)
    if not docs:
        problems.append("_知识库引用.md 未记录任何行业文档（需含 industry-*.md 文件名）——先 read_file 行业文档再写文案")
        return problems
    # 检查引用的文档真实存在
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from industry_kb_map import doc_exists
    for d in set(docs):
        if not doc_exists(d):
            problems.append(f"_知识库引用.md 引用的行业文档不存在: {d}（查 wiki/concepts/industry-index.md 确认文件名）")
    # 检查是否记录了「引用要点」
    if "要点" not in content and "引用" not in content and "策略" not in content:
        problems.append("_知识库引用.md 未记录引用要点（需写明引用了行业文档的哪些策略/结构）")
    return problems

def main():
    if len(sys.argv) < 4 or sys.argv[1] != "check":
        print("用法: python3 data_source_gate.py check <项目目录> <node4_body|all>")
        sys.exit(3)
    proj = sys.argv[2]
    gate = sys.argv[3]
    if gate not in ("node4_body", "all"):
        print("UNKNOWN_GATE:" + gate)
        sys.exit(3)
    if not os.path.isdir(proj):
        log_blocked(f"BLOCKED: 项目目录不存在 {proj}")
        sys.exit(1)

    targets = []
    if gate in ("node4_body", "all"):
        targets.append(("node4_body", os.path.join(proj, "节点4_文案定稿.md")))

    blocked = False
    for gname, fpath in targets:
        if gname == "node4_body":
            problems = check_body(proj)
            # 2026-08-09 新增：知识库引用物理卡点（node4_kb 并入 node4_body）
            kb_problems = check_kb_ref(proj)
            problems = problems + kb_problems
            if not problems:
                continue
            print(f"BLOCKED:{gname}:数据不达标")
            for p in problems[:5]:
                print(f"  - {p}")
                log_blocked(f"BLOCKED {gname}: {p}")
            blocked = True
            continue
    if blocked:
        sys.exit(2)
    print("ALLOWED")
    sys.exit(0)

if __name__ == "__main__":
    main()
