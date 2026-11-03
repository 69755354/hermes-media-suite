#!/bin/bash
# hash-verify.sh — 核心规则文件哈希校验
GUARD_DIR="/home/ubuntu/.hermes/guard"
HASH_DIR="$GUARD_DIR/hashes"
ALERT_LOG="$GUARD_DIR/security_alerts.log"
FILES=(
    "/home/ubuntu/.hermes/SOUL.md:SOUL.md.md5"
    "/home/ubuntu/.hermes/profiles/customer/SOUL.md:customer_SOUL.md.md5"
)
ALL_PASS=true
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
for ENTRY in "${FILES[@]}"; do
    FILE="${ENTRY%%:*}"; HASH_FILE="${HASH_DIR}/${ENTRY##*:}"
    [ ! -f "$FILE" ] && { echo "[$TIMESTAMP] HASH_FAIL:FILE_MISSING:$FILE" >> "$ALERT_LOG"; echo "FAIL:$FILE"; ALL_PASS=false; continue; }
    [ ! -f "$HASH_FILE" ] && { echo "[$TIMESTAMP] HASH_FAIL:HASH_MISSING:$FILE" >> "$ALERT_LOG"; echo "FAIL:$FILE"; ALL_PASS=false; continue; }
    CURRENT=$(md5sum "$FILE" | awk '{print $1}'); STORED=$(cat "$HASH_FILE" | awk '{print $1}')
    [ "$CURRENT" != "$STORED" ] && { echo "[$TIMESTAMP] HASH_FAIL:MISMATCH:$FILE" >> "$ALERT_LOG"; echo "FAIL:$FILE"; ALL_PASS=false; } || echo "OK:$FILE"
done
[ "$ALL_PASS" = false ] && { echo "SECURITY_BREACH: 规则文件被篡改"; exit 1; }
echo "ALL_OK"
