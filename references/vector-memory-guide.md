# Vector Memory Guide — 向量記憶 API 使用指南

> 適用於 MemoryHub Tier 1-3

---

## MCP 工具列表

### mem_save — 保存記憶

```
參數：
  collection (str, optional) — 集合名稱，默認 "openclaw_mem"
  content (str, required) — 記憶內容
  tags (list[str], optional) — 標籤，如 ["project:hk-stock", "date:2026-05-18"]
  metadata (dict, optional) — 附加元數據
```

**示例**：
```json
{
  "collection": "openclaw_mem",
  "content": "今日完成 Cellfie Global CEO 盡職調查，產出 3 份 PDF：DD報告、融資方案、交叉驗證。關鍵發現：CEO 背景為半導體行業，公司主營跨境電商物流。",
  "tags": ["調研", "盡職調查", "project:cellfie", "date:2026-05-18"],
  "metadata": {
    "session_id": "859ca859",
    "channel": "whatsapp",
    "files": ["cellfie_dd.pdf", "cellfie_financing.pdf", "cellfie_crosscheck.pdf"]
  }
}
```

### mem_search — 語義搜索

```
參數：
  query (str, required) — 搜索查詢
  collection (str, optional) — 集合名稱
  limit (int, default 10) — 最大返回數
  tags (list[str], optional) — 標籤過濾
```

**示例**：
```json
{
  "query": "上週的化工廠盡職調查報告",
  "collection": "openclaw_mem",
  "limit": 5,
  "tags": ["調研"]
}
```

**返回**：
```json
[
  {
    "rank": 1,
    "score": 0.8734,
    "content": "完成德馳投資6182.HK化工廠盡調...",
    "tags": ["調研", "化工"],
    "created_at": "2026-05-15T14:30:00"
  }
]
```

### mem_stats — 統計

```
參數：collection (str, required)
返回：{points_count, indexed_vectors_count, status, config}
```

### mem_list_collections — 列出集合

```
無參數
返回：[{name, points_count, status}]
```

### mem_delete — 刪除記憶

```
參數：collection (str), point_id (str)
返回：確認訊息
```

---

## 標籤最佳實踐

| 標籤類型 | 格式 | 示例 |
|---------|------|------|
| 日期 | `date:YYYY-MM-DD` | `date:2026-05-18` |
| 項目 | `project:名稱` | `project:hk-stock-dd` |
| 類型 | 任務類型 | `調研`, `決策`, `踩坑`, `會議` |
| 渠道 | `channel:名稱` | `channel:whatsapp` |
| 優先級 | `priority:high` | `priority:critical` |

---

## 搜索技巧

1. **用自然語言**：不需要關鍵詞，直接描述你想找什麼
2. **加標籤縮小範圍**：`tags=["project:cellfie"]` 只搜該項目
3. **檢查分數**：score > 0.8 高度相關，0.6-0.8 可能相關，<0.6 弱相關
4. **跨 Collection 搜索**：不指定 collection 或輪詢多個
