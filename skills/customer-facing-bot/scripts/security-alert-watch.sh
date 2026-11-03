#!/bin/bash
# security-alert-watch.sh — 监控安全日志，有新告警就输出（cron自动投递）
LOG_FILE="/home/ubuntu/.hermes/guard/security_alerts.log"
SEEN_FILE="/home/ubuntu/.hermes/guard/.alerts_seen"
mkdir -p "$(dirname "$LOG_FILE")"
[ ! -f "$LOG_FILE" ] && { touch "$LOG_FILE"; exit 0; }
LAST_LINE=$(tail -1 "$LOG_FILE")
[ -z "$LAST_LINE" ] && exit 0
[ -f "$SEEN_FILE" ] && [ "$LAST_LINE" = "$(cat "$SEEN_FILE")" ] && exit 0
echo "$LAST_LINE"
echo "$LAST_LINE" > "$SEEN_FILE"
