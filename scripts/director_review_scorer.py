#!/usr/bin/env python3
"""director_review_scorer.py — 导演意图四维评分器（2026-08-20 P2.2 新增）

创意评审的「意图闸」：LLM 当评委，查正则查不出的非机械问题。
四维：
  1. 动作-台词绑定：动作是不是台词带出来的？（镜5「说评论区扣时手放膝上」= 解耦 → 不合格）
  2. 镜数由叙事决定：镜头数是叙事需要，还是为了凑模板/凑时长？
  3. 情绪弧：全片情绪有无起承转合，还是从头平到尾？
  4. 五问真答：导演五问（拍什么/谁在看/为什么现在/情绪基准/唯一诉求）有没有真回答？

用法:
  python3 director_review_scorer.py <分镜文件> [--out 导演评审报告.md]

返回码：
  0 = PASS（四维均过或仅低风险警告）
  2 = 打回（非 action_tie/high 的中高风险问题，门禁阶段仅 WARN）
  4 = 强制打回（action_tie 维度存在 high 问题）
"""
import argparse
import json
import os
import re
import sys
import time

import yaml
import requests

MODEL_FALLBACK = "deepseek-v4-pro"
URL = "https://api.deepseek.com/v1/chat/completions"
TEMP = 0.3
MAX_TOKENS = 8000
MAX_CONTENT_CHARS = 60000
THINKING = {"type": "enabled"}
CONFIG_PATH = os.environ.get(
    "HERMES_CONFIG",
    os.path.join(os.environ.get("HERMES_HOME", os.path.join(os.path.expanduser("~"), ".hermes")), "config.yaml"),
)
SCORE_DIMS = ("action_tie", "narrative_shots", "emotion_arc", "five_questions")
ACTION_TIE_BLOCK_MARKER = "INTENT_BLOCK:action_tie:high"

def load_key():
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as handle:
                cfg = yaml.safe_load(handle) or {}
            key = cfg.get("model", {}).get("api_key", "")
            if key:
                return key
        except (OSError, TypeError, yaml.YAMLError):
            pass
    return os.environ.get("DEEPSEEK_API_KEY", "")


def load_model():
    """模型名与 API key 使用同一份本机配置，原模型名仅作兜底。

    优先读取 auxiliary.model.default（辅助任务专用模型，如评审/质检），
    缺失时才回退顶层 model.default（主对话模型），再缺失用 MODEL_FALLBACK。
    """
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as handle:
                cfg = yaml.safe_load(handle) or {}
            name = cfg.get("auxiliary", {}).get("model", {}).get("default", "")
            if not (isinstance(name, str) and name.strip()):
                name = cfg.get("model", {}).get("default", "")
            if isinstance(name, str) and name.strip():
                return name.strip()
        except (OSError, TypeError, yaml.YAMLError):
            pass
    return MODEL_FALLBACK

JUDGE_PROMPT = """你是资深导演评委。请对以下分镜脚本做导演意图四维评审。
判断标准（不是格式检查，是创作质量检查）：

1. 动作-台词绑定：每个动作是否由台词/情境带出来？若存在「说 A 的同时做与 A 无关的 B」→ 问题。
2. 镜数由叙事决定：镜头数量是叙事需要还是凑模板？若镜头可删可并、无信息增量 → 问题。
3. 情绪弧：全片情绪有无起承转合？从头平到尾 → 问题。
4. 五问真答：拍什么/谁在看/为什么现在/情绪基准/唯一诉求，这五问在脚本里能不能回答出来？

输出严格 JSON（不要其他文字）：
{{"scores": {{"action_tie": 0-100, "narrative_shots": 0-100, "emotion_arc": 0-100, "five_questions": 0-100}}, "issues": [{{"dim": "action_tie", "severity": "high|mid|low", "detail": "..."}}], "overall": 0-100, "verdict": "PASS|REWORK"}}
PASS 条件：四维均 >= 60 且无 high 问题。

分镜内容：
===BEGIN===
{content}
===END===
"""

def judge(content):
    key = load_key()
    if not key:
        print("❌ 无 DeepSeek key", file=sys.stderr)
        return None
    prompt = JUDGE_PROMPT.format(content=content[:MAX_CONTENT_CHARS])
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": load_model(),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": TEMP,
        "max_tokens": MAX_TOKENS,
        "thinking": THINKING,
    }
    for attempt in range(3):
        try:
            r = requests.post(URL, headers=headers, json=payload, timeout=120)
            r.raise_for_status()
            d = r.json()
            message = d["choices"][0]["message"]
            text = message.get("content") or message.get("reasoning_content") or ""
            # 提取 JSON（可能被代码块包裹）
            m = re.search(r"\{.*\}", text, re.S)
            if not m:
                print(
                    f"[judge] 响应无JSON(attempt {attempt + 1}): {text[:200]}",
                    file=sys.stderr,
                )
                if attempt == 2:
                    return None
                time.sleep(2 * (attempt + 1))
                continue
            return json.loads(m.group(0))
        except (requests.RequestException, KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
            if attempt == 2:
                print(f"[judge] 调用失败: {e}", file=sys.stderr)
                return None
            time.sleep(2 * (attempt + 1))
    return None


def normalize_result(result):
    """校验 Judge 契约，并由代码重算 verdict，避免模型自相矛盾时误放行。"""
    if not isinstance(result, dict) or not isinstance(result.get("scores"), dict):
        raise ValueError("响应缺少 scores 对象")
    scores = {}
    for dim in SCORE_DIMS:
        value = result["scores"].get(dim)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 100:
            raise ValueError(f"{dim} 必须是 0-100 数值")
        scores[dim] = float(value)
    issues = result.get("issues", [])
    if not isinstance(issues, list) or not all(isinstance(item, dict) for item in issues):
        raise ValueError("issues 必须是对象数组")
    high_risk = any(str(item.get("severity", "")).lower() == "high" for item in issues)
    verdict = "PASS" if min(scores.values()) >= 60 and not high_risk else "REWORK"
    overall = sum(scores.values()) / len(scores)
    return scores, issues, overall, verdict


def has_high_action_tie(issues):
    """唯一提前收紧的窄口径：动作与台词解耦达到 high 时强制拦截。"""
    return any(
        str(item.get("dim", "")).lower() == "action_tie"
        and str(item.get("severity", "")).lower() == "high"
        for item in issues
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("storyboard")
    ap.add_argument("--out", default="导演评审报告.md")
    args = ap.parse_args()
    if not os.path.isfile(args.storyboard):
        print(f"BLOCKED: 分镜文件不存在 {args.storyboard}")
        return 2
    content = open(args.storyboard, encoding="utf-8", errors="ignore").read()
    res = judge(content)
    if res is None:
        print("BLOCKED: 意图闸评审失败（judge 无响应），不自动放行")
        return 2
    try:
        scores, issues, overall, verdict = normalize_result(res)
    except ValueError as exc:
        print(f"BLOCKED: 意图闸响应格式无效（{exc}），不自动放行")
        return 2
    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("# 导演意图评审报告\n\n")
        f.write(f"- 判定: {verdict}\n")
        f.write(f"- 总分: {overall:.1f}\n")
        reviewed_chars = min(len(content), MAX_CONTENT_CHARS)
        coverage = reviewed_chars / len(content) * 100 if content else 100.0
        f.write(f"- 覆盖: {reviewed_chars}/{len(content)} 字符（{coverage:.1f}%）\n")
        if reviewed_chars < len(content):
            f.write(f"- 截断告警: 超出 {MAX_CONTENT_CHARS} 字符的内容未送评\n")
        f.write(f"- 四维: 动作-台词绑定 {scores['action_tie']:g} / 镜数叙事 {scores['narrative_shots']:g} / 情绪弧 {scores['emotion_arc']:g} / 五问 {scores['five_questions']:g}\n\n")
        if issues:
            f.write("## 问题清单\n\n")
            for it in issues:
                f.write(f"- [{it.get('severity')}] {it.get('dim')}: {it.get('detail')}\n")
    print(f"意图闸: {verdict}（总分{overall:.1f}，{len(issues)}个问题）")
    if has_high_action_tie(issues):
        print(ACTION_TIE_BLOCK_MARKER)
    print(f"OUTPUT: {os.path.abspath(args.out)}")
    if has_high_action_tie(issues):
        return 4
    return 0 if verdict == "PASS" else 2

if __name__ == "__main__":
    sys.exit(main())
