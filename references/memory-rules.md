# Memory Rules — 記憶寫入規則

> 來源：OpenClaw MEMORY-SYSTEM.md（2026-05-10 建立）
> 移植到 MemoryHub 作為 Tier 0 的行為規範

---

## 五條核心規則

### Rule 1: 即時寫入（做咗就寫）
**觸發條件：** 完成任何有意義的任務
```
完成任務 → 更新 daily log → 如踩坑 → 同步寫 lessons
```

### Rule 2: Session 結束前 Checkpoint
**觸發條件：** 對話臨結束 / 感覺快做完了
```
回顧本 session 做過的事 → 寫入 daily log → 重要項目 → 更新 projects/
```

### Rule 3: 長 Session 自動 Checkpoint
**觸發條件：** 同一 session 運行 >2 小時
```
每 2 小時 → 寫一次 progress update 到 daily log
```

### Rule 4: 踩坑必記錄
**觸發條件：** 發現錯誤 / 失誤 / 教訓
```
發現踩坑 → 寫 lessons/ → 更新 lessons/index.md
```

### Rule 5: 每日反思
**觸發條件：** 每日結束前
```
讀取今日 daily log → 提煉：犯錯 / 進步 / 未解決 → 有值得長記的 → 更新 MEMORY.md
```

---

## 文件格式

### 每日日志（daily/YYYY-MM-DD.md）
```markdown
# YYYY-MM-DD 工作日誌

## 🎯 今日完成
## 🔥 重點項目進度
## 💬 重要對話 / 指示
## 📌 待辦事項
```

### 踩坑日志（lessons/YYYY-MM-DD-topic.md）
```markdown
# 坑：[簡短標題]
- 發生時間 | 情況描述 | 根本原因 | 解決方案 | 教訓
```

### 項目記憶（projects/PROJECT.md）
```markdown
# PROJECT — 項目記憶
## 概要 | 最近進度 | 踩過的坑 | 重要決策 | 待辦事項
```

---

## 關鍵提醒

1. **永遠唔好依賴 session log** — 下次 session 唔會自動讀
2. **做咗嘢就要寫低** — 否則等於冇做過
3. **踩坑比成功更重要** — 記住錯誤先至唔會再犯
4. **每日反思係習慣** — 好似人類瞓覺前諗返今日做過咩
