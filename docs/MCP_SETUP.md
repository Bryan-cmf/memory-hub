# 📡 MCP Setup Guide

MemoryHub uses **MCP (Model Context Protocol)** for real-time memory capture (Mode A).

When an AI agent calls a MemoryHub MCP tool (e.g., `mem_save`), the conversation is automatically captured and displayed on the Dashboard.

## Quick Setup

Run the interactive installer — it auto-detects your platforms and configures MCP:

```bash
memory-hub setup
```

## Manual Setup

### OpenClaw

Edit `~/.openclaw/openclaw.json`, add under `mcp.servers`:

```json
"memory-hub": {
  "command": "python3",
  "args": ["-m", "memory_hub.server.mcp_server"],
  "env": {
    "EMBEDDING_MODEL": "BAAI/bge-m3",
    "QDRANT_URL": "http://localhost:6333",
    "MEMORY_COLLECTION": "openclaw_mem",
    "DAEMON_HOOK_URL": "http://localhost:3872/hook"
  }
}
```

### DeepSeek TUI

Edit `~/.deepseek/mcp.json`:

```json
"memory-hub": {
  "command": "python3",
  "args": ["-m", "memory_hub.server.mcp_server"],
  "env": {
    "EMBEDDING_MODEL": "BAAI/bge-m3",
    "QDRANT_URL": "http://localhost:6333",
    "MEMORY_COLLECTION": "deepseek_mem",
    "DAEMON_HOOK_URL": "http://localhost:3872/hook"
  }
}
```

### Hermes Agent

Edit `~/.hermes/mcp.json`:

```json
"memory-hub": {
  "command": "python3",
  "args": ["-m", "memory_hub.server.mcp_server"],
  "env": {
    "EMBEDDING_MODEL": "BAAI/bge-m3",
    "QDRANT_URL": "http://localhost:6333",
    "MEMORY_COLLECTION": "hermes_mem",
    "DAEMON_HOOK_URL": "http://localhost:3872/hook"
  }
}
```

### Claude Code

Edit `~/.claude/mcp.json`:

```json
"memory-hub": {
  "command": "python3",
  "args": ["-m", "memory_hub.server.mcp_server"],
  "env": {
    "EMBEDDING_MODEL": "BAAI/bge-m3",
    "QDRANT_URL": "http://localhost:6333",
    "MEMORY_COLLECTION": "claude_mem",
    "DAEMON_HOOK_URL": "http://localhost:3872/hook"
  }
}
```

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `mem_save` | Save a memory entry to vector database |
| `mem_search` | Semantic search across all memories |
| `mem_stats` | View collection statistics |
| `mem_list_collections` | List all memory collections |
| `mem_delete` | Delete a memory entry |
| `capture_send` | Send conversation capture to dashboard |

## Restart Platforms

⚠️ **After configuring MCP, restart each platform** to load the new MCP server:

```bash
# OpenClaw
openclaw gateway restart

# DeepSeek TUI
# Close and reopen DeepSeek TUI

# Claude Code
# Close and reopen Claude Code session

# Hermes
# Restart your Hermes instance
```

## Verification

Run the verification tool to check MCP status:

```bash
memory-hub verify
```

Expected output:

```
  ✅ MCP: OpenClaw: configured
  ✅ MCP: DeepSeek: configured
  ✅ MCP: Hermes: configured
  ✅ MCP: Claude Code: configured
```

## How It Works

```
AI Agent calls mem_save("important insight")
        │
        ▼
MCP Server processes the request
        │
        ├──▶ Qdrant vector DB (semantic storage)
        │
        └──▶ POST /hook to Daemon (Mode A capture)
                │
                ▼
        Dashboard shows real-time capture
```

Mode A (MCP real-time) and Mode B (filesystem scan every 5 minutes) complement each other — you get both instant MCP captures and automatic background scanning.
