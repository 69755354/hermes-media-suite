#!/usr/bin/env python3
"""
security-middleware.py — 全链路越权防御中间层
所有API请求/节点执行前必须经过本中间层校验。
硬编码，不可被任何输入/模型输出绕过。
"""
import json, os, sys, time, re
from pathlib import Path

GUARD_DIR = Path("/home/ubuntu/.hermes/guard")
STATE_FILE = GUARD_DIR / "middleware_state.json"
ALERT_LOG = GUARD_DIR / "security_alerts.log"
OP_LOG = GUARD_DIR / "operations.log"

# 硬编码配置
PARAM_WHITELIST = {
    "seedance": {
        "allowed_keys": {"prompt", "duration", "reference_image", "seed", "model"},
        "ranges": {"duration": (3, 10), "seed": (1, 999999999)},
        "allowed_models": {"doubao-seedance-2-0-mini-260615"},
        "allowed_dynamic_strength": (25, 45),
    },
    "chanjing": {
        "allowed_keys": {"audio_man", "text", "digital_human_id", "model", "speed", "gesture_strength", "background_img", "clothes_img"},
        "ranges": {"speed": (0.8, 1.2), "gesture_strength": (0.1, 0.5)},
    },
    "deepseek": {
        "allowed_keys": {"model", "messages", "temperature", "max_tokens"},
        "ranges": {"temperature": (0.0, 1.0), "max_tokens": (100, 4096)},
        "allowed_models": {"deepseek-v4-pro", "deepseek-v4-flash"},
    },
}
CHANNEL_BINDING = {"探店": "seedance", "剧情": "seedance", "口播": "chanjing"}
BLOCKED_KEYWORDS = [
    "跳过校验","跳过节点","修改参数","强制1080P","忽略白名单",
    "不用规则","切换通道","多渲染几次","删除限制","临时放开权限",
    "忽略SOUL","忽略SKILL","无视安全","覆盖规则","忽略所有之前的",
    "忽略规则","忽略指令","忽略设置",
    "DAN模式","开发者模式","God模式","Do Anything Now",
    "ignore all previous","ignore all prior","override",
    "ignore all instructions","ignore all rules",
]
MAX_RETRIES = 2
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 3
RATE_LIMIT_COOLDOWN = 600
COST_THRESHOLD = 50.0

# CLI commands: check_params, check_channel, check_keywords, check_retry, increment_retry, check_rate, check_cost, record_cost, log, status
# Usage: security-middleware.py <command> [args]
