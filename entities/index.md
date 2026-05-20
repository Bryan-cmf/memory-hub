# MemoryHub Entities

以下實體文件由 MemoryHub Scanner 自動維護，按需手動補充。

- [people.md](people.md) — 人物圖譜（互動歷史、偏好、決策風格）
- [projects.md](projects.md) — 項目時間線（從創建到歸檔的完整生命週期）
- [decisions.md](decisions.md) — 決策日誌（背景→選項→選擇→結果，含 superseded_by）
- [lessons.md](lessons.md) — 跨年教訓（按領域分類，永不刪除）

## 自動提取規則

Scanner 在掃描 JSONL 對話時自動檢測：
- 「給 [人名] 發送」→ 更新 people.md 的互動記錄
- 「完成了 [項目名] 的 [任務]」→ 更新 projects.md 的進度
- 「決定/選擇/採用 [X] 而非 [Y]」→ 寫入 decisions.md
- 「踩坑了/[錯誤描述]/下次應該」→ 寫入 lessons.md

## 手動維護

自動提取僅覆蓋常見模式。以下情況需手動補充：
- 複合人名（如「王總經理」→ 補充為「王總」）
- 項目更名（需手動更新 projects.md 並保留舊名引用）
- 跨年決策關聯（手動添加 `superseded_by` 和 `related_to`）

*最後更新：2026-05-19*
