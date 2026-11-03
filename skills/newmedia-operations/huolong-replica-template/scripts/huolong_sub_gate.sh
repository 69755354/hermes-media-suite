#!/usr/bin/env bash
# 烧字幕前的物理卡点（2026-09-29 用户批）：同音占位错字没查过，不许烧字幕。
# 用法：huolong_sub_gate.sh <字幕.ass> [--allow 词]
# 退出 0 = 可以烧；非 0 = 拒绝，且原因打到 stderr。
set -u
ASS="${1:?用法: huolong_sub_gate.sh <字幕.ass> [--allow 词]}"; shift || true
CHK="$(dirname "$0")/huolong_six_checks.py"
if [ ! -f "$CHK" ]; then echo "[BLOCKED] 找不到判据脚本 $CHK" >&2; exit 2; fi
OUT="$(python3 "$CHK" subtitle "$ASS" "$@" 2>&1)"; RC=$?
echo "$OUT"
if [ $RC -ne 0 ]; then
  echo "[BLOCKED] 字幕判据 FAIL → 不许烧字幕（$ASS）" >&2
  exit $RC
fi
echo "[GATE] 字幕判据 PASS → 可以烧（$ASS）"
