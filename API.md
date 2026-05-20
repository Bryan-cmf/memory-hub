# MemoryHub API Reference

Dashboard runs on `http://localhost:3872`. All endpoints return JSON unless noted.

## Endpoints

### GET /

Returns the Dashboard HTML page.

### GET /api/state

Current daemon state.

```json
{
  "total_captured": 42,
  "mode_a_count": 5,
  "mode_b_count": 37,
  "scan_cycle": 12,
  "last_scan": "2026-05-20T14:00:00+08:00",
  "platforms": {
    "openclaw": {"captured": 20, "files": 680, "last_preview": "..."},
    "hermes":   {"captured": 10, "files": 412, "last_preview": "..."},
    "deepseek": {"captured": 5,  "files": 6,   "last_preview": "..."},
    "claude":   {"captured": 7,  "files": 42,  "last_preview": "..."}
  },
  "recent": [{"platform": "...", "role": "user", "content": "...", "time": "..."}]
}
```

### GET /api/messages?limit=100

Recent captured messages (reverse chronological). Default limit: 100.

### GET /api/search?q=<query>&limit=10

Full-text search across all captured memories. Searches both capture files and MCP-saved memories.

### GET /api/history

Historical capture counts.

```json
{
  "hourly": {"05-20 14:00": {"openclaw": 3, "hermes": 1}},
  "daily":  {"05-20": {"openclaw": 20, "hermes": 10}},
  "uptime_hours": 2.5
}
```

### GET /api/collections

Qdrant collection sizes.

```json
{
  "openclaw_mem": 1480,
  "hermes_mem": 0,
  "deepseek_mem": 0,
  "claude_mem": 0,
  "shared_mem": 0
}
```

### POST /hook

Mode A capture endpoint. Called by MCP server on tool use.

```bash
curl -X POST http://localhost:3872/hook \
  -H "Content-Type: application/json" \
  -d '{"platform":"openclaw","role":"user","content":"Hello"}'
```

Response: `{"status":"captured"}`

## MCP Server (JSON-RPC stdio)

The MCP server runs as a subprocess of each AI platform. It implements the Model Context Protocol over stdio.

### Tools

| Tool | Arguments | Returns |
|------|-----------|---------|
| `mem_save` | `{collection?, content, tags?, metadata?}` | `{status, point_id, preview}` |
| `mem_search` | `{collection?, query, limit?, tags?}` | `{results: [{score, content, point_id}]}` |
| `mem_stats` | `{collection?}` | `{points_count, status}` |
| `mem_list_collections` | `{}` | `{collections: [{name}]}` |
| `mem_delete` | `{collection, point_id}` | `{status, vector_deleted, file_deleted}` |
| `capture_send` | `{platform, role, content}` | `{status, preview}` |

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | Sentence transformer model |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant connection |
| `MEMORY_COLLECTION` | `openclaw_mem` | Default collection |
| `DAEMON_HOOK_URL` | `http://localhost:3872/hook` | Mode A capture notification |
| `SIMILARITY_THRESHOLD` | `0.6` | Minimum search score |
