# 🔧 Troubleshooting

## Daemon not starting

**Symptom:** `memory-hub start` fails or daemon crashes

```bash
# Check log
cat ~/.memory-hub/capture_daemon.log

# Common causes:
# 1. Port 3872 already in use
lsof -i :3872

# 2. Python dependencies missing
pip install -r requirements.txt
```

## Qdrant not connecting

**Symptom:** "Qdrant unavailable" in dashboard

```bash
# Check Docker
docker ps | grep qdrant

# Start Qdrant
docker run -d --name mh-qdrant -p 6333:6333 qdrant/qdrant

# Verify
curl http://localhost:6333/health
```

## Dashboard shows 0 captures

**Symptom:** Mode A and Mode B both show 0

**Explanation:** The daemon only counts captures during its current run. If no new conversations have occurred since the daemon started, 0 is correct.

**Verify:**
```bash
# Check daemon state
curl http://localhost:3872/api/state

# Send a test capture via MCP hook
curl -X POST http://localhost:3872/hook \
  -H "Content-Type: application/json" \
  -d '{"platform":"test","role":"user","content":"Test capture"}'
```

## MCP tools not appearing

**Symptom:** Agent says "unknown tool: mem_save"

1. Verify MCP config:
```bash
memory-hub verify
```

2. Restart the platform:
```bash
openclaw gateway restart
# or close/reopen DeepSeek TUI / Claude Code
```

3. Check if MCP server works:
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python3 -m memory_hub.server.mcp_server
```

## Platform not detected

**Symptom:** Installer says "Not found" for a platform you have

Create the config directory manually:
```bash
mkdir -p ~/.hermes   # for Hermes
mkdir -p ~/.deepseek  # for DeepSeek
# etc.
```

Then re-run the installer or configure MCP manually (see [MCP_SETUP.md](MCP_SETUP.md)).

## Port conflicts

**Symptom:** "Address already in use" errors

MemoryHub uses these ports:
- `3872` — Dashboard + API
- `6333` — Qdrant

Change the dashboard port:
```bash
memory-hub start --port 3880
```

## Reset everything

```bash
# Stop daemon
memory-hub stop

# Remove Qdrant data
docker rm -f mh-qdrant
docker volume rm mh-qdrant-data

# Clear capture data
rm -rf ~/.memory-hub/captured/*
rm -rf ~/.memory-hub/capture_offsets.json

# Reinstall
pip uninstall memory-hub -y
pip install memory-hub
memory-hub setup
```

## Still stuck?

Run full verification and share the output:
```bash
memory-hub verify
```

Check logs:
```bash
cat ~/.memory-hub/capture_daemon.log
curl http://localhost:3872/api/state
```
