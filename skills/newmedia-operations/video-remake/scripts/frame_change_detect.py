#!/usr/bin/env python3
"""视频全帧变化检测：找出画面切换候选点（素材/场景/人物切换），避免间隔抽帧漏素材。

注意（2026-08-24 口径定案）：本脚本只找「画面变化」，找出的切换点必须经 vision
确认性质——人物/景别硬切才算镜界；UI 层切换（App 页面出现/消失）不算镜界，
只作段内后期贴片时点。直接拿画面切换数当分镜数 = 旧错误口径。
"""
用法: python3 frame_change_detect.py <视频.mp4> <输出目录>
"""
import subprocess, sys, os, tempfile
from PIL import Image
import numpy as np

def main():
    video = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else "/tmp/frame_change"
    os.makedirs(outdir, exist_ok=True)

    # 每 0.5 秒抽 1 帧（60fps 原片够密；需更密改 fps=4）
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", video,
         "-vf", "fps=2", f"{outdir}/f_%03d.jpg"],
        check=True)
    files = sorted(f for f in os.listdir(outdir) if f.endswith(".jpg"))
    print(f"共 {len(files)} 帧")

    # 相邻帧灰度差异，找切换点（diff>15 视为画面切换）
    prev = None
    changes = []
    for f in files:
        im = Image.open(os.path.join(outdir, f)).convert("L").resize((72, 128))
        arr = np.array(im, dtype=float)
        if prev is not None:
            diff = np.abs(arr - prev).mean()
            if diff > 15:
                changes.append((f, round(diff, 1)))
        prev = arr
    print(f"切换点 {len(changes)} 个:")
    for f, d in changes:
        print(f"  {f}: diff={d}")
    print("提示: 切换点帧=素材/场景/人物变化处，拼图逐批看覆盖全部素材")

if __name__ == "__main__":
    main()
