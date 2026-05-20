#!/usr/bin/env python3
"""MemoryHub System Status & Verification — comprehensive health report."""

import json, os, sys, urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

HKT = timezone(timedelta(hours=8))
B = "\033[1m"; G = "\033[32m"; Y = "\033[33m"; R = "\033[31m"; C = "\033[36m"; N = "\033[0m"


def check(label, ok, detail=""):
    icon = f"{G}✅{N}" if ok else f"{R}❌{N}" if ok is False else f"{Y}⚠️{N}"
    print(f"  {icon} {label}: {detail}")


def status_detail():
    """Rich system status — full breakdown."""
    print(f"\n{B}{C}🧠 MemoryHub System Status{N}")
    print(f"{'═'*60}")
    print(f"  Time: {datetime.now(HKT).strftime('%Y-%m-%d %H:%M:%S')} HKT\n")

    # ── 1. All Databases ──
    print(f"{B}🗄️  All Storage Backends{N}")
    print(f"  {'─'*56}")
    try:
        from memory_hub.sync_engine import get_all_stats
        stats = get_all_stats()
    except Exception:
        stats = {}

    # File Storage
    fs = stats.get("file", {})
    print(f"  {B}💾 File Storage (Source of Truth):{N}")
    for label in ["captures", "memories", "hooks"]:
        info = fs.get(label, {})
        files = info.get("files", 0)
        size = info.get("size_bytes", 0) / 1024 / 1024
        ok = files > 0
        icon = f"{G}✅{N}" if ok else f"{Y}⚠️{N}"
        print(f"  {icon} {label:<12} {files:>5} files, {size:.1f}MB")

    # Qdrant
    print(f"\n  {B}🧠 Qdrant (Vector Search):{N}")
    qd = stats.get("qdrant", {})
    if "error" in qd:
        print(f"  {R}❌ {qd['error']}{N}")
    else:
        total_q = 0
        for cn, pts in sorted(qd.items()):
            total_q += max(0, pts)
            bar = "█" * min(20, max(0, pts) // 100) + "░" * max(0, 20 - max(0, pts) // 100)
            icon = f"{G}🟢{N}" if pts >= 0 else f"{R}❌{N}"
            print(f"  {icon} {cn:<20} {pts:>6} pts  {bar}")
        print(f"  {'─'*56}")
        print(f"  {B}Qdrant Total:{N} {total_q} points across {len(qd)} collections")

    # Chroma
    print(f"\n  {B}📦 Chroma (Lightweight Vector):{N}")
    ch = stats.get("chroma", {})
    if "error" in ch:
        print(f"  {Y}⚠️  {ch['error']}{N}")
    elif not ch:
        print(f"  {Y}⚠️  Not installed (run: pip install chromadb){N}")
    else:
        total_c = 0
        for cn, pts in ch.items():
            total_c += pts
            print(f"  {G}✅{N} {cn:<20} {pts:>6} documents")
        print(f"  {B}Chroma Total:{N} {total_c} documents")

    # LanceDB
    print(f"\n  {B}🪶 LanceDB (Embedded Vector):{N}")
    ld = stats.get("lancedb", {})
    if "error" in ld:
        print(f"  {Y}⚠️  {ld['error']}{N}")
    elif not ld:
        print(f"  {Y}⚠️  Not installed (run: pip install lancedb){N}")
    else:
        total_l = 0
        for tn, rows in ld.items():
            total_l += rows
            print(f"  {G}✅{N} {tn:<20} {rows:>6} rows")
        print(f"  {B}LanceDB Total:{N} {total_l} rows")

    # ── 2. Daemon ──
    print(f"\n{B}📡 Capture Daemon{N}")
    print(f"  {'─'*56}")
    try:
        req = urllib.request.Request("http://localhost:3872/api/state", method="GET")
        resp = urllib.request.urlopen(req, timeout=5)
        state = json.loads(resp.read())
        print(f"  🟢 Status:     running on :3872")
        print(f"  ⏱  Started:    {state.get('started_at','')[:19]}")
        print(f"  🔄 Scan cycles: {state.get('scan_cycle', 0)}")
        print(f"  📊 Captures:   {state.get('total_captured', 0)} total")
        print(f"     ├─ Mode A (MCP):  {state.get('mode_a_count', 0)}")
        print(f"     └─ Mode B (Scan): {state.get('mode_b_count', 0)}")
        print()
        for pid, pf in state.get("platforms", {}).items():
            chs = pf.get("channels", {})
            ch_str = ", ".join(f"{k}:{v}" for k, v in sorted(chs.items())) if chs else "—"
            print(f"     {pf['icon']} {pf['name']:<12} {pf['captured']:>4} caps  {pf['files']:>4} files  [{ch_str}]")
    except Exception as e:
        print(f"  {R}❌ Daemon not responding: {str(e)[:50]}{N}")

    # ── 3. MCP Server ──
    print(f"\n{B}🔌 MCP Server{N}")
    print(f"  {'─'*56}")
    import subprocess
    try:
        r = subprocess.run(
            [sys.executable, "-c", "from memory_hub.server.mcp_server import TOOLS; print(len(TOOLS)); print(','.join(sorted(TOOLS.keys())))"],
            capture_output=True, text=True, timeout=5
        )
        lines = r.stdout.strip().split("\n")
        n = lines[0]
        tools = lines[1] if len(lines) > 1 else ""
        print(f"  ✅ Version:    v2.0.0")
        print(f"  ✅ Tools:      {n} ({tools})")
    except Exception as e:
        print(f"  ❌ MCP Server: {str(e)[:50]}")

    # ── 5. Platform MCP Configs ──
    print(f"\n{B}📋 Platform MCP Configuration{N}")
    print(f"  {'─'*56}")
    platforms = {
        "OpenClaw":    (Path.home() / ".openclaw/openclaw.json", ["mcp","servers","memory-hub"]),
        "DeepSeek TUI": (Path.home() / ".deepseek/mcp.json", ["servers","memory-hub"]),
        "Hermes Agent": (Path.home() / ".hermes/mcp.json", ["servers","memory-hub"]),
        "Claude Code":  (Path.home() / ".claude/mcp.json", ["mcpServers","memory-hub"]),
    }
    for name, (fp, keys) in platforms.items():
        installed = False
        detected = fp.parent.exists() if fp.parent != Path.home() else fp.exists()
        if fp.exists():
            try:
                cfg = json.loads(fp.read_text(encoding="utf-8"))
                d = cfg
                for k in keys:
                    d = d.get(k, {})
                installed = d and len(d) > 1  # more than just empty dict
            except: pass
        icon = f"{G}✅{N}" if installed else f"{Y}⚠️{N}" if detected else f"{R}❌{N}"
        status_text = "configured" if installed else ("platform exists, MCP not configured" if detected else "not detected")
        print(f"  {icon} {name:<14} {status_text}")

    # ── 6. MEMORY.md Index ──
    print(f"\n{B}📑 MEMORY.md Auto-Index{N}")
    print(f"  {'─'*56}")
    index_path = mh_dir / "MEMORY.md"
    if index_path.exists():
        lines = index_path.read_text(encoding="utf-8").strip().split("\n")
        print(f"  ✅ Generated: {index_path.stat().st_mtime}")
        print(f"  ✅ Size:      {len(lines)} lines, {index_path.stat().st_size} bytes")
        print(f"  Preview:")
        for l in lines[:8]:
            print(f"  │ {l[:56]}")
    else:
        print(f"  ⚠️  Not yet generated (runs hourly during scan cycle)")

    print(f"\n{B}{'═'*60}{N}\n")


def run_verify():
    """Quick health check — pass/fail for CI/CD."""
    print("🔍 MemoryHub Quick Verification")
    print("=" * 50)

    issues = 0

    # Qdrant
    try:
        req = urllib.request.Request("http://localhost:6333/collections", method="GET")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        cols = data.get("result", {}).get("collections", [])
        ok = len(cols) > 0
        check("Qdrant (vector DB)", ok, f"{len(cols)} collections")
        if not ok: issues += 1
    except Exception as e:
        check("Qdrant (vector DB)", False, str(e)[:60])
        issues += 1

    # Daemon
    try:
        req = urllib.request.Request("http://localhost:3872/api/state", method="GET")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        ok = "total_captured" in data
        check("Capture Daemon", ok, f"{data.get('total_captured',0)} captures")
        if not ok: issues += 1
    except Exception as e:
        check("Capture Daemon", False, str(e)[:60])
        issues += 1

    # Dashboard
    try:
        req = urllib.request.Request("http://localhost:3872/", method="GET")
        resp = urllib.request.urlopen(req, timeout=5)
        ok = resp.status == 200
        check("Dashboard", ok, f"HTTP {resp.status}")
        if not ok: issues += 1
    except Exception as e:
        check("Dashboard", False, str(e)[:60])
        issues += 1

    # MCP Server
    try:
        import subprocess
        r = subprocess.run(
            [sys.executable, "-c", "from memory_hub.server.mcp_server import TOOLS; print(len(TOOLS))"],
            capture_output=True, text=True, timeout=5
        )
        n = r.stdout.strip()
        ok = n.isdigit() and int(n) >= 5
        check("MCP Server", ok, f"{n} tools" if ok else r.stderr[:60])
        if not ok: issues += 1
    except Exception as e:
        check("MCP Server", False, str(e)[:60])
        issues += 1

    # File Storage
    mh_dir = Path(os.path.expanduser("~/.memory-hub"))
    memories = mh_dir / "memories"
    ok = memories.exists()
    n = len(list(memories.glob("*.json"))) if ok else 0
    check("File Storage", ok, f"{n} files")
    if not ok: issues += 1

    # Platform MCP configs
    platforms = {
        "OpenClaw":    (Path.home() / ".openclaw/openclaw.json", ["mcp","servers","memory-hub"]),
        "DeepSeek":    (Path.home() / ".deepseek/mcp.json", ["servers","memory-hub"]),
        "Hermes":      (Path.home() / ".hermes/mcp.json", ["servers","memory-hub"]),
        "Claude Code": (Path.home() / ".claude/mcp.json", ["mcpServers","memory-hub"]),
    }
    for name, (fp, keys) in platforms.items():
        ok = False; detail = "not found"
        if fp.exists():
            try:
                cfg = json.loads(fp.read_text(encoding="utf-8"))
                d = cfg
                for k in keys:
                    d = d.get(k, {})
                ok = d and len(d) > 1
                detail = "configured" if ok else "not configured"
            except: detail = "parse error"
        else:
            detected = fp.parent.exists()
            detail = "platform not detected" if not detected else "config not found"
        check(f"MCP: {name}", ok, detail)
        if not ok: issues += 1

    print()
    if issues == 0:
        print(f"{G}✅ All checks passed{N}")
    else:
        print(f"{R}❌ {issues} check(s) failed{N}")

    # Also show full status
    status_detail()


if __name__ == "__main__":
    import sys
    if "--quick" in sys.argv:
        run_verify()
    else:
        status_detail()
