#!/bin/bash
# MemoryHub Health Check — Qdrant + MCP Server + Scanner 三重監控
# 由 crontab 每 60 秒呼叫一次

LOG="/tmp/memory_hub_health.log"
MAX_LOG_LINES=500
STATUS="OK"

# ── 檢查 Qdrant ──
if ! curl -sf http://localhost:6333/health > /dev/null 2>&1; then
    STATUS="QDRANT_DOWN"
fi

# ── 檢查 MemoryHub Scanner 進程 ──
if ! pgrep -f "session_scanner.py" > /dev/null 2>&1; then
    if [ "$STATUS" = "OK" ]; then
        STATUS="SCANNER_DOWN"
    else
        STATUS="QDRANT_AND_SCANNER_DOWN"
    fi
fi

# ── 只在狀態變化時記錄 ──
STATE_FILE="/tmp/memory_hub_health_state"
PREV_STATUS=$(cat "$STATE_FILE" 2>/dev/null || echo "UNKNOWN")

if [ "$STATUS" != "$PREV_STATUS" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $STATUS (was: $PREV_STATUS)" >> "$LOG"
    echo "$STATUS" > "$STATE_FILE"
fi

# ── Log rotation ──
if [ -f "$LOG" ] && [ $(wc -l < "$LOG" 2>/dev/null || echo 0) -gt $MAX_LOG_LINES ]; then
    tail -200 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi
