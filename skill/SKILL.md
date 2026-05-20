---
name: memory-hub
description: "Persistent memory enhancement system for decade-scale memory. Use when: (1) starting a session — check recent memory, (2) completing a task — save to memory, (3) searching past work, (4) making decisions — record background+options+choice+outcome, (5) learning from mistakes, (6) end of week/month/year — trigger consolidation. Trigger keywords: 記憶, remember, recall, 之前做過, 搜索記憶, mem_search, mem_save, consolidate, 濃縮, 回顧."
---

# MemoryHub — 十年持久記憶增強技能

## 目的

確保每次重要任務的上下文被持久化，支援十年尺度的記憶檢索。本技能是 Tier 0 的實現——無需安裝，純行為規範。

## Session 開始時

```
1. 讀取 MEMORY.md 了解長期背景
2. 讀取 memory/YYYY/MM/ 最近 3 天 daily logs
3. 檢查 entities/projects.md 有無相關項目
4. 如有 MCP，調用 mem_search(query="當前任務關鍵詞", limit=5)
5. 告訴用戶發現了什麼相關歷史記憶
```

## 任務完成後

```
1. 寫入 memory/YYYY/MM/DD.md（每日原始日誌）
2. 如有決策 → 寫入 entities/decisions.md
3. 如有踩坑 → 寫入 entities/lessons.md
4. 如有新人物 → 更新 entities/people.md
5. 如有 MCP → mem_save(content="摘要", tags=["類型", "date:YYYY-MM-DD"])
```

## 防遺漏檢查清單

```
☐ 今日 daily log 已更新？
☐ 新踩坑已記錄？
☐ 重要決策已寫入 entities/decisions.md？
☐ 相關人物資訊已更新 entities/people.md？
☐ 如有 MCP，重要記憶已 mem_save？
```

## 濃縮檢查清單（每週/月/年末）

```
☐ 本週 daily logs 是否需要濃縮為 _weekly.md？
☐ 本月 weeklies 是否需要濃縮為 _monthly.md？
☐ 本年 monthlies 是否需要濃縮為 _yearly.md？
☐ entities/ 文件是否需要更新（人物/項目/決策/教訓）？
```

## 記憶可靠性原則

1. **做咗就寫** — 不要等 session 結束
2. **踩坑比成功更重要** — 記錄錯誤才不會再犯
3. **搜尋先於行動** — 開始前先查歷史
4. **關聯記憶** — 發現相關歷史時主動告訴用戶
5. **濃縮而非遺忘** — 原始日誌永不刪除
6. **實體為錨點** — 人/項目/決策是跨時間坐標
7. **檔案 > 大腦** — 永遠不要只記在心裡
8. **格式永續** — 純 Markdown UTF-8，30 年可讀

## Red Flags

| ❌ | ✅ |
|----|-----|
| 假設下次 session 會記得 | 寫入文件 |
| Session 結束才補寫 | 每完成一個任務就寫 |
| 只寫做了什麼 | 也寫為什麼和學到什麼 |
| 跳過 daily log | 簡單任務也有簡單記錄 |
| 忘記濃縮 | 每週/月/年定時濃縮 |
