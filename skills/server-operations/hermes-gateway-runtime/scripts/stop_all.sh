#!/bin/bash
# ===== 急停脚本（用户喊「急停/停」时立即执行）=====
# 物理停掉所有后台重任务：codex / claude / 数据恢复脚本 / COS 测试等
# 已部署：~/.hermes/scripts/stop_all.sh（2026-08-16）
# 用法：bash ~/.hermes/scripts/stop_all.sh
echo "=== 急停 $(date '+%H:%M:%S') ==="

# 1. codex/claude 执行器
pkill -f "codex exec" 2>/dev/null && echo "✓ codex 已杀" || echo "- 无 codex"
pkill -f "claude -p" 2>/dev/null && echo "✓ claude 已杀" || echo "- 无 claude"

# 2. 数据恢复/测试脚本（历史遗留任务）
pkill -f "rebuild_xiaolu" 2>/dev/null && echo "✓ rebuild 已杀" || echo "- 无 rebuild"
pkill -f "test_cos" 2>/dev/null && echo "✓ COS测试 已杀" || echo "- 无 COS测试"
pkill -f "deep_recover" 2>/dev/null && echo "✓ recover 已杀" || echo "- 无 recover"

# 3. 其他 python 重任务（>30% CPU 的）
for pid in $(ps aux | awk '$3 > 30 && $11 ~ /python3?/ {print $2}'); do
    cmd=$(ps -p $pid -o cmd= 2>/dev/null)
    # 不杀系统关键进程
    case "$cmd" in
        *hermes_cli*|*sshd*|*caddy*|*relay*|*helper_api*|*execute_api*|*task_api*|*billing*) ;;
        *) kill -9 $pid 2>/dev/null && echo "✓ 重任务 pid=$pid 已杀: $(echo $cmd | cut -c1-60)";;
    esac
done

echo "=== 急停完成，剩余 python 重任务：==="
ps aux | awk '$3 > 30 && $11 ~ /python3?/ {print $2, $3"%", $11}' | grep -v awk | head -5
echo "（空 = 全部停干净）"
