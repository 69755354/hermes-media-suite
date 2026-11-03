#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""火龙漫剧六类返工的物理自检（2026-09-29 建立）。

背景：2026-09-29 火龙链路连续返工，用户当场点出六件事——① 开工前没有单独的分镜表
② 段与段之间不连贯（每段重新开场 + 段间淡入淡出）③ 台词自问自答/问句接问句没人答
④ 跨段画面重复（同一构图开局）⑤ 同音占位错字上了字幕（「一级」应为「一集」）
⑥ 实念率不足（43 字只念出 29 个）。
这六条以前**只写在 skill 正文里**，没有任何代码能判，所以每次都靠返工才发现。本脚本把
这六条变成可跑的判据。

定位：**自检工具，不是闸**。不在 gate_config.yaml 注册、不写 guard/、不产获批哈希。
退出码仅供人和上层脚本参考：0=全过，1=有 FAIL，2=用法/环境问题。
skill 正文只准指向本脚本，不准再抄一份数字——同一个数字抄多份然后各自漂移，是上一轮
规则治理（projects/rule_governance_20260929/analysis.md）认定的根因。

用法：
  python3 huolong_six_checks.py storyboard <项目目录>
  python3 huolong_six_checks.py subtitle <字幕.ass> [--allow 一级]
  python3 huolong_six_checks.py readrate <段视频.mp4> --text "本段台词（字幕原字）"
  python3 huolong_six_checks.py crossdup <成片.mp4> --seams 0,8.92,19.54
  python3 huolong_six_checks.py seam <成片.mp4> [--seams 0,8.92,19.54]
  python3 huolong_six_checks.py all <项目目录> [--final 成片.mp4] [--seams ...]

实念率需要 faster_whisper：/home/ubuntu/.hermes/hermes-agent/venv/bin/python 有装。
"""
import argparse
import glob
import itertools
import os
import re
import subprocess
import sys

FF = "/home/ubuntu/workflow/scripts/ffmpeg-static-bin"
if not os.path.exists(FF):
    FF = "ffmpeg"
FFPROBE = "/usr/bin/ffprobe"

# 字幕/交付文本里的禁字表。
# 前四个是**提示词侧同音占位**（唯一来源：references/pronunciation-pitfalls-20260922.md 第三节），
# 只许出现在提示词里；出现在字幕里就是穿帮。
# 「一级」不是占位字——它是模型把「一集」念错的结果（第一节表格第 2 列）。2026-09-29 有人把
# 第 2 列当成建议写法写进了提示词，字幕跟着出现「一级」。它在提示词和字幕里**都**不该出现，
# 「一集」的正解是改话术（「从头看到尾」「整部看完」）。
HOMOPHONE_PLACEHOLDERS = {
    "提线": "提现",
    "千到": "签到",
    "悬宜": "悬疑",
    "大结菊": "大结局",
    "一级": "一集（注意：一级不是占位字，是念错的结果，提示词里也不该写）",
}
RESULTS = []

# 景别/机位/焦距词（④ 段首构图判据用）
FRAMING_RE = re.compile(
    r"(全景|中景|近景|特写|远景|过肩|侧面|正面|背面|俯拍|仰拍|平视|低角度|高角度|\d+\s*mm)")
# 机位/焦距词：只写景别不写这些 = 构图没定死
ANGLE_RE = re.compile(r"(平视|俯拍|仰拍|低角度|高角度|过肩|侧面|正面|背面|\d+\s*mm)")


def rec(ok, name, msg):
    RESULTS.append((ok, name, msg))
    print("%s %s：%s" % ("PASS" if ok else "FAIL", name, msg), flush=True)
    return ok


def _dur(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


# ---------------------------------------------------------------- ① 分镜表前置
SB_GLOBS = ["spec/*分镜*.md", "artifacts/creative/*分镜*.md", "staging/*分镜*.md",
            "output/**/*分镜*.md", "*分镜*.md", "A_STORYBOARD*.md",
            "output/**/A_STORYBOARD*.md",
            # 英文名分镜表（历史正确样例就是 storyboard_*.md 命名，别漏）
            "spec/*storyboard*.md", "artifacts/creative/*storyboard*.md",
            "staging/*storyboard*.md", "output/**/*storyboard*.md", "*storyboard*.md"]
GEN_GLOBS = ["work/*.py", "work/manifest*.json"]


def find_storyboard(proj):
    hits = []
    for g in SB_GLOBS:
        hits += glob.glob(os.path.join(proj, g), recursive=True)
    hits = [h for h in sorted(set(hits)) if os.path.isfile(h)]
    return max(hits, key=os.path.getmtime) if hits else None


# ------------------------------------------------ ⑥ 提示词侧：段首/段尾静默口径（生成前唯一能查的一关）
DEAD_PHRASES = ["开头先停顿半秒", "先停顿半秒", "开头先停顿", "开头停顿半秒", "停顿半秒，然后",
                "开口即说", "段首不留静默", "段首不要留静默", "第0秒开口", "一开场就说",
                "保持静默", "保持自然静默", "静默约", "留白", "说完后保持", "说完以后保持", "尾空",
                "语速适中", "语速偏快", "语速快", "语速自然", "语速略慢", "吐字清晰，语速"]
TAIL_HINTS = ["保持", "静默", "气口", "不要补话", "留白"]

def check_prompt_silence(proj):
    """生成前扫 spec/prompt_*.md：
    ① 不许出现已废句式「开头先停顿半秒」——它命令模型段首先空 1-2 秒，
       与硬闸「段首静默 ≤0.10s、第 0 秒开口」直接矛盾；实测代价＝模型赶进度吞句（实念率 84%）。
    ② 必须写出段尾留白（「最后一句说完后保持静默约 0.8 秒」）——只删①不加②会走向另一极端：
       模型一路念到末帧不留气口，接缝处照样被 seam 闸拦。
    """
    files = sorted(glob.glob(os.path.join(proj, "spec", "prompt*.md")) +
                   glob.glob(os.path.join(proj, "**", "prompt*.md"), recursive=True))
    files = sorted(set(f for f in files if os.path.isfile(f)))
    if not files:
        return
    dead_hits, miss_tail = [], []
    for f in files:
        t = open(f, encoding="utf-8", errors="ignore").read()
        for ph in DEAD_PHRASES:
            if ph in t:
                (miss_tail if ph in ("保持静默", "保持自然静默", "静默约", "留白", "说完后保持", "说完以后保持", "尾空") else dead_hits).append("%s: %s" % (os.path.basename(f), ph))
    rec(not dead_hits, "⑥提示词不写段首/段尾/语速指令（全部交给模型与 duration）",
        "干净" if not dead_hits else
        "命中 %d 处：%s → 段首什么都不要写，模型自然会从第 0 秒开口；写了反而制造静默或赶句"
        % (len(dead_hits), "、".join(dead_hits[:6])))
    # ⑦ 音色与逐句情绪必须写全（客户 2026-10-01：「情绪描写那些东西，你还是音色，你还是要描写」）
    no_timbre = []
    for f in files:
        t = open(f, encoding="utf-8", errors="ignore").read()
        if "配音：" not in t or "声" not in t:
            no_timbre.append("%s: 缺音色描述" % os.path.basename(f))
        elif "逐句情绪" not in t and "情绪" not in t:
            no_timbre.append("%s: 缺逐句情绪" % os.path.basename(f))
    rec(not no_timbre, "⑦音色+逐句情绪写全（必须写）",
        "各段音色描述、逐句情绪标注齐全" if not no_timbre else
        "缺失：%s → 音色（如「偏软、带点疲惫的年轻女声」）和逐句情绪（每句一个情绪词）都必须写，"
        "删的只是语速/静默，不是这两样" % "、".join(no_timbre[:6]))
    rec(not miss_tail, "⑥提示词无段尾/静默类指令",
        "干净" if not miss_tail else
        "命中：%s → 段首段尾一个字都不要写（客户 2026-10-01），静默交给模型自然发挥；尾空在合成端补"
        % "、".join(miss_tail[:6]))


def check_storyboard(proj):
    sb = find_storyboard(proj)
    if not sb:
        return rec(False, "①分镜表存在",
                   "项目里找不到分镜表（查过 %s）→ 不许写提示词、不许提交生成"
                   % "、".join(SB_GLOBS))
    rec(True, "①分镜表存在", sb)
    text = open(sb, encoding="utf-8", errors="ignore").read()

    for key in ("段间衔接表", "台词分配表"):
        rec(key in text, "①" + key,
            "有" if key in text else "缺这张表——多段/双人片缺它就会段段重新开场、自问自答")
    cols = [ln for ln in text.splitlines() if ln.count("|") >= 8]
    rec(bool(cols), "①8列分镜表",
        "找到 %d 行 ≥8 列表格" % len(cols) if cols else
        "没有 ≥8 列的表格行（时段｜说话人｜台词｜画面动作｜景别·机位·运镜｜情绪微动作｜参考图｜连续性·负面）")

    # 分镜表必须**先于**生成脚本存在：mtime 晚于生成脚本 = 事后回填 = 等于没有
    sb_m = os.path.getmtime(sb)
    gens = []
    for g in GEN_GLOBS:
        gens += glob.glob(os.path.join(proj, g))
    gens = [g for g in gens if os.path.isfile(g)]
    if gens:
        first = min(gens, key=os.path.getmtime)
        rel = os.path.relpath(first, proj)
        if sb_m > os.path.getmtime(first) + 1:
            rec(False, "①分镜表先于生成",
                "分镜表 mtime 晚于生成脚本 %s → 事后回填，不算前置分镜表" % rel)
        else:
            rec(True, "①分镜表先于生成", "分镜表早于 %s" % rel)

    check_dialogue_table(text)
    check_transition_words(text)
    check_framing(text)
    check_prompt_silence(proj)
    return sb


# ------------------------------------------------- ③ 一问一答 / 不许自问自答
def check_dialogue_table(text):
    rows = []
    for ln in text.splitlines():
        if ln.count("|") < 5 or re.match(r"^\s*\|[\s:|-]+\|\s*$", ln):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) >= 5 and re.match(r"^\d+$", cells[0]) and re.search(r"段\s*\d", cells[1]):
            rows.append(cells)  # 序｜段｜说话人｜台词｜是问是答
    if not rows:
        return rec(False, "③台词分配表可解析",
                   "解析不出行（需 5 列：序｜段｜说话人｜台词｜是问是答，序号列为纯数字）")
    rec(True, "③台词分配表可解析", "%d 行" % len(rows))

    bad = []
    notes = []
    run = 1
    for i, r in enumerate(rows):
        spk, line, kind = r[2], r[3], (r[4] if len(r) > 4 else "")
        prev = rows[i - 1] if i else None
        if prev is not None and prev[2] == spk:
            run += 1   # 句数不限（用户 2026-09-30 定）：只统计，不判失败
        else:
            run = 1
        if prev is not None:
            prev_q = prev[3].rstrip().endswith(("？", "?")) or (len(prev) > 4 and prev[4] == "问")
            this_q = line.rstrip().endswith(("？", "?")) or kind == "问"
            if prev_q and prev[2] == spk:
                bad.append("第%s行 自问自答（%s 问完自己接）" % (r[0], spk))
            if prev_q and this_q:
                bad.append("第%s行 问句接问句，上一问没人答" % r[0])
            if prev[1] != r[1] and prev[2] == spk:
                # 段首换不换人看语言逻辑（用户 2026-10-01 定）：只提示，不判失败
                notes.append("第%s行 段首沿用同一个人（%s 收尾又在 %s 开口）—— 看语言逻辑，不强制换人" % (r[0], prev[1], r[1]))
    msg = "；".join(bad) if bad else "无自问自答、无问句接问句（句数不限，段首换人看逻辑不强制）"
    if notes:
        msg += " ／ 提示：" + "；".join(notes)
    return rec(not bad, "③一问一答", msg)


# ------------------------------------------------------ ② 段间接法（写法层）
def check_transition_words(text):
    bad = re.findall(r"(淡入淡出|叠化|xfade|acrossfade|黑场过渡)", text, re.I)
    bad = [b for b in bad if b]
    # 「禁用淡入淡出」这类否定句不算违规
    neg = len(re.findall(r"(禁用|禁止|不用|不许|不要|不|没有|无)\s*(淡入淡出|叠化|黑场过渡)", text))
    return rec(len(bad) <= neg, "②段间接法写法",
               "分镜表里出现 %s ——同场多段对话一律硬切（剪段尾冻结帧 + concat）" % sorted(set(bad))
               if len(bad) > neg else "未出现正向的淡入淡出/叠化/黑场过渡")


# ------------------------------------------------------ ⑤ 字幕同音占位扫描
def check_subtitle(ass_path, allow=()):
    if not os.path.isfile(ass_path):
        return rec(False, "⑤字幕文件", "找不到 %s" % ass_path)
    text = open(ass_path, encoding="utf-8", errors="ignore").read()
    lines = [ln.split(",,", 1)[-1] for ln in text.splitlines() if ln.startswith("Dialogue:")]
    body = "\n".join(lines) or text
    hits = {w: o for w, o in HOMOPHONE_PLACEHOLDERS.items() if w in body and w not in allow}
    ok = rec(not hits, "⑤字幕无同音占位（%s）" % os.path.basename(ass_path),
             "命中 %s ——提示词占位字漏进字幕；字幕与交付文本必须用原字"
             % "、".join("%s→应为%s" % (w, o) for w, o in hits.items())
             if hits else "%d 条字幕未命中占位黑名单" % len(lines))
    trad = sorted(set(re.findall(r"[劇賺劃這個們來對現錢時間興擺]", body)))
    if trad:
        rec(False, "⑤字幕已转简体", "残留繁体字 %s（whisper 中文默认出繁体，必须强制繁→简）" % trad)
    return ok


# ------------------------------------------------------------- ⑥ 实念率
def check_readrate(video, text, floor=0.95, ceil=1.05):
    expect = len([c for c in text if "一" <= c <= "鿿" or c.isdigit()])
    if not expect:
        return rec(False, "⑥实念率", "台词里数不出汉字/数字")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return rec(False, "⑥实念率",
                   "本解释器没装 faster_whisper，换 /home/ubuntu/.hermes/hermes-agent/venv/bin/python")
    wav = "/tmp/_hl_rr_%d.wav" % os.getpid()
    subprocess.run([FF, "-y", "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", "16000", wav],
                   check=False)
    mdl = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=3)
    it, _ = mdl.transcribe(wav, language="zh", vad_filter=False, beam_size=5,
                           word_timestamps=True)
    got = 0
    for sg in it:
        for w in (sg.words or []):
            if re.sub(r"[^一-鿿0-9A-Za-z]", "", w.word):
                got += 1
    if os.path.exists(wav):
        os.remove(wav)
    rate = got / float(expect)
    if rate > ceil:
        return rec(False, "⑥实念率",
                   "%.0f%%（脚本%d字/ASR%d词）> %.0f%% = 测量不可信，去 BGM 用底片音轨重测，不许当合格"
                   % (rate * 100, expect, got, ceil * 100))
    return rec(rate >= floor, "⑥实念率",
               "%.0f%%（脚本%d字/ASR%d词，合格线 %.0f%%）%s"
               % (rate * 100, expect, got, floor * 100,
                  "" if rate >= floor else " → 重生成补齐；禁止靠删字幕掩盖"))


# --------------------------------------------- ④ 跨段构图重复 / ② 接缝定格
def _frame(video, t, size=(180, 320)):
    import cv2
    import numpy as np
    png = "/tmp/_hl_f_%d.png" % os.getpid()
    subprocess.run([FF, "-y", "-v", "error", "-ss", "%.3f" % t, "-i", video,
                    "-frames:v", "1", png], check=False)
    img = cv2.imread(png, cv2.IMREAD_GRAYSCALE)
    if os.path.exists(png):
        os.remove(png)
    if img is None:
        return None
    return cv2.resize(img, size).astype(np.float32) / 255.0


def _mse(a, b):
    import numpy as np
    return float(np.mean((a - b) ** 2)) * 100.0


def check_framing(text):
    """④ 文本层（省钱的那一道）：段首不许互相重复开局，建立镜头只许段 1 有。

    这道比像素层可靠——「每段同一构图开局」是提示词里就写重了，出片前就能判，不用先烧钱。

    判据是「景别·机位·焦距 + 画面主体」整体不重复，不是光看景别词：
    正反打（段2 拍 A、段3 拍 B，都是「近景·平视·50mm」）是标准手法，也是 ② 要求的
    「延续上一段收尾景别」的自然结果，不该判违规；真正的 ④ 是**主体和构图都一样**
    （2026-09-29 实锤 manifest_dapaidang.json：三段全是「两人同框·近景/中景」，还没写机位焦距）。
    """
    seg_first = []
    cur = None
    for ln in text.splitlines():
        m = re.match(r"^#+\s*段\s*(\d+)", ln.strip())
        if m:
            cur = m.group(1)
            continue
        if cur is None or ln.count("|") < 6:
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if not re.match(r"^[\d.]+\s*[-–]\s*[\d.]+$", cells[0]):
            continue
        if any(c == cur for c, _, _ in seg_first):
            continue
        # 取「景别·机位·运镜」那一列：按框架词命中数打分挑最高的一列。
        # 不能用「第一个含『景』字的单元格」——画面动作列常写「延续上一段收尾景别」，
        # 会把真正的景别列挡掉，导致「没写机位/焦距」的假报（2026-09-29 v4 实测踩到）。
        shot = max(cells, key=lambda c: len(FRAMING_RE.findall(c)))
        if not FRAMING_RE.search(shot):
            shot = ""
        # 画面主体：双人同框算一类，单人按说话人分类（说话人取「说话人/台词」列冒号前）
        if re.search(r"两人|双人|同框|并排|合影", shot + cells[1]):
            subj = "双人同框"
        else:
            spk = cells[1].split("：")[0].split(":")[0].strip()
            subj = "单人-" + (spk[:12] or "未标注")
        seg_first.append((cur, shot, subj))
    if len(seg_first) < 2:
        return rec(True, "④段首构图（文本层）", "只解析到 %d 段，跳过" % len(seg_first))
    bad = []
    for (sa, a, ja), (sb, b, jb) in itertools.combinations(seg_first, 2):
        key_a = set(FRAMING_RE.findall(a))
        key_b = set(FRAMING_RE.findall(b))
        if key_a and key_a == key_b and ja == jb:
            bad.append("段%s首与段%s首同主体同构图（%s｜%s）"
                       % (sa, sb, ja, "、".join(sorted(key_a))))
    for s, a, _ in seg_first[1:]:
        if re.search(r"建立镜头|场景介绍|全景", a):
            bad.append("段%s首出现建立镜头/全景（建立镜头只许段 1 有，段 2 起直接延续上一段收尾景别）" % s)
    # 只写景别不写机位/焦距 = 构图没定死 = 多段必然开成同一个构图
    # （2026-09-29 实锤：work/manifest_dapaidang.json 三段提示词只有「近景/中景」、无机位无焦距，
    #   出片即三段同构图开局；v3 重出补上「平视/低角度/过肩/35-85mm」后才拉开）
    for s, a, _ in seg_first:
        if not ANGLE_RE.search(a):
            bad.append("段%s首只写了景别、没写机位/焦距（构图没定死，多段必然开成同一个构图）" % s)
    return rec(not bad, "④段首构图（文本层）",
               "；".join(bad) if bad else "%d 个段首景别·机位互不相同、无重复开场" % len(seg_first))


def check_crossdup(video, seams, near=1.0, outlier=0.5):
    """④ 像素层：只做**异常点检测 + 出排序表给人看**，不设绝对物理阈值。

    为什么不用 video-shot-dedup 的 MSE ≥ 0.35：那条阈值是为「同一素材被重复用」定的
    （重复=近乎同帧，MSE→0）。生成段之间就算机位构图完全一样，表情/动作差异也会把灰度
    MSE 顶到 2~8（2026-09-29 免费-12 v3 实测 15 对全部落在 2.52~8.41），用 0.35 判等于
    永远不报。所以这里改成：相对离群（< 0.5×中位数）或近乎同帧（< 1.0）才判 FAIL，其余
    出排序表由人看最像的那一对。
    **相邻的「上一段尾 ↔ 下一段首」一对不参与判定**——那一对按 ② 的连贯要求本来就该像。
    """
    total = _dur(video)
    pts, order = {}, []
    for i, s in enumerate(seams):
        head = "段%d首" % (i + 1)
        tail = "段%d尾" % (i + 1)
        pts[head] = min(s + 0.20, max(total - 0.05, 0.0))
        end = (seams[i + 1] if i + 1 < len(seams) else total) - 0.25
        pts[tail] = max(end, s + 0.30)
        order += [head, tail]
    frames = {k: _frame(video, pts[k]) for k in order}
    frames = {k: v for k, v in frames.items() if v is not None}
    if len(frames) < 2:
        return rec(False, "④跨段构图（像素层）",
                   "抽帧失败（每个点必须独立 -ss 抽，别用 fps 滤镜批量抽）")
    adjacent = {("段%d尾" % i, "段%d首" % (i + 1)) for i in range(1, len(seams) + 1)}
    vals = []
    for ka, kb in itertools.combinations(frames.keys(), 2):
        d = _mse(frames[ka], frames[kb])
        vals.append((d, ka, kb, (ka, kb) in adjacent))
    vals.sort()
    print("  取样点两两灰度 MSE（小=像，*=相邻接缝对，不参与判定）：")
    for d, ka, kb, adj in vals:
        print("    %-7s %-7s %6.3f%s" % (ka, kb, d, " *" if adj else ""))
    judged = [v for v in vals if not v[3]]
    if not judged:
        return rec(True, "④跨段构图（像素层）", "没有可判定的非相邻对")
    med = sorted(d for d, _, _, _ in judged)[len(judged) // 2]
    bad = ["%s↔%s MSE=%.3f" % (ka, kb, d) for d, ka, kb, _ in judged
           if d < near or d < outlier * med]
    return rec(not bad, "④跨段构图（像素层）",
               "疑似同机位/同构图：%s（判据：< %.1f 近乎同帧，或 < %.1f×中位数 %.3f 离群）"
               % ("；".join(bad), near, outlier, med)
               if bad else "%d 对非相邻取样点无离群（中位数 %.3f，最小 %.3f）"
               % (len(judged), med, judged[0][0]))


def check_seam(video, seams=()):
    r = subprocess.run([FF, "-v", "info", "-i", video, "-vf",
                        "freezedetect=n=-60dB:d=0.15", "-f", "null", "-"],
                       capture_output=True, text=True)
    fz = re.findall(r"freeze_start: ([\d.]+)", r.stderr)
    ok = rec(not fz, "②接缝定格",
             "freezedetect 命中 %s（合格线 0 处；段尾冻结帧必须拼接前剪掉）" % fz
             if fz else "freezedetect 0 处")
    if seams:
        r2 = subprocess.run([FF, "-v", "info", "-i", video, "-af",
                             "silencedetect=n=-40dB:d=0.08", "-f", "null", "-"],
                            capture_output=True, text=True)
        sil = [(float(a), float(b)) for a, b in
               re.findall(r"silence_start: ([\d.]+)[\s\S]*?silence_end: ([\d.]+)", r2.stderr)]
        bad = ["段首 %.2fs 处静默 %.2fs" % (s, b - max(a, s)) for s in seams for (a, b) in sil
               if a <= s + 0.02 and b - max(a, s) > 0.10]
        rec(not bad, "②段首静默",
            "；".join(bad) + "（合格线 ≤0.10s）" if bad else "各段首静默 ≤0.10s")
    return ok


# ------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["storyboard", "subtitle", "readrate",
                                    "crossdup", "seam", "all"])
    ap.add_argument("target")
    ap.add_argument("--text", default="")
    ap.add_argument("--seams", default="")
    ap.add_argument("--final", default="")
    ap.add_argument("--allow", default="")
    ap.add_argument("--floor", type=float, default=0.95)
    a = ap.parse_args()
    seams = [float(x) for x in a.seams.split(",") if x.strip()]
    allow = [x for x in a.allow.split(",") if x.strip()]

    if a.cmd == "storyboard":
        check_storyboard(a.target)
    elif a.cmd == "subtitle":
        check_subtitle(a.target, allow)
    elif a.cmd == "readrate":
        if not a.text:
            print("用法：readrate <段视频> --text 「本段台词（字幕原字）」")
            return 2
        check_readrate(a.target, a.text, a.floor)
    elif a.cmd == "crossdup":
        if not seams:
            print("用法：crossdup <成片> --seams 0,8.92,19.54（段起点，见拼接日志）")
            return 2
        check_crossdup(a.target, seams)
    elif a.cmd == "seam":
        check_seam(a.target, seams)
    else:
        check_storyboard(a.target)
        for ass in sorted(set(glob.glob(os.path.join(a.target, "*.ass")) +
                              glob.glob(os.path.join(a.target, "**/*.ass"), recursive=True))):
            check_subtitle(ass, allow)
        finals = sorted(glob.glob(os.path.join(a.target, "out/*.mp4")), key=os.path.getmtime)
        final = a.final or (finals[-1] if finals else "")
        if final:
            check_seam(final, seams)
            if seams:
                check_crossdup(final, seams)
            else:
                print("SKIP ④：没给 --seams 段起点，跨段构图比对跑不了")
        else:
            print("SKIP ②④：没找到成片（给 --final）")
        print("SKIP ⑥：实念率要逐段跑 readrate（段视频 + 该段台词）")

    fails = [r for r in RESULTS if not r[0]]
    print("\n合计 %d 项，FAIL %d 项" % (len(RESULTS), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
