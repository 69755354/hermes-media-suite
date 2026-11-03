#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_generic.py — P0-3 通用批量校验脚本（2026-08-24 合并版落地）

把任务书 R1-RN 自检清单合并成一次执行。规则文件驱动（YAML/JSON），
一次输出 PASS/FAIL + 失败项编号 + 定位行。执行器最多跑「首次校验 → 一次修订 → 复跑」三轮。

用法:
  python3 verify_generic.py <产物文件> <规则文件>

规则文件格式（YAML）:
```yaml
checks:
  - id: R1
    name: 四段齐全
    type: keyword_required          # 产物必须含全部关键词
    keywords: ["G1", "G2", "G3", "G4"]
  - id: R3
    name: 台词逐字一致
    type: file_contains             # 另一个文件的行必须出现在产物中
    source_file: /path/to/字幕.ass
    keywords: ["句1", "句2"]
  - id: R8
    name: 无禁用表述
    type: keyword_forbidden         # 产物不得含这些词
    keywords: ["可能", "或许", "大概"]
forbidden_global: ["可能", "或许", "大概", "应该会"]   # 对所有检查生效的禁用词
```
"""
import argparse
import json
import pathlib
import re
import sys

try:
    import yaml
except ImportError:
    yaml = None


def load_rules(path: str) -> dict:
    p = pathlib.Path(path)
    if p.suffix in (".yaml", ".yml") and yaml:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if p.suffix == ".json":
        return json.loads(p.read_text(encoding="utf-8"))
    if yaml:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    raise SystemExit("需要 yaml 库或 JSON 规则文件")


def run_check(check: dict, text: str, base_dir: pathlib.Path) -> list:
    ctype = check.get("type", "keyword_required")
    cid = check.get("id", "?")
    name = check.get("name", "")
    label = f"[{cid} {name}]"
    fails = []
    if ctype == "keyword_required":
        for kw in check.get("keywords", []):
            if kw not in text:
                fails.append(f"  {label} 缺关键词「{kw}」")
    elif ctype == "keyword_forbidden":
        for kw in check.get("keywords", []):
            idx = text.find(kw)
            if idx >= 0:
                line_no = text[:idx].count("\n") + 1
                fails.append(f"  {label} 出现禁用词「{kw}」@L{line_no}")
    elif ctype == "regex_required":
        for pat in check.get("patterns", []):
            if not re.search(pat, text, re.M | re.I):
                fails.append(f"  {label} 未命中正则「{pat}」")
    elif ctype == "regex_forbidden":
        for pat in check.get("patterns", []):
            m = re.search(pat, text, re.M | re.I)
            if m:
                line_no = text[: m.start()].count("\n") + 1
                fails.append(f"  {label} 命中禁用正则「{pat}」@L{line_no}")
    elif ctype == "file_contains":
        src = check.get("source_file", "")
        p = pathlib.Path(src)
        if not p.is_absolute():
            p = base_dir / p
        if not p.exists():
            fails.append(f"  {label} 源文件不存在: {p}")
        else:
            src_text = p.read_text(encoding="utf-8", errors="ignore")
            for kw in check.get("keywords", []):
                if kw not in text:
                    fails.append(f"  {label} 产物缺源文件关键词「{kw}」")
                elif kw not in src_text:
                    fails.append(f"  {label} 源文件自身也不含「{kw}」（检查配置）")
    elif ctype == "output_line":
        if not re.search(r"OUTPUT:\s*\S+", text):
            fails.append(f"  {label} 缺 OUTPUT: 行")
    else:
        fails.append(f"  {label} 未知检查类型 {ctype}")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("rules")
    args = ap.parse_args()
    artifact = pathlib.Path(args.artifact)
    if not artifact.exists():
        print(f"BLOCKED: 产物不存在 {artifact}")
        return 2
    text = artifact.read_text(encoding="utf-8", errors="ignore")
    rules = load_rules(args.rules)
    all_fails = []
    for kw in rules.get("forbidden_global", []):
        idx = text.find(kw)
        if idx >= 0:
            line_no = text[:idx].count("\n") + 1
            all_fails.append(f"  [全局禁用] 出现「{kw}」@L{line_no}")
    for check in rules.get("checks", []):
        all_fails.extend(run_check(check, text, artifact.parent))
    if all_fails:
        print(f"BLOCKED: 产物 {artifact.name} 未过 {len(all_fails)} 项检查")
        print("\n".join(all_fails))
        return 1
    print(f"PASS: {len(rules.get('checks', []))} 项检查全部通过，文件 {artifact}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
