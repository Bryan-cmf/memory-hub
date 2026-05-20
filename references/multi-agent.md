# Multi-Agent Memory Protocol (6.1-6.4)

> 多個 Agent 共享記憶時的隔離、同步與權限規範

---

## 6.1 Collection 隔離策略

每個 Agent 擁有獨立的 Qdrant collection，記憶不混淆：

| Collection | Agent | 寫入權 | 讀取權 |
|-----------|-------|--------|--------|
| `openclaw_mem` | OpenClaw Main Agent (飛書) | ✅ | ✅ |
| `hermes_mem` | Hermes Agent | ✅ | ✅ |
| `deepseek_mem` | DeepSeek TUI Agent | ✅ | ✅ |
| `shared_mem` | 所有 Agent | 需審批 | ✅ |
| `project_mem` | 項目特定 Agent | ✅ | ✅ |

## 6.2 跨 Agent 記憶共享

```
Agent A 查詢：「有冇 Agent B 做過類似的工作？」

1. mem_search(query="...", collection="*")
2. 返回所有 collection 中的相關記憶
3. 標記來源 collection（openclaw_mem / hermes_mem / shared_mem）
```

## 6.3 記憶同步協議

Agent A 完成重要任務後：
```
1. 寫入自己的 collection (openclaw_mem)
2. 判斷是否需要共享：
   - 決策記錄 → mem_save(collection="shared_mem")
   - 踩坑教訓 → mem_save(collection="shared_mem")
   - 項目進度 → 更新 entities/projects.md（所有 Agent 共享檔案）
```

## 6.4 權限隔離

- Scanner 只讀取 `workspace/memory/` 路徑 → 不能訪問系統文件
- Agent 只能 `mem_save` 到自有 collection + shared_mem
- `mem_delete` 需要確認彈窗
- 檔案層是最終 Source of Truth，向量層可隨時重建
