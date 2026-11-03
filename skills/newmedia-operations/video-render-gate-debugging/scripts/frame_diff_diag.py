#!/usr/bin/env python3
"""成片/素材帧差分诊断：客观定位"中间卡了/死帧/镜切"。
用法: python3 frame_diff_diag.py <视频路径> [开始秒] [结束秒] [步进秒=0.5]
输出: 每个相邻帧对的像素差异率, 标 [镜切]/[微变]/[静止死帧]。
铁律: 高差异(>25%)是正常动态, 只有差异骤降<5%才是静止死帧/卡顿根因。
不依赖 vision 模型, 纯 ffmpeg 抽帧 + 字节比对, 可兜底视觉接口不可用。
"""
import subprocess, os, sys

def frame_raw(path, t):
    out = f"/tmp/fdiff_{int(t*10)}.pgm"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", path, "-ss", str(t),
                    "-frames:v", "1", "-vf", "scale=64:64,format=gray", out], check=True)
    data = open(out, 'rb').read()
    idx = data.find(b'\n255\n') + 5
    return data[idx:idx + 64 * 64]

def main():
    path = sys.argv[1]
    t0 = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    t1 = float(sys.argv[3]) if len(sys.argv) > 3 else None
    step = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5
    # 无 t1 时用视频实际时长
    if t1 is None:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", path],
                           capture_output=True, text=True, check=True)
        t1 = float(r.stdout.strip())
    times = [round(t0 + i * step, 2) for i in range(int((t1 - t0) / step) + 1)]
    raws = {}
    for t in times:
        if t > t1:
            continue
        try:
            raws[t] = frame_raw(path, t)
        except Exception:
            raws[t] = None
    print(f"=== {os.path.basename(path)}   {t0}→{t1}s  差分析 ===")
    prev = None
    for t in times:
        if raws.get(t) is None:
            prev = None
            continue
        if prev is not None and raws.get(prev) is not None:
            a, b = raws[prev], raws[t]
            d = sum(1 for i in range(len(a)) if a[i] != b[i]) / len(a)
            if d > 0.25:
                tag = "镜切/跳动"
            elif d > 0.05:
                tag = "微变"
            else:
                tag = "!!! 静止死帧(卡顿根因)"
            print(f"  {prev:.1f}→{t:.1f}s : {d*100:5.1f}%  [{tag}]")
        prev = t

if __name__ == "__main__":
    main()
