# Cross-Session Memory Strategy — 跨 Session 記憶策略

## 核心命題

> **問題不在「Agent 記性不好」，問題在「記憶系統的核心輸入源是 Agent 手動操作」。**
>
> 只要記憶系統依賴任何 Agent 主動寫入，就永遠存在遺漏風險。

---

## 三種記憶黑洞（實證）

### 黑洞 1：同 Session 忘記（坑 #2, 2026-05-17）

```
症狀：Agent 在連續 6 項任務後忘記寫 daily log
根因：任務密度太高，meta-task「寫記憶」被擠出注意力
失效鏈：Layer 1 失效 → Layer 2 跟著失效 → Layer 3 無法定義觸發
```

### 黑洞 2：跨 Session 根本不知道（坑 #25, 2026-05-18）

```
症狀：WhatsApp session 獨立喚醒，不繼承飛書 session 的記憶規則
數據：32 次 tool call、3 份 PDF（3.6MB）、0 次 write
根因：純結構性——prompt 無法解決跨 session 問題
```

### 黑洞 3：計數 ≠ 記錄（坑 #25）

```
症狀：autocheck 知道 session 859ca859 存在（"8 REAL_USER"）
      但不知道裡面說了什麼
根因：計數型監控 ≠ 內容提取型監控
```

---

## MemoryHub 的跨 Session 策略

### 策略 1：系統級 JSONL 掃描（主力）

```
不依賴 Agent：
  session_scanner 直接讀取 Gateway 自動寫入的 session JSONL
  → Agent 根本無法阻止、無法遺漏、無法干預

覆蓋所有渠道：
  飛書 JSONL / WhatsApp JSONL / Discord JSONL 全部掃描

增量掃描：
  維護 scan_state.json → 每次只處理新行 → 零重複
```

### 策略 2：跨 Collection 搜索

```
用戶問「之前做過什麼？」：
  → mem_search(query) 跨所有 collection
  → 返回按時間排序的相關記憶
  → Agent 看到跨 session 的完整上下文
```

### 策略 3：規則不依賴繼承

```
錯誤做法：
  讓每個非主 session 的 Agent 都記住記憶規則
  → prompt 膨脹、模型差異、session 隔離

正確做法：
  系統層 session_scanner 自動提取
  → 不依賴 Agent 知道規則
  → 不依賴 Agent 執行規則
```

---

## 實施檢查清單

```
☐ session_scanner 正在運行？（guard.sh 確認）
☐ scan_state.json 今日有更新？
☐ 各渠道 session JSONL 目錄已配置？
☐ mem_search 可正常返回跨 session 結果？
☐ 無 Gateway API 依賴？（純檔案系統掃描）
```
