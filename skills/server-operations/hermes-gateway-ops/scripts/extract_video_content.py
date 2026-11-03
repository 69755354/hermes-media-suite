#!/usr/bin/env python3
"""
视频内容提取工具：视频 → 文字稿
用法: python3 extract_video_content.py <视频路径> [模型大小:tiny/base/small/medium]
输出: 时间戳+台词 文字稿（stdout），保存 .txt 同目录

依赖: pip install faster-whisper（装进 Hermes venv）
模型下载坑（2026-08-05 实测）:
  - HF 直连被墙: HF_ENDPOINT=https://hf-mirror.com
  - 镜像走 xet 报 401: HF_HUB_DISABLE_XET=1
  - 首次下载后脚本自动优先本地缓存 ~/.cache/huggingface/faster-whisper-<size>
"""
import sys, os, time, subprocess, tempfile

def extract_audio(video_path, wav_path):
    """ffmpeg 抽音频为 16k 单声道 wav"""
    r = subprocess.run(['ffmpeg', '-y', '-i', video_path, '-ar', '16000', '-ac', '1',
                        '-c:a', 'pcm_s16le', wav_path],
                       capture_output=True, text=True, timeout=120)
    return r.returncode == 0 and os.path.exists(wav_path)

def main():
    if len(sys.argv) < 2:
        print("用法: python3 extract_video_content.py <视频路径> [模型:tiny/base/small]")
        sys.exit(1)
    video = sys.argv[1]
    model_size = sys.argv[2] if len(sys.argv) > 2 else 'small'
    if not os.path.exists(video):
        print(f"❌ 视频不存在: {video}")
        sys.exit(1)

    wav = tempfile.mktemp(suffix='.wav')
    print(f"🎵 抽音频... ({os.path.basename(video)})")
    t0 = time.time()
    if not extract_audio(video, wav):
        print("❌ ffmpeg 抽音频失败")
        sys.exit(1)
    print(f"   ✓ 完成 ({time.time()-t0:.1f}s)")

    print(f"🧠 加载 faster-whisper 模型 [{model_size}]...")
    from faster_whisper import WhisperModel
    t0 = time.time()
    local_dir = os.path.expanduser(f"~/.cache/huggingface/faster-whisper-{model_size}")
    if os.path.isdir(local_dir):
        model = WhisperModel(local_dir, device="cpu", compute_type="int8")
    else:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
    print(f"   ✓ 模型就绪 ({time.time()-t0:.1f}s)")

    print("📝 转写中...")
    t0 = time.time()
    segments, info = model.transcribe(wav, language="zh", beam_size=5)
    lines = []
    for seg in segments:
        ts = f"[{int(seg.start//60):02d}:{int(seg.start%60):02d}]"
        lines.append(f"{ts} {seg.text.strip()}")
        print(f"  {ts} {seg.text.strip()}")
    print(f"   ✓ 转写完成 ({time.time()-t0:.1f}s)")

    out = os.path.splitext(video)[0] + '_transcript.txt'
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"\n✅ 完成！文字稿: {out}")
    os.unlink(wav)

if __name__ == '__main__':
    main()
