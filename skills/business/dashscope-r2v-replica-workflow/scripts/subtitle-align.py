#!/usr/bin/env python3
"""
字幕时码对齐实际语音：silencedetect → 字数比例分配 → 生成 ASS
+ 幽灵字幕检测：检查每个shot的台词是否都被实际念出

用法:
  python3 subtitle-align.py <成片路径> <台词文件> <输出ASS路径> [noise_dB] [min_dur]

台词文件格式（每行一句，空行分隔shot）:
  喂你知道吗
  现在看漫剧也能赚钱了
  就是这个火龙漫剧
  
  不只是看剧能赚
  日常福利奖励多到领不完

空白行分隔的不同段 = 不同shot。
脚本会自动检测每个shot的语音段，按字数比例分配字幕时码。
同时检测幽灵字幕（字幕分配到静音段=台词没念）。

--check-phantom 模式：只检测幽灵字幕，不生成ASS
  python3 subtitle-align.py --check-phantom <成片路径> <台词文件> [shot边界文件]
"""

import subprocess, sys, re, json, os

def run_silencedetect(video_path, noise=-30, min_dur=0.15):
    """运行 ffmpeg silencedetect，返回静音段列表"""
    af = f"silencedetect=noise={noise}dB:d={min_dur}"
    cmd = ["ffmpeg", "-hide_banner", "-i", video_path, "-af", af, "-f", "null", "-"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    
    events = []
    for line in result.stderr.split('\n'):
        m = re.search(r'silence_start:\s*([\d.]+)', line)
        if m:
            events.append(('start', float(m.group(1))))
        m = re.search(r'silence_end:\s*([\d.]+)', line)
        if m:
            events.append(('end', float(m.group(1))))
    
    # 配对
    silences = []
    i = 0
    while i < len(events):
        if events[i][0] == 'start':
            s = events[i][1]
            if i+1 < len(events) and events[i+1][0] == 'end':
                e = events[i+1][1]
                silences.append((s, e))
                i += 2
            else:
                i += 1
        else:
            i += 1
    return silences

def get_speech_segments(video_path, noise=-30, min_dur=0.15):
    """从静音段推导语音段"""
    silences = run_silencedetect(video_path, noise, min_dur)
    
    # 获取音频时长
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", video_path],
        capture_output=True, text=True, timeout=15
    )
    d = json.loads(result.stdout)
    audio_dur = 0
    for s in d.get('streams', []):
        if s.get('codec_type') == 'audio':
            audio_dur = float(s.get('duration', 0))
            break
    
    # 推导语音段
    prev_end = 0
    speech_segs = []
    for s, e in silences:
        if s > prev_end + 0.01:
            speech_segs.append((prev_end, s))
        prev_end = e
    if prev_end < audio_dur:
        speech_segs.append((prev_end, audio_dur))
    
    return speech_segs

def check_phantom_subtitles(video_path, shots, shot_boundaries=None, noise=-30, min_dur=0.15):
    """
    检测幽灵字幕：台词分配到静音段=台词没被念出
    
    shot_boundaries: [(start, end), ...] 每个shot在成片中的全局时间范围
    如果不提供，按等分估算
    """
    speech_segs = get_speech_segments(video_path, noise, min_dur)
    
    print(f"检测到 {len(speech_segs)} 个语音段:")
    for i, (s, e) in enumerate(speech_segs):
        print(f"  语音段{i+1}: {s:.3f}-{e:.3f} ({e-s:.3f}s)")
    
    if not shot_boundaries:
        # 等分估算
        audio_dur = speech_segs[-1][1] if speech_segs else 40
        n_shots = len(shots)
        shot_boundaries = [(audio_dur * i / n_shots, audio_dur * (i+1) / n_shots) for i in range(n_shots)]
    
    phantom_lines = []
    
    for shot_idx, (shot_start, shot_end) in enumerate(shot_boundaries):
        shot_subs = shots[shot_idx]
        # 该shot的语音段
        shot_speech = [(s, e) for s, e in speech_segs if s < shot_end and e > shot_start]
        if not shot_speech:
            print(f"\n⚠️  Shot{shot_idx+1} ({shot_start:.1f}-{shot_end:.1f}s): 完全没有语音！")
            for sub in shot_subs:
                phantom_lines.append((shot_idx, sub, "shot无语音"))
            continue
        
        total_speech = sum(e - s for s, e in shot_speech)
        shot_dur = shot_end - shot_start
        silence_ratio = 1 - (total_speech / shot_dur) if shot_dur > 0 else 1
        
        print(f"\nShot{shot_idx+1} ({shot_start:.1f}-{shot_end:.1f}s): {len(shot_subs)}句, 语音{total_speech:.2f}s/{shot_dur:.2f}s")
        
        # 检查尾部静音
        last_speech_end = max(e for s, e in shot_speech)
        tail_silence = shot_end - last_speech_end
        if tail_silence > 1.0:
            print(f"  ⚠️  尾部静音 {tail_silence:.2f}s — 可能有台词没念")
            # 估算多少句台词落在静音区
            # 按字数比例算每句时长
            total_chars = sum(len(s.replace(' ','')) for s in shot_subs)
            cursor = shot_start
            for sub in shot_subs:
                chars = len(sub.replace(' ', ''))
                ratio = chars / total_chars if total_chars > 0 else 0
                dur = ratio * total_speech
                sub_end = cursor + dur
                if sub_end > last_speech_end and cursor < last_speech_end:
                    # 这句跨越了语音结束点
                    print(f"  ⚠️  \"{sub}\" 可能没念完 (分配{cursor:.2f}-{sub_end:.2f}s, 语音结束{last_speech_end:.2f}s)")
                if cursor > last_speech_end:
                    print(f"  ❌ \"{sub}\" 完全在静音区 (分配{cursor:.2f}-{sub_end:.2f}s) — 没念!")
                    phantom_lines.append((shot_idx, sub, f"完全在静音区({cursor:.2f}-{sub_end:.2f}s)"))
                cursor = sub_end
    
    if phantom_lines:
        print(f"\n{'='*50}")
        print(f"发现 {len(phantom_lines)} 条幽灵字幕:")
        for shot_idx, sub, reason in phantom_lines:
            print(f"  Shot{shot_idx+1}: \"{sub}\" — {reason}")
        print(f"\n修复方案:")
        print(f"  1. 重新生成该shot，补全prompt台词")
        print(f"  2. 砍掉幽灵字幕句，成片到实际语音结束处收尾")
    else:
        print(f"\n✅ 未检测到幽灵字幕")
    
    return phantom_lines

def parse_script(file_path):
    """解析台词文件，返回 shot 分组列表"""
    with open(file_path, 'r') as f:
        content = f.read()
    
    shots = []
    for block in content.split('\n\n'):
        lines = [l.strip() for l in block.strip().split('\n') if l.strip()]
        if lines:
            shots.append(lines)
    return shots

def fmt_time(t):
    """格式化时间为 ASS 格式 H:MM:SS.cc"""
    m = int(t // 60)
    s = t % 60
    h = int(m // 60)
    m = m % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def generate_aligned_ass(shots, speech_segs, output_path, video_width=720, video_height=1280):
    """生成对齐的 ASS 字幕文件"""
    
    # 每个 shot 的句子数
    total_lines = sum(len(s) for s in shots)
    
    # 按 shot 分配语音段（简单方案：连续分配）
    # 如果有 N 个 shot 和 M 个语音段，需要人工指定映射
    # 这里用简单方案：每个 shot 取总时长的 1/N
    # 更精确的方案需要人工指定 shot 边界
    
    # 简化：所有句子按字数比例分配到全部语音时长
    all_lines = []
    for shot in shots:
        all_lines.extend(shot)
    
    total_chars = sum(len(line.replace(' ', '')) for line in all_lines)
    total_speech = sum(e - s for s, e in speech_segs)
    
    # 生成字幕
    subs = []
    cursor = 0  # 语音段内游标
    for line in all_lines:
        chars = len(line.replace(' ', ''))
        ratio = chars / total_chars
        duration = ratio * total_speech
        
        # 找到 cursor 对应的实际时间
        actual_start = None
        actual_end = None
        elapsed = 0
        
        for seg_start, seg_end in speech_segs:
            seg_dur = seg_end - seg_start
            if actual_start is None and elapsed + seg_dur > cursor:
                actual_start = seg_start + (cursor - elapsed)
            if actual_start is not None and elapsed + seg_dur >= cursor + duration:
                actual_end = seg_start + (cursor + duration - elapsed)
                break
            elapsed += seg_dur
        
        if actual_end is None:
            actual_end = speech_segs[-1][1] if speech_segs else cursor + duration
        
        subs.append({'start': actual_start, 'end': actual_end, 'text': line})
        cursor += duration
    
    # 写 ASS
    header = f"""[Script Info]
Title: Auto-aligned subtitles (silencedetect)
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,WenQuanYi Zen Hei,56,&H00FFFFFF,&H00FFFFFF,&H00000000,&H8C000000,-1,0,0,0,100,100,0,0,1,3,2,2,60,60,380,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""
    
    lines_out = [header]
    for sub in subs:
        lines_out.append(f"Dialogue: 1,{fmt_time(sub['start'])},{fmt_time(sub['end'])},Main,,0,0,0,,{sub['text']}")
    
    ass_content = '\n'.join(lines_out) + '\n'
    with open(output_path, 'w') as f:
        f.write(ass_content)
    
    print(f"生成 {len(subs)} 句字幕 → {output_path}")
    for i, sub in enumerate(subs):
        print(f"  {i+1:2d}. [{fmt_time(sub['start'])}→{fmt_time(sub['end'])}] {sub['text']}")
    
    return subs

def main():
    if len(sys.argv) < 4:
        print(f"用法: {sys.argv[0]} <成片路径> <台词文件> <输出ASS路径> [noise_dB] [min_dur]")
        print(f"  台词文件: 每行一句，空行分隔shot")
        print(f"")
        print(f"幽灵字幕检测模式:")
        print(f"  {sys.argv[0]} --check-phantom <成片路径> <台词文件> [shot边界文件]")
        print(f"  shot边界文件: 每行一个shot的 起始秒,结束秒")
        sys.exit(1)
    
    # 幽灵字幕检测模式
    if sys.argv[1] == '--check-phantom':
        video_path = sys.argv[2]
        script_path = sys.argv[3]
        shots = parse_script(script_path)
        
        shot_boundaries = None
        if len(sys.argv) > 4:
            # 读取shot边界
            with open(sys.argv[4]) as f:
                shot_boundaries = []
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) == 2:
                        shot_boundaries.append((float(parts[0]), float(parts[1])))
        
        check_phantom_subtitles(video_path, shots, shot_boundaries)
        return
    
    video_path = sys.argv[1]
    script_path = sys.argv[2]
    output_path = sys.argv[3]
    noise = int(sys.argv[4]) if len(sys.argv) > 4 else -30
    min_dur = float(sys.argv[5]) if len(sys.argv) > 5 else 0.15
    
    print(f"检测语音段: {video_path} (noise={noise}dB, min_dur={min_dur}s)")
    speech_segs = get_speech_segments(video_path, noise, min_dur)
    print(f"检测到 {len(speech_segs)} 个语音段:")
    for i, (s, e) in enumerate(speech_segs):
        print(f"  语音段{i+1}: {s:.3f}-{e:.3f} ({e-s:.3f}s)")
    
    shots = parse_script(script_path)
    print(f"\n台词: {sum(len(s) for s in shots)} 句, {len(shots)} 个shot")
    
    # 先检测幽灵字幕
    print(f"\n=== 幽灵字幕检测 ===")
    check_phantom_subtitles(video_path, shots)
    
    # 再生成ASS
    print(f"\n=== 生成对齐ASS ===")
    generate_aligned_ass(shots, speech_segs, output_path)

if __name__ == '__main__':
    main()
