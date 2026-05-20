# MemoryHub v2.0 — 功能完善建議 & 任務清單

> 日期: 2026-05-19 | 基於全代碼審查 | 僅建議，不執行

---

## 🔴 第一優先（部署就緒）

### 1. Qdrant Collection 初始化
```bash
# 需建立 3 個新 collection（openclaw_mem 已存在）
for col in deepseek_mem hermes_mem claude_mem; do
  curl -X PUT "http://localhost:6333/collections/$col" \
    -H 'Content-Type: application/json' \
    -d '{"vectors":{"size":384,"distance":"Cosine"}}'
done
```
| Collection | 用途 | 狀態 |
|-----------|------|------|
| `deepseek_mem` | DeepSeek TUI 對話記憶 | ❌ 未建 |
| `hermes_mem` | Hermes Agent 對話記憶 | ❌ 未建 |
| `claude_mem` | Claude Code 對話記憶 | ❌ 未建 |

### 2. 掃描路徑校準
當前 `capture_daemon.py` 設定的路徑與實際路徑對比：

| 平台 | 設定路徑 | 建議路徑 | 原因 |
|------|---------|---------|------|
| **OpenClaw** | `~/.openclaw/agents/main/sessions/` | ✅ 正確 | — |
| **DeepSeek TUI** | `~/.deepseek/sessions/` | `~/.deepseek/sessions/checkpoints/latest.json` | 只有 checkpoint 格式 |
| **Hermes** | `~/.hermes/sessions/` | ⚠️ 待確認目錄存在 | — |
| **Claude Code** | `~/.claude/projects/-Users-Claw/memory/` | `~/.claude/projects/` (遍歷子目錄) | 路徑含特殊字符 `-Users-Claw` |

### 3. capture_daemon.py 啟動
```bash
# 方法 A: 直接啟動
python3 ~/Desktop/MemoryHub/capture_daemon.py

# 方法 B: launchd 開機自啟
cp ~/Desktop/MemoryHub/scripts/com.memoryhub.capture-daemon.plist \
   ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.memoryhub.capture-daemon.plist
```

---

## 🟡 第二優先（功能增強）

### 4. Dashboard 端口統一
| 檔案 | 預設端口 | 用途 |
|------|---------|------|
| `capture_daemon.py` | **3872** | 捕獲看板 |
| `hub_server.py` | **3120** | 中樞伺服器 |

> **建議**：統一為一個端口，或明確區分用途並在 README 說明。

### 5. 四平台 MCP 配置部署
每平台需將 MCP JSON 寫入對應設定檔：

| 平台 | 設定檔 | MCP 配置 |
|------|--------|---------|
| OpenClaw | `~/.openclaw/openclaw.json` | `mcp.openclaw.json` |
| DeepSeek TUI | `~/.deepseek/mcp.json` | `mcp.deepseek.json` |
| Hermes | `~/.hermes/config.yaml` | `mcp.hermes.json` (需轉 YAML) |
| Claude Code | `~/.claude.json` | `mcp.claude.json` |

### 6. hub_server.py 整合 Hook 接收
目前 `hub_server.py` 有 `POST /hook` 端點，但 capture_daemon.py 的 hook 是內部攔截。需要確認兩個模組之間的 hook 傳遞機制：

```
Agent → MCP tools → capture_daemon MODE A → hub_server POST /hook → Dashboard
```

> **建議**：capture_daemon 成功捕獲後，主動 POST 到 hub_server 的 `/hook` 端點。

### 7. 跨平台統一搜索 API
`hub_server.py` 的 `/api/search` 目前只搜檔案層。建議整合 Qdrant 向量搜索：

```python
# 建議：hub_server 的 unified_search() 加入 Qdrant 層
def unified_search(query, limit=10):
    # Layer 1: Qdrant 向量搜索 (bypass MCP, direct client)
    # Layer 2: 檔案層全文搜索
    # Layer 3: 合併去重排序
```

---

## 🟢 第三優先（長期增強）

### 8. MCP Server 自動加載
`server/mcp_server.py` 目前是 standalone JSON-RPC stdio 伺服器。需要確保各平台能正確啟動它：

```json
// 各平台的 MCP 設定中
{
  "command": "python3",
  "args": ["/Users/Claw/Desktop/MemoryHub/server/mcp_server.py"],
  "env": {
    "MEMORY_COLLECTION": "openclaw_mem",  // 隨平台變化
    "QDRANT_URL": "http://localhost:6333"
  }
}
```

### 9. backup_daemon.py 自動排程
目前 `backup_daemon.py` 是手動 CLI 觸發。建議加入 launchd 排程或 crontab：

```bash
# /Library/LaunchDaemons/com.memoryhub.backup.plist
# 或 crontab
0 * * * * python3 ~/Desktop/MemoryHub/backup_daemon.py --tier hourly
0 2 * * * python3 ~/Desktop/MemoryHub/backup_daemon.py --tier daily
0 3 * * 0 python3 ~/Desktop/MemoryHub/backup_daemon.py --tier weekly
```

### 10. capture_daemon.py 錯誤恢復
目前已支援檢查點（`.capture_checkpoint.json`），但崩潰後重啟時應**自動從檢查點恢復**而非從頭掃描。當前邏輯已部分實現 — 建議補完：

```python
# 建議：啟動時檢查檢查點
checkpoint = MH_DIR / ".capture_checkpoint.json"
if checkpoint.exists():
    data = json.loads(checkpoint.read_text())
    STATE["total_captured"] = data.get("total", 0)
    # 從最近檢查點繼續，而非歸零
```

### 11. 多語言搜尋支援
`hybrid_search.py` + `server/mcp_server.py` 目前使用 BGE-m3（支援多語言）。但中文分詞精度可優化：

> **建議**：加入 jieba 中文分詞輔助關鍵字匹配，提升中文搜尋精準度。

### 12. 知識圖譜可視化
`entity_graph.py` 已有實體提取和關係建立，但缺少視覺化輸出。

> **建議**：輸出 Graphviz DOT 格式或 Mermaid 語法，讓關係圖可視化。

---

## 📋 任務優先級總表

| # | 任務 | 優先級 | 類別 | 預估時間 |
|---|------|--------|------|---------|
| 1 | 建立 3 個 Qdrant collection | 🔴 | 部署 | 1 min |
| 2 | 校準 4 平台掃描路徑 | 🔴 | 部署 | 5 min |
| 3 | 啟動 capture_daemon.py | 🔴 | 部署 | 1 min |
| 4 | Dashboard 端口統一 | 🟡 | 增強 | 5 min |
| 5 | 部署 4 平台 MCP 配置 | 🟡 | 部署 | 10 min |
| 6 | Hub Server Hook 串接 | 🟡 | 架構 | 15 min |
| 7 | Qdrant 向量搜索整合到 hub | 🟡 | 增強 | 20 min |
| 8 | MCP Server 自動載入驗證 | 🟢 | 部署 | 10 min |
| 9 | backup_daemon 自動排程 | 🟢 | 增強 | 10 min |
| 10 | 崩潰恢復檢查點完善 | 🟢 | 增強 | 10 min |
| 11 | 中文分詞搜尋優化 | 🟢 | 增強 | 30 min |
| 12 | 知識圖譜可視化 | 🟢 | 增強 | 20 min |

---

*研究完畢，未執行任何修改。*
