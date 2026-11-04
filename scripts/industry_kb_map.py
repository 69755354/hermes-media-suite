#!/usr/bin/env python3
"""行业知识库映射（2026-08-09 新增：物理卡点用）
与 wiki/concepts/industry-index.md 同步的机器可读版。
新增行业文档时，两处都要更新。
"""
import os

WORKFLOW_HOME = os.environ.get("WORKFLOW_HOME", os.path.join(os.path.expanduser("~"), "workflow"))
WIKI_ROOT = os.path.join(WORKFLOW_HOME, "wiki", "concepts")

# 行业关键词 → 行业文档（与 industry-index.md 一致）
INDUSTRY_MAP = [
    (["餐饮", "饭店", "火锅", "烧烤", "奶茶", "咖啡", "小吃", "面馆"], "industry-catering.md"),
    (["教育", "培训", "知识付费", "课程", "教辅", "职业技能"], "industry-education.md"),
    (["情感", "恋爱", "婚姻", "心理", "情绪", "励志"], "industry-emotion.md"),
    (["健身", "运动", "瑜伽", "减肥", "健康管理", "体育", "养生", "理疗", "调理"], "industry-fitness.md"),
    (["母婴", "育儿", "亲子", "儿童", "孕妇", "产后"], "industry-maternal.md"),
    (["财经", "理财", "投资", "保险", "商业", "创业", "职场"], "industry-finance.md"),
    (["美妆", "护肤", "化妆品", "个护", "美容", "调肤"], "xiaohongshu-industry-beauty.md"),
    (["火龙", "漫剧", "国新汇金", "优矩"], "huolong-manju-standard.md"),
]

FALLBACK = "industry-strategy-overview.md"


def resolve_industry_doc(industry_text: str) -> str:
    """按行业关键词解析应读的行业文档（宽松匹配）。"""
    if not industry_text:
        return FALLBACK
    for keywords, doc in INDUSTRY_MAP:
        for kw in keywords:
            if kw in industry_text:
                return doc
    return FALLBACK


def doc_exists(doc_name: str) -> bool:
    return os.path.exists(os.path.join(WIKI_ROOT, doc_name))
