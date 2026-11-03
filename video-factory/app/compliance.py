"""MVP 文案合规扫描器。规则只做确定性拦截，不替代人工终审。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def load_rules(path: Path) -> dict[str, Any]:
    # 配置文件使用 JSON 语法（同时也是合法 YAML），避免运行时依赖解析器。
    return json.loads(path.read_text(encoding="utf-8"))


def scan_text(text: str, industry: str, rules: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    groups = ["extreme_words", "send_away_words", "general_risks"]
    normalized_industry = industry.lower()
    for keyword, group_name in rules.get("industry_keywords", {}).items():
        if keyword.lower() in normalized_industry:
            groups.append(group_name)
    seen: set[tuple[str, str]] = set()
    for group in groups:
        spec = rules.get("groups", {}).get(group, {})
        for term in spec.get("terms", []):
            if re.search(re.escape(term), text, re.IGNORECASE):
                key = (group, term)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(
                    {
                        "group": group,
                        "term": term,
                        "level": spec.get("level", "block"),
                        "message": spec.get("message", "命中风险词"),
                    }
                )
    blocking = [item for item in findings if item["level"] == "block"]
    return {
        "passed": not blocking,
        "blocking_count": len(blocking),
        "warning_count": len(findings) - len(blocking),
        "findings": findings,
        "note": "机器扫描只覆盖确定性词项，仍须人工检查事实、原创度和行业语义风险。",
    }
