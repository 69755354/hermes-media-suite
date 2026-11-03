#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""段间切点 / 片尾 物理闸（2026-09-29 立，FAIL 直接拒绝交付）。

判据：
  A) 段间切点不得落在词内部（留 0.12s 容差，抵 ASR 对齐漂移）——切在词里＝「话没说完就换段」。
     修法：把该段 LEN 用到源素材结尾（切点落句末），禁止靠字幕遮盖。
  B) 尾空（末段有效语音到片尾）≥ 0.40s，用音频能量实测（不靠 ASR 末词时间，ASR 会漂）。
  C) WARN：切点前 40ms 音频能量 >0.10 → 切点处语音是硬断的（可能是源片段自身就截断收尾），
     这种只能重生成该段或把切点前移到上一句末。

尾部满帧盖素材（App 录屏/其它片）另需目视：抽片尾最后 3 帧，最后一帧必须是本段场景/人物。

用法：
  python3 huolong_seam_word_gate.py <成片.mp4> --seams 0,9.2,17.527 [--model medium] [--min-tail 0.40]
退出码：0=PASS（可含 WARN），1=FAIL（不许交付）。
"""
import argparse, os, subprocess, sys

ASR_PY = "/home/ubuntu/asrvenv/bin/python"
FF = "/home/ubuntu/workflow/scripts/ffmpeg-static-bin"
SEAM_TOL = 0.12


def ensure_asr_env():
    try:
        import faster_whisper  # noqa: F401
        import numpy  # noqa: F401
        return
    except Exception:
        pass
    if os.path.exists(ASR_PY) and os.path.realpath(sys.executable) != os.path.realpath(ASR_PY):
        raise SystemExit(subprocess.call([ASR_PY, os.path.abspath(__file__)] + sys.argv[1:]))
    raise SystemExit("[BLOCKED] 找不到 faster_whisper / numpy，无法做词级核对")


def pcm(path):
    import numpy as np
    cmd = [FF, "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", "16000", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, dtype=np.float32)


def rms_at(a, t, win=640):
    import numpy as np
    n = len(a)
    i = int(t * 16000)
    seg = a[max(0, i - win):min(n, i)]
    if len(seg) == 0:
        return 0.0
    return float(np.sqrt((seg.astype('float64') ** 2).mean()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--seams", required=True, help="段间切点（成片秒），逗号分隔；第 0 个可为 0")
    ap.add_argument("--model", default="medium")
    ap.add_argument("--min-tail", type=float, default=0.40)
    ap.add_argument("--head-threshold", type=float, default=0.10)
    a = ap.parse_args()
    ensure_asr_env()
    import numpy as np
    from faster_whisper import WhisperModel

    seams = [float(x) for x in a.seams.split(",") if x.strip() != ""]
    media_seams = [s for s in seams if s > 0.05]

    dur = None
    try:
        out = subprocess.run(["/usr/bin/ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", a.video], capture_output=True, text=True)
        dur = float(out.stdout.strip())
    except Exception:
        pass

    pcm_ = pcm(a.video)
    win = 640
    nw = len(pcm_) // win
    env = [float(np.sqrt((pcm_[k * win:(k + 1) * win].astype('float64') ** 2).mean())) for k in range(nw)]

    m = WhisperModel(a.model, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(a.video, language="zh", word_timestamps=True, vad_filter=False)
    words = [(w.start, w.end, w.word) for s in segs for w in (s.words or [])]
    if not words:
        print("FAIL 没识别到任何词，无法核对")
        return 1

    bad = 0
    for sm in media_seams:
        hit = [(round(x, 2), round(y, 2), t) for x, y, t in words if x + SEAM_TOL < sm < y - SEAM_TOL]
        if hit:
            print("FAIL 切点 %.3f 落在词内部（>%.2fs）：%s" % (sm, SEAM_TOL, hit))
            bad += len(hit)
        else:
            print("PASS 切点 %.3f 在词外（容差 %.2fs）" % (sm, SEAM_TOL))
        e = rms_at(pcm_, sm)
        if e > a.head_threshold:
            print("WARN 切点 %.3f 前 40ms 能量 %.3f > %.2f：语音在这里是硬断的，若源片段自身就是截断收尾，只能重生成该段"
                  % (sm, e, a.head_threshold))

    # 尾空：找最后一个能量 >0.10 的 40ms 窗口
    voiced = [k for k, v in enumerate(env) if v > 0.10]
    if not voiced:
        print("FAIL 全片没有可判定的语音能量窗口")
        return 1
    last_t = (voiced[-1] + 1) * win / 16000.0
    tail = (dur - last_t) if dur else None
    if tail is None:
        print("WARN 取不到片长；末次有效语音 %.2fs" % last_t)
    elif tail < a.min_tail:
        print("FAIL 尾空 %.2fs < %.2fs（末次语音 %.2f / 片长 %.2f）" % (tail, a.min_tail, last_t, dur))
        bad += 1
    else:
        print("PASS 尾空 %.2fs（末次语音 %.2f / 片长 %.2f）" % (tail, last_t, dur))

    print("结论：" + ("FAIL %d 处" % bad if bad else "PASS 段间切点在词外 + 尾空达标（WARN 须人工判）"))
    print("提醒：片尾是否被满帧盖素材，须另抽最后 3 帧目视——最后一帧必须是本段场景/人物。")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
