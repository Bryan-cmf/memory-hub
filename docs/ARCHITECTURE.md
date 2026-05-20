# MemoryHub v2.0 — Architecture

> Version: 2.0.0 | Date: 2026-05-20

## Design Philosophy

**Text + Vector + Time > Text alone.**
Files are Source of Truth, vector memory is the semantic index, time layers are the lifecycle skeleton.

## System Architecture

```
AI Platforms (OpenClaw / Hermes / DeepSeek / Claude Code)
        │                          │
        │ MODE B: File scan        │ MODE A: MCP real-time
        │ (every 5 min)            │ (instant via /hook)
        ▼                          ▼
   Capture Daemon (:3872) ──── Qdrant Vector DB (:6333)
        │                          │
   Dashboard (:3872)          MCP Server (stdio)
   • Live feed                • mem_save / mem_search
   • 24h/7d charts            • mem_stats / capture_send
   • Global search             • 4 per-platform collections
   • Collection stats
```

## Core Components

### Capture Daemon (`memory_hub/daemon.py`)

Single unified daemon handling:
- **Mode A (MCP real-time)**: Accepts capture via POST `/hook`, triggered when any platform calls MCP tools
- **Mode B (filesystem scan)**: Scans 4 platform session directories every 5 minutes, incremental via file offsets
- **Dashboard**: Built-in HTTP server on port 3872 with 6 API endpoints
- **State management**: In-memory state + persistent offset tracking for incremental scanning

### MCP Server (`memory_hub/server/mcp_server.py`)

JSON-RPC stdio server with 6 tools:
- `mem_save` — Save memory to Qdrant + notify daemon
- `mem_search` — Semantic similarity search
- `mem_stats` — Collection statistics
- `mem_list_collections` — List all collections
- `mem_delete` — Delete a memory entry
- `capture_send` — Explicit conversation capture

### CLI (`memory_hub/cli.py`)

```bash
memory-hub setup    # Interactive installer
memory-hub start    # Start daemon
memory-hub status   # System health
memory-hub stop     # Stop daemon
memory-hub verify   # Health verification
memory-hub backup   # Run backup
```

## Data Flow

```
1. User chats with AI agent
2. Agent's session file updated (JSONL/JSON)
3. Daemon Mode B scanner picks up new lines (≤5 min delay)
   OR Agent calls MCP tool → Mode A instant capture
4. Content parsed, role extracted (user/assistant)
5. Capture saved to ~/.memory-hub/captured/<platform>/YYYY/MM/DD.jsonl
6. Vector embedding generated via BGE-m3 (local inference)
7. Stored in Qdrant collection for semantic search
8. Dashboard updated in real-time
```

## Platform Parsers

| Platform | Parser | Format | Notes |
|----------|--------|--------|-------|
| OpenClaw | `_scan_file` | JSONL | type="message" with content blocks |
| Hermes | `_scan_file` | JSONL | role/content per line |
| DeepSeek | `_scan_deepseek_checkpoint` | JSON | messages array with content blocks |
| Claude Code | `_scan_file` | JSONL | event log format; MCP for best results |

## Storage Layout

```
~/.memory-hub/
├── capture_daemon_state.json   # Live daemon state
├── capture_offsets.json         # Per-file byte/message offsets
├── captured/                    # All captures (Source of Truth)
│   ├── openclaw/YYYY/MM/DD.jsonl
│   ├── hermes/YYYY/MM/DD.jsonl
│   ├── deepseek/YYYY/MM/DD.jsonl
│   └── claude/YYYY/MM/DD.jsonl
├── memories/                    # MCP-saved memories
│   └── <uuid>.json
└── hooks/                       # Hook log
```

## Deduplication (3-layer)

1. **Layer A**: UUID5 content-based dedup
2. **Layer B**: Offset-based incremental scan (only scan new content)
3. **Layer C**: Cross-session similarity dedup (>85%)

## Lifecycle

```
Daily raw logs → Weekly digest → Monthly summary → Yearly review → Decade archive
       ↓              ↓               ↓               ↓               ↓
   Never deleted   Key events     Milestones      Year review     Long-term trends
```

## Tech Stack

- **Language**: Python 3.9+
- **Vector DB**: Qdrant (Docker, primary)
- **Embedding**: BGE-m3 (local, via sentence-transformers)
- **Full-text**: SQLite (built-in)
- **API**: HTTP (stdlib http.server)
- **MCP**: JSON-RPC stdio
- **Auto-start**: launchd (macOS) / systemd (Linux)
