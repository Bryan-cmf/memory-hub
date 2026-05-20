# 🧠 MemoryHub — Persistent Memory Enhancement System

> Vector semantic memory + Multi-platform auto-capture + Decade-scale lifecycle
> Version: 2.0.0 | License: MIT

## One-Liner

**Cure Agent amnesia.** A fourth-layer enhancement to existing memory systems — vector search + session scanning + decade-scale lifecycle.

## Quick Start

```bash
# One-command install
pip install memory-hub

# Interactive setup
memory-hub setup

# Start daemon
memory-hub start

# Open dashboard
open http://localhost:3872
```

## Why MemoryHub?

| Problem | Current | MemoryHub Solution |
|---------|---------|-------------------|
| Agent forgets daily log | High task density | Auto-capture from 4 platforms |
| Cross-session amnesia | Blank slate each session | Vector search across time |
| Non-main sessions ignored | WhatsApp etc. no rules | Daemon scans all platforms |
| Memories fade over time | Old buried by new | Consolidate, never delete |

## Architecture

```
AI Platforms (OpenClaw / Hermes / DeepSeek / Claude)
        │                          │
        │ MODE B: File scan        │ MODE A: MCP real-time
        ▼                          ▼
   Capture Daemon ──────── Qdrant Vector DB
        │                    (localhost:6333)
        │
   Dashboard (:3872)    MCP Server (6 tools)
```

## Commands

```bash
memory-hub setup       # Interactive installation wizard
memory-hub start       # Start the capture daemon
memory-hub status      # Show system health
memory-hub stop        # Stop the daemon
memory-hub verify      # Run verification checks
memory-hub backup      # Run backup
```

## Supported Platforms

| Platform | Capture Mode | Format |
|----------|:---:|--------|
| 🦙 OpenClaw | Auto-scan + MCP | JSONL |
| 🪽 Hermes | Auto-scan + MCP | JSONL |
| 🐋 DeepSeek TUI | Auto-scan + MCP | JSON |
| 🦫 Claude Code | Auto-scan + MCP | JSONL |

## Backends

| Backend | Required | Install | Purpose |
|---------|:---:|---------|---------|
| 💾 File System | ✅ | Built-in | Source of Truth |
| 🗄️ SQLite | ✅ | Built-in | Metadata + full-text index |
| 🧠 Qdrant | ✅ | Docker | Vector search (primary) |
| 📦 Chroma | Optional | pip | Lightweight vector (no Docker) |
| 🪶 LanceDB | Optional | pip | Embedded vector (lightest) |

## Key Features

- 🔍 **Semantic search** — "last month's DD report" not grep
- 📡 **4-Platform capture** — OpenClaw / Hermes / DeepSeek / Claude
- 🧠 **Vector memory** — Qdrant + BGE-m3, local inference
- 🛡️ **3-tier backup** — hourly / daily / weekly
- 📊 **Live Dashboard** — `:3872` real-time feed + charts + search
- 🔌 **MCP Integration** — 6 tools, Mode A real-time capture
- 🌐 **Decade memory** — daily → weekly → monthly → yearly consolidation

## Documentation

| Guide | File |
|-------|------|
| Quick Start | [QUICKSTART.md](QUICKSTART.md) |
| Installation | [INSTALL.md](INSTALL.md) |
| User Guide | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) |
| Architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| MCP Setup | [docs/MCP_SETUP.md](docs/MCP_SETUP.md) |
| API Reference | [API.md](API.md) |
| Troubleshooting | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |

## License

MIT © Bryan Chan
