# MemoryHub Installation Guide

## Quick Install (recommended)

```bash
pip install memory-hub
memory-hub setup
```

That's it. The setup wizard auto-detects your environment and configures everything.

## Prerequisites

| Requirement | Check |
|-------------|-------|
| Python 3.9+ | `python3 --version` |
| pip | `pip3 --version` |
| Docker | `docker --version` (for Qdrant) |

## Interactive Setup Flow

Running `memory-hub setup` walks you through:

```
Phase 1: Environment Check
  → Detects Python, pip, Docker, git
  → Detects installed AI platforms (OpenClaw/Hermes/DeepSeek/Claude)

Phase 2: Core Components (auto-installed)
  → Qdrant (Docker) — vector search
  → SQLite — full-text index
  → MemoryHub daemon + Dashboard
  → Python dependencies

Phase 3: Optional Backends (interactive choice)
  → Chroma (pip, no Docker)
  → LanceDB (pip, embedded)
  → Press Enter to skip

Phase 4: MCP Configuration
  → Auto-writes MCP config for all detected platforms
  → Shows restart instructions

Phase 5: Verification
  → Checks Qdrant, Dashboard, file storage

Phase 6: Start daemon
  → Optional immediate daemon start
```

## Manual Start

```bash
# Start daemon on default port 3872
memory-hub start

# Custom port
memory-hub start --port 3880

# Check status
memory-hub status

# Stop
memory-hub stop
```

## Auto-Start Configuration

### macOS (launchd)

```bash
cp scripts/com.memoryhub.capture-daemon.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.memoryhub.capture-daemon.plist
```

### Linux (systemd)

```bash
sudo cp scripts/systemd/memoryhub-capture-daemon.service /etc/systemd/system/
sudo systemctl enable memoryhub-capture-daemon
sudo systemctl start memoryhub-capture-daemon
```

## Docker Compose (alternative)

```bash
docker-compose up -d
```

This starts Qdrant + the daemon in containers.

## Post-Install

1. Open Dashboard: http://localhost:3872
2. Verify: `memory-hub verify`
3. Restart your AI platforms for MCP integration
4. Start chatting — captures appear automatically!

## Uninstall

```bash
# Stop daemon
memory-hub stop

# Remove Qdrant
docker rm -f mh-qdrant

# Remove data (optional)
rm -rf ~/.memory-hub

# Uninstall package
pip uninstall memory-hub -y
```

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).
