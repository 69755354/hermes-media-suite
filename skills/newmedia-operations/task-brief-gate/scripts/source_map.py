#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""source_map.py — P0-2 一次性 Source Map 生成器（只读，2026-08-24）

对任务书 SOURCE_MAP 段（或旧版 DATA_SOURCE= 逗号列表）列出的每个文件输出：
  文件 hash、总行数、关键词命中行——执行器按行号读，不用全文扫。
用法:
  python3 source_map.py <任务书文件>
"""
import hashlib
import pathlib
import re
import sys

KEYWORDS = ["定案", "硬切", "镜界", "人物", "切点", "UI", "台词", "时长", "时码",
            "Seedance", "duration", "负面", "@图", "参考", "贴片", "尾卡", "运镜"]


def index_file(fpath: str, purpose: str, rows: str) -> str:
    p = pathlib.Path(fpath)
    out = [f"\n## {fpath}", f"目的: {purpose}" + (f" | 必读行号: {rows}" if rows else "")]
    if not p.exists():
        out.append("状态: MISSING")
        return "\n".join(out)
    data = p.read_bytes()
    txt = data.decode("utf-8", "ignore")
    out.append(f"状态: OK | {len(data)} 字节 | {len(txt.splitlines())} 行")
    out.append(f"sha256: {hashlib.sha256(data).hexdigest()[:16]}")
    for kw in KEYWORDS:
        hits = [ln_no for ln_no, l2 in enumerate(txt.splitlines(), 1) if kw in l2]
        if hits:
            shown = ",".join(str(h) for h in hits[:20])
            out.append(f"关键词[{kw}] 命中行: {shown}{' …' if len(hits) > 20 else ''}")
    return "\n".join(out)


def source_map(brief_path: pathlib.Path) -> str:
    text = brief_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out = [f"# Source Map — {brief_path.name}"]
    # 优先解析 SOURCE_MAP 表格段：| 文件 | 必读行号 | 读取目的 |
    in_sm, sm_rows = False, []
    for ln in lines:
        if ln.startswith("## 3. SOURCE_MAP") or (ln.startswith("##") and "SOURCE_MAP" in ln):
            in_sm = True
            continue
        if in_sm and ln.startswith("## ") and "SOURCE_MAP" not in ln:
            break
        if not in_sm:
            continue
        m = re.match(r"\|\s*(\S+?)\s*\|\s*([^|]*)\s*\|\s*([^|]*)\s*\|", ln)
        if not m:
            continue
        fpath, rows, purpose = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        if fpath and fpath != "文件" and not fpath.startswith("---"):
            sm_rows.append((fpath, rows, purpose))
    if sm_rows:
        out += [index_file(f, p, r) for f, p, r in sm_rows]
        return "\n".join(out)
    # 兼容旧格式：DATA_SOURCE=<逗号列表>
    ds_line = next((ln for ln in lines if ln.startswith("DATA_SOURCE=")), None)
    if ds_line:
        for fpath in [s.strip() for s in ds_line.split("=", 1)[1].split(",") if s.strip()]:
            out.append(index_file(fpath, "DATA_SOURCE 全量索引", ""))
    else:
        out.append("未找到 SOURCE_MAP 段或 DATA_SOURCE 行")
    return "\n".join(out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: source_map.py <任务书文件>")
        sys.exit(1)
    print(source_map(pathlib.Path(sys.argv[1])))
