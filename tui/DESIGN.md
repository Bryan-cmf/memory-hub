# MemoryHub TUI — 向量記憶系統終端界面

> 版本：v1.0.0 | 依賴：Python 3.9+ + textual
>
> 一個鍵盤驅動的終端界面，用於監控、搜索和管理向量記憶系統。

---

## 一、技術選型

| 選項 | 選擇 | 理由 |
|------|------|------|
| 框架 | **Textual** (Python) | Rich TUI 框架，CSS 佈局，內建 widget 豐富 |
| 替代 | Rich Live | 更輕量但功能較少 |
| 後端 | 直接調用 Qdrant HTTP API | 零額外依賴 |
| 安裝 | `pip install memory-hub[tui]` | 可選安裝，不強制 |

---

## 二、啟動方式

```bash
# 安裝後
memory-hub tui                    # 啟動 TUI
memory-hub tui --collection openclaw_mem  # 指定 collection
memory-hub tui --refresh 3        # 每 3 秒自動刷新（默認 5 秒）

# 快捷鍵
mh-tui                            # 別名
```

---

## 三、界面佈局（Dashboard 首頁）

```
┌─────────────────────────────────────────────────────────────┐
│ 🧠 MemoryHub v1.0.0                     Q: Quit  H: Help    │ ← 頂欄
├───────────────┬─────────────────────────────────────────────┤
│               │                                             │
│  📊 Dashboard │  🟢 System Status                           │
│               │  ┌─────────────────────────────────────┐    │
│  🔍 Search    │  │ Qdrant:    ● Online  (v1.13)        │    │
│               │  │ Scanner:   ● Running (last: 2m ago) │    │
│  💾 Save      │  │ Health:    ● OK                     │    │
│               │  │ Uptime:    3d 12h 45m               │    │
│  📈 Stats     │  │ Model:     BGE-m3 (1024d, MPS)      │    │
│               │  │ Tier:      2 (Qdrant Full)          │    │
│  ⚙️  Settings │  └─────────────────────────────────────┘    │
│               │                                             │
│               │  📊 Collections                             │
│               │  ┌──────────────┬──────┬────────┬────────┐  │
│               │  │ Collection   │ Docs │ Vectors│ Status │  │
│               │  ├──────────────┼──────┼────────┼────────┤  │
│               │  │ openclaw_mem │ 1409 │  1409  │  🟢    │  │
│               │  │ hermes_mem   │   0  │    0   │  🟢    │  │
│               │  │ shared_mem   │   0  │    0   │  🟢    │  │
│               │  └──────────────┴──────┴────────┴────────┘  │
│               │                                             │
│               │  📡 Recent Scans                            │
│               │  ┌─────────────────────────────────────┐    │
│               │  │ 19:30  Scanned 3 sessions, 12 new   │    │
│               │  │ 19:25  Scanned 3 sessions, 0 new    │    │
│               │  │ 19:20  Scanned 2 sessions, 5 new    │    │
│               │  └─────────────────────────────────────┘    │
├───────────────┴─────────────────────────────────────────────┤
│ 🟢 System OK │ openclaw_mem: 1409 docs │ Scanner: Running   │ ← 底欄
└─────────────────────────────────────────────────────────────┘
```

---

## 四、五個面板詳解

### 4.1 📊 Dashboard（儀表板）

**顯示內容**：Qdrant 連接狀態、Scanner 狀態、模型信息、運行時長、最近掃描日誌（最後 5 條）、各 Collection 文檔數量表格

**刷新頻率**：每 5 秒自動刷新

### 4.2 🔍 Search（語義搜索）

**功能**：輸入自然語言查詢 → 實時搜索 → 結果列表（含 score、日期、tags、內容預覽）

**快捷鍵**：
| 鍵 | 功能 |
|----|------|
| `Enter` | 查看記憶詳情（彈窗顯示完整內容 + metadata） |
| `D` | 刪除選中的記憶（確認彈窗） |
| `S` | 複製到 Save 面板 |

### 4.3 💾 Save（保存記憶）

**功能**：輸入記憶內容 → 選擇 collection → 添加 tags/metadata → 保存到向量庫。下方顯示最近保存記錄（成功/失敗）。

### 4.4 📈 Stats（統計分析）

**顯示**：
- 總記憶數
- 按 Collection 分佈（橫條圖）
- 按標籤分佈（Top 10，橫條圖）
- 時間分佈（最近 30 天，熱力圖）
- 記憶品質（平均長度、最舊/最新日期）

### 4.5 ⚙️ Settings（設置）

**可調參數**：

| 參數 | 類型 | 默認值 | 說明 |
|------|------|--------|------|
| `similarity_threshold` | slider (0.3-0.95) | 0.6 | 搜索相似度閾值 |
| `max_results` | select (1-50) | 10 | 搜索最大返回數 |
| `scan_interval` | select (1-60 min) | 5 | JSONL 掃描間隔 |
| `auto_sync` | toggle | ON | 自動檔案同步 |
| `collections` | multi-select | [openclaw_mem] | 啟用的 collections |
| `embedding_model` | select | BGE-m3 | Embedding 模型 |
| `session_dirs` | text list | [預設] | 自定義 session 目錄 |
| `skip_patterns` | text list | [emails,...] | 跳過關鍵詞 |

**操作**：`↑↓` 選擇 / `←→` 調整 / `Enter` 確認 / `Ctrl+S` 保存 / `Ctrl+R` 恢復默認

---

## 五、全局快捷鍵

| 鍵 | 功能 |
|----|------|
| `1`-`5` | 直接跳到面板 (Dashboard/Search/Save/Stats/Settings) |
| `Tab` / `Shift+Tab` | 前進/後退面板 |
| `Q` / `Ctrl+C` | 退出 |
| `H` / `?` | 幫助彈窗 |
| `R` | 手動刷新 |
| `F` | 全屏切換 |
| `/` | 快速跳到 Search 面板 |
| `Ctrl+S` | 保存當前設置 |
| `Esc` | 關閉彈窗/返回 |

---

## 六、技術架構

```python
# 技術棧
- textual >= 0.52.0       # TUI 框架
- httpx                    # HTTP 請求 Qdrant API
- json, pathlib            # 標準庫

# 文件結構
tui/
├── app.py                 # 主 App 入口
├── screens/
│   ├── dashboard.py       # 儀表板
│   ├── search.py          # 搜索界面
│   ├── save.py            # 保存界面
│   ├── stats.py           # 統計界面
│   └── settings.py        # 設置界面
├── widgets/
│   ├── status_bar.py      # 頂欄/底欄
│   ├── collection_table.py # Collection 表格
│   └── memory_detail.py   # 記憶詳情彈窗
├── api/
│   ├── qdrant_client.py   # Qdrant HTTP API 封裝
│   └── scanner_status.py  # Scanner 狀態讀取
└── config.py              # 配置管理
```

---

## 七、安裝依賴（更新）

```bash
# Tier 0 + TUI（僅監控，無向量功能）
pip install memory-hub[tui]

# Tier 1 + TUI
pip install memory-hub[tui]        # 含 textual + sqlite-vec + sentence-transformers

# Tier 2 + TUI
pip install memory-hub[full,tui]   # 含全部
```

---

## 八、設計原則

- **可選組件**：不啟動 TUI 時，daemon 照常運行
- **零干擾**：TUI 通過 HTTP API 查詢，不干擾 daemon
- **即裝即用**：`memory-hub tui` 一條命令啟動
- **鍵盤優先**：所有操作可通過鍵盤完成，無需滑鼠
