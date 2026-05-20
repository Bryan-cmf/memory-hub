# 🧠 MemoryHub User Guide

## Overview

MemoryHub captures conversations from your AI platforms and stores them for semantic search, auto-summarization, and decade-scale memory retention.

## How It Works

```
You chat with AI → MemoryHub captures → Dashboard shows live feed
                        ↓
                 Qdrant vector DB
                        ↓
              Semantic search across all history
```

## Dashboard

Open http://localhost:3872 in your browser.

| Section | Shows |
|---------|-------|
| **Stats Bar** | Today's captures, MCP vs file scan, scan cycles, Qdrant points, uptime |
| **Platform Cards** | Per-platform capture count, tracked files, progress bars |
| **Charts** | 24-hour hourly or 7-day daily capture trends |
| **Live Feed** | Real-time stream of captured conversations |
| **Search** | Full-text search across all captured memories |

### Reading the Dashboard

- **Mode A (MCP)**: Captures from real-time MCP tool calls — instant
- **Mode B (Scan)**: Captures from filesystem scanning — up to 5 min delay
- **Red number (0)**: Normal after daemon restart — will grow as new conversations happen
- **Progress bar**: Shows how many tracked files have produced captures this session

## Available Memory Tools

When MCP is configured, your AI agents get these tools:

| Tool | What It Does | Example |
|------|-------------|---------|
| `mem_save` | Save an insight to memory | "Remember: client prefers email on Fridays" |
| `mem_search` | Semantic search all memories | "Find the DD report from last month" |
| `mem_stats` | See collection sizes | "How many memories do we have?" |
| `capture_send` | Explicit capture to dashboard | Send a conversation snippet |

## Search Syntax

Via the dashboard search box or `mem_search` tool:

```
"exact phrase"       # Phrase match
project:cellfie      # Filter by project
2026-05              # Filter by month
```

## Auto-Start

### macOS
```bash
cp scripts/com.memoryhub.capture-daemon.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.memoryhub.capture-daemon.plist
```

### Linux
```bash
sudo cp scripts/systemd/memoryhub-capture-daemon.service /etc/systemd/system/
sudo systemctl enable --now memoryhub-capture-daemon
```

## Backup

```bash
memory-hub backup --tier hourly    # Every hour
memory-hub backup --tier daily     # Daily snapshot
memory-hub backup --tier weekly    # Weekly archive
```

Backups are stored in `~/.memory-hub/backups/`.

## Data Locations

| Path | Contains |
|------|----------|
| `~/.memory-hub/captured/` | All captured conversations (Source of Truth) |
| `~/.memory-hub/memories/` | MCP-saved memories |
| `~/.memory-hub/capture_offsets.json` | Scan position tracking |
| `~/.memory-hub/capture_daemon_state.json` | Live daemon state |

## Health Check

```bash
memory-hub verify
```

Checks: Qdrant, daemon, dashboard, MCP server, file storage, and all 4 platform MCP configs.

## Upgrading

```bash
pip install --upgrade memory-hub
memory-hub setup    # Re-run to update configs
```

## See Also

- [Installation Guide](../INSTALL.md)
- [Architecture](ARCHITECTURE.md)
- [MCP Setup](MCP_SETUP.md)
- [Troubleshooting](TROUBLESHOOTING.md)
