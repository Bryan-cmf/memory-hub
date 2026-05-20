#!/usr/bin/env python3
"""MemoryHub System Verification — one-command health check."""

import json, os, sys, urllib.request
from pathlib import Path

def check(label, ok, detail=""):
    icon = "✅" if ok else "❌" if ok is False else "⚠️"
    print(f"  {icon} {label}: {detail}")

def run_verify():
    print("🔍 MemoryHub System Verification")
    print("=" * 50)

    # 1. Qdrant
    ok, detail = False, ""
    try:
        req = urllib.request.Request("http://localhost:6333/collections", method="GET")
        resp = urllib.request.urlopen(req, timeout=3)
        data = json.loads(resp.read())
        cols = data.get("result", {}).get("collections", [])
        ok = len(cols) > 0
        total_pts = 0
        if ok:
            for c in cols:
                try:
                    req2 = urllib.request.Request(f"http://localhost:6333/collections/{c['name']}", method="GET")
                    resp2 = urllib.request.urlopen(req2, timeout=3)
                    d2 = json.loads(resp2.read())
                    total_pts += d2.get("result", {}).get("points_count", 0)
                except: pass
        detail = f"{len(cols)} collections, {total_pts} points" if ok else str(data)[:40]
    except Exception as e:
        detail = str(e)[:60]
    check("Qdrant (vector DB)", ok, detail)

    # 2. Daemon
    ok, detail = False, ""
    ok, detail = False, ""
    try:
        req = urllib.request.Request("http://localhost:3872/api/state", method="GET")
        resp = urllib.request.urlopen(req, timeout=3)
        data = json.loads(resp.read())
        ok = "total_captured" in data
        total = data.get("total_captured", 0)
        detail = f"running, {total} captures" if ok else "unexpected response"
    except Exception as e:
        detail = str(e)[:60]
    check("Capture Daemon (3872)", ok, detail)

    # 3. Dashboard
    ok, detail = False, ""
    try:
        req = urllib.request.Request("http://localhost:3872/", method="GET")
        resp = urllib.request.urlopen(req, timeout=3)
        ok = resp.status == 200
        detail = f"HTTP {resp.status}" if ok else f"HTTP {resp.status}"
    except Exception as e:
        detail = str(e)[:60]
    check("Dashboard", ok, detail)

    # 4. MCP Server
    try:
        import subprocess
        r = subprocess.run(
            [sys.executable, "-c", "from memory_hub.server.mcp_server import TOOLS; print(len(TOOLS))"],
            capture_output=True, text=True, timeout=5,
            cwd=str(Path(__file__).resolve().parent.parent)
        )
        n = r.stdout.strip()
        ok = n.isdigit() and int(n) >= 5
        detail = f"v2.0.0, {n} tools" if ok else f"import failed: {r.stderr[:60]}"
    except Exception as e:
        ok = False
        detail = str(e)[:60]
    check("MCP Server", ok, detail)

    # 5. SQLite / File storage
    mh_dir = Path(os.path.expanduser("~/.memory-hub"))
    memories = mh_dir / "memories"
    ok = memories.exists()
    n = len(list(memories.glob("*.json"))) if ok else 0
    check("SQLite / File Storage", ok, f"{n} files" if ok else "not found")

    # 6. Platform MCP configs
    platforms = {
        "OpenClaw": Path(os.path.expanduser("~/.openclaw/openclaw.json")),
        "DeepSeek": Path(os.path.expanduser("~/.deepseek/mcp.json")),
        "Hermes": Path(os.path.expanduser("~/.hermes/mcp.json")),
        "Claude Code": Path(os.path.expanduser("~/.claude/mcp.json")),
    }
    for name, fp in platforms.items():
        ok = False; detail = "not found"
        if fp.exists():
            try:
                cfg = json.loads(fp.read_text(encoding="utf-8"))
                servers = cfg.get("mcp", {}).get("servers", cfg.get("servers", cfg.get("mcpServers", {})))
                ok = "memory-hub" in servers
                detail = "configured" if ok else "memory-hub not in config"
            except Exception:
                detail = "config parse error"
        else:
            detail = "config file not found"
        check(f"MCP: {name}", ok, detail)

    # 7. Collections
    print()
    print("📊 Qdrant Collections:")
    try:
        req = urllib.request.Request("http://localhost:6333/collections", method="GET")
        resp = urllib.request.urlopen(req, timeout=3)
        data = json.loads(resp.read())
        for c in data.get("result", {}).get("collections", []):
            cn = c["name"]
            try:
                req2 = urllib.request.Request(f"http://localhost:6333/collections/{cn}", method="GET")
                resp2 = urllib.request.urlopen(req2, timeout=3)
                d2 = json.loads(resp2.read())
                pts = d2.get("result", {}).get("points_count", 0)
                status = d2.get("result", {}).get("status", "unknown")
                print(f"  • {cn}: {pts} points ({status})")
            except:
                print(f"  • {cn}: ? points")
    except Exception as e:
        print(f"  ⚠️  Qdrant unavailable: {e}")

    print()
    print("✅ Verification complete.")

if __name__ == "__main__":
    run_verify()
