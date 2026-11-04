#!/usr/bin/env python3
"""Codex 任务强制预读清单（2026-08-09 用户定案：谁写谁读，物理卡点）
每个 codex 写产物前，必须先读对应知识库/skill，并写预读记录文件。
缺记录 → BLOCKED。本文件是 Codex 预读清单的唯一真相（管辖范围仅限预读清单；视频线口径、门禁实现、行业路由各自以其管辖范围内的权威源为准），新增节点时同步更新。

【规则优先级 2026-10-02 用户定】用户口径（current-rulings-20261001.md）＞ 优矩官方 brief ＞ 参考片实存值 ＞ 内部旧文档。与优矩 brief 冲突时，一律以用户口径为准；用户口径没覆盖的地方才按优矩执行。
【口径准备】先读 NEW_RULINGS（口径总表），再读其它文档。任何文档（含 wiki 贴素材规则、各 skill）与 NEW_RULINGS 冲突的条款一律作废，按 NEW_RULINGS 执行。

预读记录文件约定：项目目录 `_预读_<节点号>.md`，内容含：
- 已读文件（至少写一种完整路径：绝对路径、`workflow/` 相对路径、或 `.hermes/...` 相对路径；只写裸文件名仅告警、不硬拦）
- 引用要点（至少一条策略/结构/红线）
"""
import os

_HOME_DIR = os.path.expanduser("~")
WORKFLOW_HOME = os.environ.get("WORKFLOW_HOME", os.path.join(_HOME_DIR, "workflow"))
HERMES_HOME = os.environ.get("HERMES_HOME", os.path.join(_HOME_DIR, ".hermes"))

# 所有内容生产节点的固定基线；节点专属文档在 PRELOAD_REQUIRED 中继续追加。
# 【最高优先级】2026-10-01/02 用户口径总表；与其它文档冲突时以此为准
NEW_RULINGS = f"{HERMES_HOME}/skills/newmedia-operations/huolong-replica-template/references/current-rulings-20261001.md"

# 火龙专项文档：RG:195 / VP:132,215,391 / RG:133 要求「不读不许动笔」；industry-index 火龙/漫剧行指向 huolong-manju-standard.md。
# 2026-10-02 审计 N3：这 4 份不再是「所有内容生产节点」的基线，只在火龙项目的节点上要求（见 _is_huolong_project）；
# 非火龙项目（餐饮/教育/健身等）不得因此被拦。
HUOLONG_TEMPLATE_SKILL = f"{HERMES_HOME}/skills/newmedia-operations/huolong-replica-template/SKILL.md"
HUOLONG_BRIEF_RULES = f"{HERMES_HOME}/skills/newmedia-operations/huolong-replica-template/references/huolong-brief-rules-20260921.md"
HUOLONG_MANJU_STANDARD = f"{WORKFLOW_HOME}/wiki/concepts/huolong-manju-standard.md"
HUOLONG_REF_PATTERNS = f"{WORKFLOW_HOME}/wiki/concepts/huolong-ref-material-patterns.md"
HUOLONG_BASELINE = [
    HUOLONG_TEMPLATE_SKILL,
    HUOLONG_BRIEF_RULES,
    HUOLONG_MANJU_STANDARD,
    HUOLONG_REF_PATTERNS,
]

# 快乐马 happyhorse-1.1-r2v（默认生成通道）：接口文档 + 引用语法文档（2026-10-02 审计 C6，替换 Seedance 文档）
HAPPYHORSE_API_SKILL = f"{HERMES_HOME}/skills/business/dashscope-video-generation/SKILL.md"
HAPPYHORSE_REF_SYNTAX = f"{WORKFLOW_HOME}/wiki/video-shotcraft/references_happyhorse-adaptation.md"

CONTENT_PRODUCTION_BASELINE = [
    NEW_RULINGS,
    f"{HERMES_HOME}/skills/newmedia-operations/content-data-review/SKILL.md",
    f"{HERMES_HOME}/skills/newmedia-operations/content-review-gate/SKILL.md",
    f"{HERMES_HOME}/skills/newmedia-operations/video-production/SKILL.md",
    # huoshan 属广州/火山链路（2026-10-02 用户定：跟本机无关），不再列为基线必读
    f"{HERMES_HOME}/skills/newmedia-operations/content-redlines/SKILL.md",
]

# 节点 → 必须预读的文件（wiki 路径，相对 /home/ubuntu/workflow）
PRELOAD_REQUIRED = {
    "1": [  # 用户分析
        *CONTENT_PRODUCTION_BASELINE,
        f"{WORKFLOW_HOME}/wiki/concepts/industry-index.md",
    ],
    "2": [  # 爆款拆解
        *CONTENT_PRODUCTION_BASELINE,
        f"{WORKFLOW_HOME}/wiki/concepts/industry-index.md",
    ],
    "3": [  # 选题
        *CONTENT_PRODUCTION_BASELINE,
        f"{WORKFLOW_HOME}/wiki/concepts/industry-index.md",
    ],
    "4": [  # 文案（已由 data_source_gate._知识库引用.md 卡点覆盖，此处冗余保险）
        *CONTENT_PRODUCTION_BASELINE,
        f"{WORKFLOW_HOME}/wiki/concepts/industry-index.md",
    ],
    "5": [  # 分镜脚本 → 以 video-production §4.2、§6 为准（huoshan 不再单列必读）
        *CONTENT_PRODUCTION_BASELINE,
    ],
    "8": [  # Seedream 生图 → 读 seedream 模板
        *CONTENT_PRODUCTION_BASELINE,
        f"{HERMES_HOME}/skills/newmedia-operations/seedream-image-generation/SKILL.md",
        f"{HERMES_HOME}/skills/newmedia-operations/ai-image-gen-strategy/SKILL.md",
    ],
    "10": [  # 提示词 → 读快乐马接口文档 + 引用语法（2026-10-02 审计 C6：Seedance 文档换成快乐马）
        *CONTENT_PRODUCTION_BASELINE,
        HAPPYHORSE_API_SKILL,
        HAPPYHORSE_REF_SYNTAX,
        # 叠加参数与 LOGO 字段由 Hermes 出（NEW_RULINGS C19），不写进分镜/提示词；
        # App 画面一律后期贴片（NEW_RULINGS 补充第 23 条），提示词阶段不写屏内生成口径。
    ],
    "11": [  # 合规质检 → 读红线库
        *CONTENT_PRODUCTION_BASELINE,
    ],
    # ===== 2026-08-10 v5.0 语义节点预读映射 =====
    "MARKET_INSIGHT": [  # 洞察 → 读行业索引+行业文档（data_source_gate 覆盖知识库引用）
        *CONTENT_PRODUCTION_BASELINE,
        f"{WORKFLOW_HOME}/wiki/concepts/industry-index.md",
    ],
    "GROWTH_STRATEGY": [  # 打法 → 读阶段打法库
        *CONTENT_PRODUCTION_BASELINE,
        f"{WORKFLOW_HOME}/wiki/concepts/account-staged-operations-library.md",
        f"{WORKFLOW_HOME}/wiki/concepts/industry-index.md",
    ],
    "TOPIC_EXPERIMENT": [  # 选题 → 读行业索引
        *CONTENT_PRODUCTION_BASELINE,
        f"{WORKFLOW_HOME}/wiki/concepts/industry-index.md",
    ],
    "COPY_PACKAGE": [  # 文案 → 读红线库（data_source_gate 知识库引用卡点覆盖行业文档）
        *CONTENT_PRODUCTION_BASELINE,
    ],
    "CREATIVE_BLUEPRINT": [  # 分镜 → 以 video-production §4.2、§6 为准（huoshan 不再单列必读）
        *CONTENT_PRODUCTION_BASELINE,
    ],
    "MEDIA_PREP": [  # 素材与生成准备 → 读 seedream 生图 + 快乐马接口/引用语法
        *CONTENT_PRODUCTION_BASELINE,
        f"{HERMES_HOME}/skills/newmedia-operations/seedream-image-generation/SKILL.md",
        f"{HERMES_HOME}/skills/newmedia-operations/ai-image-gen-strategy/SKILL.md",
        HAPPYHORSE_API_SKILL,
        HAPPYHORSE_REF_SYNTAX,
    ],
    "MEDIA_PRODUCTION": [  # 提示词质检、快乐马生成、逐镜验证（合成/交付见 DELIVERY_PACKAGE）
        *CONTENT_PRODUCTION_BASELINE,
        HAPPYHORSE_API_SKILL,
    ],
    "DELIVERY_PACKAGE": [  # ffmpeg 合成、字幕/BGM/环境音、贴片与 LOGO 规则、终检交付
        *CONTENT_PRODUCTION_BASELINE,
        f"{WORKFLOW_HOME}/wiki/video-shotcraft/overlay-rules-quick.md",
    ],
}

# 【2026-10-02 用户当场定的硬规则，已写进口径总表 NEW_RULINGS 正文，合成/出片必须执行】
# 1. LOGO：凡口播念到「火龙漫剧」品牌名处就上屏（段内首次出现处 + 片尾 CTA 处），约 1.5 秒撤下；不常驻、不加角标。
# 2. 贴片与当句台词立场一致：吐槽/痛点处不得出现品牌自己的 App 画面；品牌画面只跟在正面句之后。
# 3. 同一素材全片只放一遍、禁循环（用户当场定）。
# 【出处更正 2026-10-02（审计 N6）】「App 图标/界面/播放画面全片综合展示时长 ≥5 秒」不是用户当场定的三条之一，
# 出处是优矩 brief 原文「综合展示时长不少于 5-10 秒」；它是全片累计值，不是每块贴片 ≥5 秒、单块不设上下限。

# 平台 → 爆款拆解预读（按选定平台）
PLATFORM_EXTRA = {
    "抖音": [],
    "小红书": [f"{WORKFLOW_HOME}/wiki/concepts/xiaohongshu-industry-beauty.md"],
    "视频号": [],
    "公众号": [f"{WORKFLOW_HOME}/wiki/concepts/wechat-public-account-industry.md"],
    "快手": [f"{WORKFLOW_HOME}/wiki/concepts/kuaishou-industry.md"],
}


def required_for(node: str) -> list:
    """去重返回必读清单（同一条目重复只算一次）。"""
    out = []
    for f in PRELOAD_REQUIRED.get(str(node), []):
        if f not in out:
            out.append(f)
    return out


def record_path(proj: str, node: str) -> str:
    return os.path.join(proj, f"_预读_{node}.md")


def _path_forms(f: str) -> set:
    """必读文件在预读记录里的合法写法（2026-10-02 审计 N5，认三种写法）：
    ① 完整绝对路径；
    ② `/home/ubuntu/` 下的相对路径（如 `workflow/wiki/...`、`.hermes/skills/...`）；
    ③ `/home/ubuntu/workflow/` 下的相对路径（如 `wiki/...`）。
    仍必须按完整路径匹配，禁止按文件名匹配——四份 skill 都叫 SKILL.md，
    按文件名时记录里出现一次「SKILL.md」就四份全算读过（2026-10-02 审计 C23）。
    """
    forms = {f}
    for root, alias in ((WORKFLOW_HOME, "workflow/"), (HERMES_HOME, ".hermes/")):
        prefix = root.rstrip("/") + "/"
        if f.startswith(prefix):
            rel = f[len(prefix):]
            forms.add(rel)
            forms.add(alias + rel)
    return forms


def _is_huolong_project(proj: str) -> bool:
    """火龙/漫剧项目判定（2026-10-02 审计 N3）：只看本项目，不看节点。

    命中任一即算火龙项目：
    ① 项目目录名含 huolong / manju / 火龙 / 漫剧；
    ② 项目 CONTEXT.md 正文出现「火龙」或「漫剧」。
    非火龙项目（餐饮/教育/健身等）返回 False，不再被火龙专项文档拦。
    """
    name = os.path.basename(os.path.normpath(proj)).lower()
    if any(k in name for k in ("huolong", "manju", "火龙", "漫剧")):
        return True
    ctx = os.path.join(proj, "CONTEXT.md")
    if os.path.exists(ctx):
        try:
            text = open(ctx, encoding="utf-8", errors="ignore").read()
        except OSError:
            return False
        if "火龙" in text or "漫剧" in text:
            return True
    return False


def _has_bare_name(content: str, basename: str) -> bool:
    """记录里是否出现「裸文件名」——某一行含该文件名但不含路径分隔符。

    2026-10-02 审计 N5：旧记录只写裸文件名时只告警不硬拦；含完整路径的行不算裸名
    （避免 basename 为 SKILL.md 时，被别的完整路径尾部的 SKILL.md 误判成裸名）。
    """
    for line in content.splitlines():
        s = line.strip().lstrip("-*•+ \t")
        if basename in s and "/" not in s and "\\" not in s:
            return True
    return False


def check_node_preload(proj: str, node: str) -> list:
    """检查某节点是否有预读记录且引用了要求的文件。返回问题列表（BLOCK）；裸文件名只告警不拦。

    2026-10-02 审计：
    ① C23：行业索引只在必读清单里列了它的节点检查（不再对所有节点硬查，消除误拦）；
    ② C23：必读文件按完整路径匹配（消除 SKILL.md 只读一份就全放行的漏放）；
    ③ N3：火龙专项文档只在火龙项目上要求（_is_huolong_project），非火龙项目不被拦；
    ④ N5：路径匹配认绝对/`workflow/`/`.hermes/...` 三种写法；旧记录只写裸文件名 → 告警不拦。
    """
    problems = []
    req = required_for(node)
    if _is_huolong_project(proj):
        for f in HUOLONG_BASELINE:
            if f not in req:
                req = req + [f]
    if not req:
        return problems  # 无强制预读要求
    rp = record_path(proj, node)
    if not os.path.exists(rp):
        problems.append(f"缺 {os.path.basename(rp)}——节点{node} 产出前必须先读: " + "; ".join(req))
        return problems
    content = open(rp, encoding="utf-8", errors="ignore").read()
    missing = []
    for f in req:
        if any(form in content for form in _path_forms(f)):
            continue
        if _has_bare_name(content, os.path.basename(f)):
            print(f"WARN: _预读_{node}.md 只匹配到裸文件名，建议补全路径: {f}")
        else:
            missing.append(f)
    if missing:
        problems.append(f"_预读_{node}.md 未引用要求的文件（按完整路径匹配）: " + "; ".join(missing))
    # 至少一条要点
    if "要点" not in content and "引用" not in content and "策略" not in content:
        problems.append(f"_预读_{node}.md 未记录引用要点")
    return problems


def main():
    """CLI: python3 codex_preload_manifest.py check <项目目录> <节点号>"""
    import sys
    if len(sys.argv) < 4 or sys.argv[1] != "check":
        print("用法: python3 codex_preload_manifest.py check <项目目录> <节点号(1-11) 或语义ID（如 MEDIA_PRODUCTION/DELIVERY_PACKAGE）>")
        sys.exit(3)
    proj = sys.argv[2]
    node = sys.argv[3]
    if not os.path.isdir(proj):
        print(f"BLOCKED: 项目目录不存在 {proj}")
        sys.exit(1)
    problems = check_node_preload(proj, node)
    if problems:
        print(f"BLOCKED:preload_{node}")
        for p in problems[:5]:
            print(f"  - {p}")
        sys.exit(2)
    print("ALLOWED")


if __name__ == "__main__":
    main()
