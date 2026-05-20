# 知識圖譜設計 — Knowledge Graph Design

> 靈感來源：agentmemory 的 entity extraction + typed relationships
> 目標：讓記憶之間產生關聯，而不只是堆積

---

## 為什麼需要知識圖譜？

```
沒有圖譜的記憶搜索：
  「Qdrant 為什麼被選中？」→ grep "Qdrant" → 找到很多提及，但不知道哪次是決定

有圖譜的記憶搜索：
  「Qdrant 為什麼被選中？」→ 查 entities/decisions.md → 找到結構化記錄：
  - 時間：2026-05-12
  - 背景：需要向量數據庫做語義搜索
  - 選項：Chroma、Milvus、Qdrant、Weaviate
  - 選擇：Qdrant
  - 原因：Rust 原生高效、on_disk 省 RAM、Docker 一鍵部署
  - 決策人：Bryan
  - 相關記憶：memory/2026/05/12.md, memory/2026/05/_weekly-05-12.md
```

---

## 實體類型

### people.md — 人物圖譜

```markdown
# 人物圖譜

## 王總
- **角色**：投資決策人
- **首次出現**：2026-03-15（飛書，討論港股調研方向）
- **溝通偏好**：喜歡表格、時間線、不喜歡長篇文字
- **決策風格**：快速判斷，需要數據支持
- **關鍵互動**：
  - 2026-04-21：要求 IPO 報告包含時間表 → [daily/04-21.md]
  - 2026-05-18：Cellfie Global 盡調指示（WhatsApp）→ [session:859ca859]
- **相關項目**：hk-stock-dd, cellfie-financing
- **備註**：重要決策最好準備 3 個選項供選擇
```

### projects.md — 項目時間線

```markdown
# 項目圖譜

## hk-stock-dd（港股盡職調查系統）
- **狀態**：活躍
- **創建**：2026-04-15
- **目標**：自動化港股 IPO 調研流程
- **關鍵里程碑**：
  - 2026-04-21：加入 Tavily 強制搜索 → [decision:D-20260421]
  - 2026-05-10：建立記憶系統防止失憶 → [decision:D-20260510]
  - 2026-05-12：選擇 Qdrant 為向量數據庫 → [decision:D-20260512]
  - 2026-05-19：MemoryHub 開源項目啟動
- **技術棧**：Python, Qdrant, BGE-m3, MCP
- **踩坑記錄**：see entities/lessons.md #2, #25
```

### decisions.md — 決策日誌

```markdown
# 決策日誌

## D-20260512：選擇 Qdrant 為向量數據庫
- **時間**：2026-05-12
- **背景**：需要向量數據庫支持語義記憶搜索
- **選項**：
  | 選項 | 優點 | 缺點 | 結論 |
  |------|------|------|------|
  | Chroma | Python 原生 | 僅 Python，無 Rust API | ❌ |
  | Milvus | 功能最全 | 過重，需 Kubernetes | ❌ |
  | Qdrant | Rust 原生、on_disk、Docker | 需 Docker | ✅ |
  | Weaviate | GraphQL 支持 | 開源版功能受限 | ❌ |
- **選擇**：Qdrant
- **原因**：Rust 原生高效、on_disk 模式節省 Apple Silicon RAM、Docker 一鍵部署
- **決策人**：Bryan
- **相關記憶**：[daily/05-12.md], [weekly/05-12.md]
- **狀態**：已實施

## D-20260519：採用濃縮而非遺忘策略
- **時間**：2026-05-19
- **背景**：設計十年記憶系統，需決定是否引入遺忘機制
- **選擇**：濃縮而非遺忘（不同於 agentmemory 的做法）
- **原因**：十年尺度的記憶不應丟失任何歷史事實
- **參考**：agentmemory 的 lifecycle management 設計
```

### lessons.md — 跨年教訓

```markdown
# 跨年教訓

## 記憶系統
- **L-20260510**：做完不寫 = 沒做過。Agent 必須在任務完成後立即寫入記憶
- **L-20260517**：三層防護可能同時失效。記憶系統不能依賴 Agent 自覺
- **L-20260518**：計數 ≠ 記錄。autocheck 知道 session 存在 ≠ 知道內容
- **L-20260518**：跨 session 規則不能依賴繼承。系統級掃描是唯一解法

## 項目管理
- ...（按領域分類）
```

---

## 關係類型

| 關係 | 語義 | 示例 |
|------|------|------|
| `requested_by` | 誰發起 | 盡調報告 requested_by 王總 |
| `produced` | 產出 | 調研 produced 3份PDF |
| `depends_on` | 依賴 | DD系統 depends_on 記憶系統 |
| `supersedes` | 取代 | D-20260519 supersedes D-20260512 |
| `related_to` | 相關 | 記憶黑洞 related_to WhatsApp session |
| `caused_by` | 根因 | 失憶 caused_by 沒寫daily log |

---

## 自動提取規則

Scanner 在掃描 JSONL 對話時，檢測以下模式自動提取實體：

```
「幫我做 [項目名] 的 [任務類型]」 → Project
「發給 [人名]」→ Person  
「產出 [文件名]」→ File
「我們決定 [選擇] 而不是 [替代方案]」→ Decision
「踩坑了，[錯誤描述]」→ Lesson
```

---

## 混合搜索 API

```
mem_search(
    query="過去半年關於緩存的決策",
    since="2026-01-01",
    entities=["Project:agentics-website"],
    relations=["depends_on", "supersedes"],
    limit=10
)

返回路徑合併：
1. 向量搜索 → 語義相關記憶
2. 實體圖遍歷 → 通過關係鏈接的記憶
3. 時間過濾 → 只返回指定時間範圍
```
