# MemoryHub Guard Layer — 監控文檔

## 健康檢查腳本 (health_check.sh)

每 60 秒執行一次，檢查三項：
1. **Qdrant**：`curl -sf http://localhost:6333/health`
2. **Scanner**：`pgrep -f session_scanner.py`
3. **MCP Server**：`pgrep -f mcp_server.py`

狀態變化時記錄到 `/tmp/memory_hub_health.log`。連續故障時發送桌面通知。

## Crontab 排程

```bash
# Session JSONL 掃描 — 每 5 分鐘
*/5 * * * * python3 ~/.memory-hub/scanner/session_scanner.py

# 檔案差分同步 — 每 15 分鐘
*/15 * * * * python3 auto_sync.py

# 健康檢查 — 每 1 分鐘
* * * * * bash ~/.memory-hub/guard/health_check.sh

# 每日記憶摘要 — 每天 23:00
0 23 * * * python3 ~/.memory-hub/scanner/session_scanner.py --daily-summary

# 每週濃縮 — 每週日 23:30
30 23 * * 0 python3 consolidate.py weekly

# 每月濃縮 — 每月 1 日 00:00
0 0 1 * * python3 consolidate.py monthly

# 年度濃縮 — 每年 1/1 00:00
0 0 1 1 * python3 consolidate.py yearly
```

## 警報條件

| 條件 | 級別 | 行動 |
|------|------|------|
| Qdrant 離線 >5 分鐘 | ⚠️ WARN | 記錄到 health log |
| Qdrant 離線 >30 分鐘 | 🔴 CRIT | 發送桌面通知 |
| Scanner 停止 >10 分鐘 | ⚠️ WARN | 記錄到 health log |
| 3 天無新記憶 | ⚠️ WARN | 檢查 crontab |
| 7 天無新記憶 | 🔴 CRIT | 發送桌面通知 |
