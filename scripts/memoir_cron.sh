#!/bin/bash
# Memory Value Platform — Cron Wrapper
# 被 cron 調用，負責準備回憶錄生成環境並觸發

set -e

WORKSPACE="$HOME/.openclaw/workspace"
MEMOIR_DIR="$HOME/.memory-hub/memoirs"
SCRIPT="$HOME/Desktop/MemoryHub/memory_hub/memoir.py"
LOG="/tmp/memoir-cron.log"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> "$LOG"

MODE="$1"
DATE_ARG="${2:-}"

cd $HOME/Desktop/MemoryHub

if [ "$MODE" = "week" ]; then
    echo "📔 生成週度回憶錄..." >> "$LOG"
    if [ -n "$DATE_ARG" ]; then
        python3 -m memory_hub.memoir week --date "$DATE_ARG" --dry-run >> "$LOG" 2>&1
    else
        python3 -m memory_hub.memoir week --dry-run >> "$LOG" 2>&1
    fi
    echo "✅ Prompt 已準備，等待 OpenClaw agent 完成生成" >> "$LOG"

elif [ "$MODE" = "month" ]; then
    echo "📕 生成月度回憶錄..." >> "$LOG"
    if [ -n "$DATE_ARG" ]; then
        python3 -m memory_hub.memoir month --date "$DATE_ARG" --dry-run >> "$LOG" 2>&1
    else
        python3 -m memory_hub.memoir month --dry-run >> "$LOG" 2>&1
    fi
    echo "✅ Prompt 已準備" >> "$LOG"

else
    echo "Usage: $0 {week|month} [date YYYY-MM-DD]"
    exit 1
fi
