#!/usr/bin/env python3
"""火龙漫剧 风险提示小字行数校验（横版/竖版通用）

用法:
    python3 check_risk_lines.py <mp4> [<mp4> ...]
    python3 check_risk_lines.py --dir <目录>

判定:
    5 行 = PASS（三类一律 5 句，第 1 行＝「新人看剧5分钟后满0.3元就能提现」）
    4 行 = MISSING（缺第 1 行，需补行）
    >=6 行 = DUP（重复叠印，必须还原，不许再叠）

要点（2026-10-09 事故教训）:
    * 不要用“亮度比值”判有没有第 1 行——参考片内容会误判（剧情-04/05、免费-26/28 都曾被误判为“缺”，实际已有，结果叠成 6 行）。
    * 只认行数。
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image


def row_count(mp4, ss=3.0):
    """返回 (行数, 宽, 高)。横版取底部左侧，竖版取底部左侧。"""
    tmp = os.path.join(tempfile.gettempdir(), "_riskline_probe.png")
    subprocess.run(["ffmpeg", "-v", "error", "-ss", str(ss), "-i", mp4,
                    "-frames:v", "1", tmp, "-y"], check=True)
    a = np.array(Image.open(tmp).convert("L"))
    h, w = a.shape
    if w >= h:  # 横版 1280x720
        reg = a[560:715, 8:480]
    else:       # 竖版 720x1280
        reg = a[1130:1280, 2:350]
    rs = (reg > 175).sum(axis=1)
    thr = max(4, int(rs.max() * 0.25))
    on = rs > thr
    rows, prev, start = 0, False, 0
    for i, v in enumerate(on):
        if v and not prev:
            start = i
        if not v and prev and i - start >= 6:
            rows += 1
        prev = v
    if prev and len(on) - start >= 6:
        rows += 1
    return rows, w, h


def verdict(rows):
    if rows == 5:
        return "PASS"
    if rows < 5:
        return "MISSING"
    return "DUP"


def main(argv):
    files = []
    if len(argv) >= 2 and argv[0] == "--dir":
        for d, _, fs in os.walk(argv[1]):
            files += [os.path.join(d, f) for f in sorted(fs)
                      if f.endswith((".mp4", ".mov"))]
    else:
        files = list(argv)
    if not files:
        print("用法: check_risk_lines.py <mp4>... | --dir <目录>")
        return 2
    bad = 0
    for p in files:
        rows, w, h = row_count(p)
        v = verdict(rows)
        if v != "PASS":
            bad += 1
        print(f"{v:8s} 行数={rows}  {w}x{h}  {os.path.basename(p)}")
    print(f"\n合计 {len(files)} 条，不合格 {bad} 条")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
