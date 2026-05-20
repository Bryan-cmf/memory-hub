# MemoryHub Quick Start

## 30-Second Install

```bash
pip install memory-hub
memory-hub setup
```

The setup wizard auto-detects your environment, installs Qdrant, configures MCP for all your AI platforms.

## Commands

```bash
memory-hub setup       # Interactive setup wizard
memory-hub start       # Start daemon + dashboard
memory-hub status      # System health check
memory-hub stop        # Stop daemon
memory-hub verify      # Full verification
memory-hub backup      # Run backup
```

## After Install

1. **Open Dashboard:** http://localhost:3872
2. **Restart your AI platforms** for MCP integration
3. **Start chatting** — conversations auto-capture!

## What's Installed

| Component | Port | Purpose |
|-----------|------|---------|
| Qdrant | :6333 | Vector semantic search |
| Dashboard | :3872 | Live capture feed + charts |
| MCP Server | stdio | Real-time memory tools |

## Next Steps

- [Installation Guide](INSTALL.md) — full setup walkthrough
- [Architecture](docs/ARCHITECTURE.md) — system design
- [MCP Setup](docs/MCP_SETUP.md) — per-platform config
- [User Guide](docs/USER_GUIDE.md) — daily usage
- [Troubleshooting](docs/TROUBLESHOOTING.md) — common fixes
