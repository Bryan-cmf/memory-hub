# Changelog

## v2.0.0 — Production Release (2026-05-20)

### Major
- **Python package structure** (`memory_hub/`): pip installable, CLI entry point
- **CLI** (`memory-hub`): setup/start/status/stop/verify/backup commands
- **Unified installer** with interactive TUI wizard (Phase 1-6)
- **Enhanced Dashboard**: 6 API endpoints, 24h/7d charts, global search, collection stats
- **MCP integration**: Real-time Mode A capture via daemon /hook, 6 tools
- **One-command install**: `pip install memory-hub && memory-hub setup`

### Fixed
- DeepSeek parser: tool_result/tool_use block content extraction
- Claude Code: scan paths expanded from 1 to 6 directories (15→42 tracked files)
- Hermes: parser switched from checkpoint to line-by-line JSONL
- HTTP routing: path matching via urlparse (query string handling)
- Multiple hidden bugs: subprocess import, HOOK_LOG_DIR, offset tracking

### Documentation
- New: USER_GUIDE.md, MCP_SETUP.md, TROUBLESHOOTING.md, INSTALL.md
- Updated: README.md, ARCHITECTURE.md (v2.0), QUICKSTART.md, API.md
- Cleaned: removed v1.x development reports

### Infrastructure
- macOS LaunchAgent: de-hardcoded paths, corrected port (3872)
- Linux systemd: new service file
- Docker Compose: updated to reference capture_daemon
- MCP config snippets: added DAEMON_HOOK_URL
- requirements.txt + pyproject.toml updates

## v1.2.0 — Hook Upgrade (2026-05-19)

### Added
- Dual-mode capture daemon (`capture_daemon.py`): MODE A (MCP) + MODE B (filesystem)
- Dashboard (`http://localhost:3872`): 4-platform real-time monitor
- Capture state persistence (`capture_state.json`)
- Capture file layer (`~/.memory-hub/captured/{platform}/YYYY/MM/DD.jsonl`)
- launchd config (`scripts/com.memoryhub.capture-daemon.plist`)
- 4-platform MCP configs
- 3-layer dedup: UUID5 + Offset + Semantic similarity
- 3-layer guard: Qdrant + Daemon + Scanner health monitoring
- Crash recovery: checkpoint persistence
