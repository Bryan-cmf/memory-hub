#!/bin/bash
# MemoryHub Three-Layer Guard v1.2
# Monitors: Qdrant + MCP Server + Capture Daemon + Scanner
# Called by crontab every 60 seconds

LOG="/tmp/memory_hub_guard.log"
MAX_LOG_LINES=500
STATUS="OK"
ISSUES=""

# ── Layer 1: Qdrant Health ──
if ! curl -sf --max-time 3 http://localhost:6333/health > /dev/null 2>&1; then
    STATUS="QDRANT_DOWN"
    ISSUES="$ISSUES qdrant"
fi

# ── Layer 2: Capture Daemon (new in v1.2) ──
CAPTURE_PIDFILE="$HOME/.memory-hub/capture_daemon.pid"
if [ -f "$CAPTURE_PIDFILE" ]; then
    CAPTURE_PID=$(cat "$CAPTURE_PIDFILE" 2>/dev/null)
    if ! kill -0 "$CAPTURE_PID" 2>/dev/null; then
        if [ "$STATUS" = "OK" ]; then
            STATUS="CAPTURE_DOWN"
        else
            STATUS="${STATUS}_CAPTURE_DOWN"
        fi
        ISSUES="$ISSUES capture-daemon"
    fi
else
    # Capture daemon not required (optional component)
    :
fi

# ── Layer 3: Session Scanner ──
if ! pgrep -f "session_scanner.py" > /dev/null 2>&1; then
    if [ "$STATUS" = "OK" ]; then
        STATUS="SCANNER_DOWN"
    else
        STATUS="${STATUS}_SCANNER_DOWN"
    fi
    ISSUES="$ISSUES scanner"
fi

# ── State change detection ──
STATE_FILE="/tmp/memory_hub_guard_state"
PREV_STATUS=$(cat "$STATE_FILE" 2>/dev/null || echo "UNKNOWN")

if [ "$STATUS" != "$PREV_STATUS" ]; then
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$TIMESTAMP] $STATUS (was: $PREV_STATUS) issues:$ISSUES" >> "$LOG"
    echo "$STATUS" > "$STATE_FILE"
    
    # ── Desktop notification on critical failures ──
    if [[ "$STATUS" == *"DOWN"* ]] && command -v osascript &>/dev/null; then
        osascript -e "display notification \"MemoryHub: $STATUS\" with title \"🧠 Guard Alert\"" 2>/dev/null || true
    fi
fi

# ── Log rotation ──
if [ -f "$LOG" ] && [ $(wc -l < "$LOG" 2>/dev/null || echo 0) -gt $MAX_LOG_LINES ]; then
    tail -200 "$LOG" > "${LOG}.tmp" && mv "${LOG}.tmp" "$LOG"
fi

echo "$STATUS"
