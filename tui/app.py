#!/usr/bin/env python3
"""MemoryHub TUI — 向量記憶系統終端監控界面 (Textual)"""

# Requires: pip install textual

import json, os
from pathlib import Path
from datetime import datetime

MH_DIR = Path(os.path.expanduser("~/.memory-hub"))
STATE_FILE = MH_DIR / "scan_state.json"

def get_system_status():
    """Get current system status."""
    status = {
        "qdrant": "unknown",
        "scanner": "unknown",
        "last_scan": None,
        "sessions_tracked": 0,
        "collections": []
    }
    
    # Check Qdrant
    import urllib.request
    try:
        req = urllib.request.Request("http://localhost:6333/")
        urllib.request.urlopen(req, timeout=2)
        status["qdrant"] = "online"
    except:
        status["qdrant"] = "offline"
    
    # Check scanner state
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            status["last_scan"] = state.get("last_scan_time")
            status["sessions_tracked"] = len(state.get("sessions", {}))
        except:
            pass
    
    # Check scanner pid
    import subprocess
    try:
        r = subprocess.run(["pgrep", "-f", "session_scanner.py"], capture_output=True, text=True)
        status["scanner"] = "running" if r.stdout.strip() else "stopped"
    except:
        status["scanner"] = "unknown"
    
    return status

def render_dashboard():
    """Render a simple dashboard in terminal (no Textual dependency for basic mode)."""
    status = get_system_status()
    
    print("\033[2J\033[H")  # Clear screen
    print("=" * 60)
    print("  🧠 MemoryHub Dashboard")
    print("=" * 60)
    print(f"  Qdrant:    {'🟢 Online' if status['qdrant'] == 'online' else '🔴 Offline'}")
    print(f"  Scanner:   {'🟢 Running' if status['scanner'] == 'running' else '🔴 Stopped'}")
    print(f"  Sessions:  {status['sessions_tracked']} tracked")
    print(f"  Last scan: {status['last_scan'] or 'Never'}")
    print("=" * 60)
    print("  Commands: [S]earch  [V]iew stats  [Q]uit")

def search_memory(query: str):
    """Simple grep-based memory search."""
    memory_dir = Path(os.path.expanduser("~/.openclaw/workspace/memory"))
    results = []
    for f in sorted(memory_dir.rglob("*.md")):
        try:
            content = f.read_text(encoding="utf-8")
            if query.lower() in content.lower():
                idx = content.lower().find(query.lower())
                start = max(0, idx - 60)
                snippet = content[start:idx + len(query) + 100].replace("\n", " ")[:150]
                results.append({"file": str(f.relative_to(memory_dir)), "snippet": snippet})
        except: continue
    
    return results[:10]

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "status":
            print(json.dumps(get_system_status(), ensure_ascii=False, indent=2))
        elif cmd == "search" and len(sys.argv) > 2:
            results = search_memory(sys.argv[2])
            for i, r in enumerate(results, 1):
                print(f"{i}. [{r['file']}] {r['snippet'][:100]}")
    else:
        render_dashboard()
