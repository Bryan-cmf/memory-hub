# Contributing to MemoryHub

## Quick Start

```bash
git clone https://github.com/bryan-cmf/memory-hub.git
cd memory-hub
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[full]"
```

## Project Structure

```
MemoryHub/
├── capture_daemon.py      # Main daemon (port 3872)
├── scanner/               # Session JSONL scanner
├── server/                # MCP server (5 tools)
├── tui/                   # Terminal UI
├── backend_installer.py   # Database installer
├── backup_daemon.py       # Backup system
└── references/            # Design docs
```

## Running Tests

```bash
python3 test_capture.py
python3 test_hub.py
python3 test_memoryhub.py
```

## PR Guidelines

1. All Python files must pass `ast.parse()` syntax check
2. New features should have corresponding tests
3. Keep dependencies minimal (stdlib preferred)
4. Dashboard HTML/CSS must match existing style
