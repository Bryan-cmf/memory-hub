#!/usr/bin/env python3
"""MemoryHub TUI — Full Interactive Dashboard with Save/Stats/Settings panels (9.3-9.5)"""

import json, os, sys
from pathlib import Path

MH_DIR = Path(os.path.expanduser("~/.memory-hub"))
MEMORY_ROOT = Path(os.path.expanduser("~/.openclaw/workspace/memory"))

def clear_screen():
    print("\033[2J\033[H", end="")

def show_menu(current=None):
    clear_screen()
    print("=" * 60)
    print("  🧠 MemoryHub TUI v1.1")
    print("=" * 60)
    print("  [1] Dashboard   [2] Search   [3] Save")
    print("  [4] Stats       [5] Settings  [6] Timeline  [7] Graph  [Q] Quit")
    print("=" * 60)

def panel_dashboard():
    """9.1 Dashboard — system status overview."""
    show_menu()
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:6333/")
        urllib.request.urlopen(req, timeout=2)
        qdrant = "🟢 Online"
    except:
        qdrant = "🔴 Offline"
    
    state_file = MH_DIR / "scan_state.json"
    if state_file.exists():
        s = json.loads(state_file.read_text(encoding="utf-8"))
        sessions = len(s.get("sessions", {}))
        last = s.get("last_scan_time", "Never")
    else:
        sessions = 0; last = "Never"
    
    print(f"\n  Qdrant:    {qdrant}")
    print(f"  Sessions:  {sessions} tracked")
    print(f"  Last scan: {last}")
    
    # File stats
    total = len(list(MEMORY_ROOT.rglob("*.md"))) if MEMORY_ROOT.exists() else 0
    print(f"  Files:     {total} total")

def panel_search():
    """9.2 Search — grep + entity search."""
    show_menu()
    query = input("  Search query: ").strip()
    if not query: return
    
    results = []
    for f in sorted(MEMORY_ROOT.rglob("*.md")):
        try:
            content = f.read_text(encoding="utf-8")
            if query.lower() in content.lower():
                idx = content.lower().find(query.lower())
                s = max(0, idx-60)
                e = min(len(content), idx+len(query)+100)
                results.append({"file": str(f.relative_to(MEMORY_ROOT)), "snippet": content[s:e].replace("\n"," ")[:150]})
        except: continue
    
    print(f"\n  Found {len(results)} results:")
    for i, r in enumerate(results[:10], 1):
        print(f"  {i}. [{r['file']}] {r['snippet'][:100]}")

def panel_save():
    """9.3 Save — write memory entry."""
    show_menu()
    content = input("  Content: ").strip()
    if not content: return
    tags = input("  Tags (comma-separated): ").strip()
    
    from datetime import datetime
    today = datetime.now()
    daily_dir = MEMORY_ROOT / str(today.year) / f"{today.month:02d}"
    daily_dir.mkdir(parents=True, exist_ok=True)
    daily_file = daily_dir / f"{today.day:02d}.md"
    
    entry = f"\n| {today.strftime('%H:%M')} | {content} | — | {tags} |\n"
    with open(daily_file, "a", encoding="utf-8") as f:
        f.write(entry)
    
    print(f"\n  ✅ Saved to {daily_file.relative_to(MEMORY_ROOT)}")

def panel_stats():
    """9.4 Stats — memory statistics."""
    show_menu()
    stats = {"daily": 0, "weekly": 0, "monthly": 0, "yearly": 0, "total_size": 0}
    
    for f in MEMORY_ROOT.rglob("*.md"):
        try:
            s = f.stat().st_size
            stats["total_size"] += s
            if "_yearly" in f.name: stats["yearly"] += 1
            elif "_monthly" in f.name: stats["monthly"] += 1
            elif "_weekly" in f.name: stats["weekly"] += 1
            elif not f.name.startswith("_"): stats["daily"] += 1
        except: continue
    
    print(f"\n  📊 Memory Statistics")
    print(f"  Daily logs:   {stats['daily']}")
    print(f"  Weekly:       {stats['weekly']}")
    print(f"  Monthly:      {stats['monthly']}")
    print(f"  Yearly:       {stats['yearly']}")
    print(f"  Total size:   {stats['total_size']/1024:.1f} KB")

def panel_settings():
    """9.5 Settings — configure MemoryHub."""
    show_menu()
    config_file = MH_DIR / "config.json"
    config = {}
    if config_file.exists():
        config = json.loads(config_file.read_text(encoding="utf-8"))
    
    print(f"\n  ⚙️  Current Settings")
    for k, v in config.items():
        print(f"  {k}: {v}")
    
    print("\n  Settings are stored in ~/.memory-hub/config.json")
    print("  Edit this file to change scan intervals, models, etc.")

def panel_timeline():
    """9.6 Timeline — memory timeline visualization."""
    show_menu()
    print("\n  📅 Generating memory timeline...")
    
    events = []
    for f in sorted(MEMORY_ROOT.rglob("*.md")):
        if f.name.startswith("_"): continue
        try:
            content = f.read_text(encoding="utf-8")
            first_line = content.split("\n")[0].replace("#", "").strip()[:80] or f.stem
            parts = str(f.relative_to(MEMORY_ROOT)).split("/")
            date_str = f"{parts[0]}-{parts[1]}-{f.stem[:2]}" if len(parts) >= 3 and parts[0].isdigit() else "unknown"
            
            events.append({
                "date": date_str,
                "file": str(f.relative_to(MEMORY_ROOT)),
                "title": first_line[:60],
                "size": f.stat().st_size
            })
        except: continue
    
    events.sort(key=lambda e: e["date"], reverse=True)
    
    for e in events[:20]:
        kb = e["size"]/1024
        marker = "📝" if kb < 1 else "📄" if kb < 5 else "📚"
        print(f"  {marker} {e['date']:12s} {e['title'][:50]}")
        print(f"       {e['file']} ({kb:.1f}KB)")

def panel_graph():
    """9.7 Graph — entity relationship graph."""
    show_menu()
    print("\n  🔗 Entity Graph")
    
    # Extract entities from recent memory files
    import re
    entities = {"people": set(), "projects": set(), "files": set()}
    
    recent_files = sorted(MEMORY_ROOT.rglob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)[:30]
    for f in recent_files:
        try:
            content = f.read_text(encoding="utf-8")[:2000]
            # People
            for m in re.findall(r'(?:給|發給|告訴|通知|匯報)([\u4e00-\u9fff]{1,4})(?:總|經理)?', content):
                entities["people"].add(m)
            # Projects
            for m in re.findall(r'([\u4e00-\u9fff]+)(?:項目|系統|調研)', content):
                entities["projects"].add(m)
            # Files
            for m in re.findall(r'([\w\-]+\.(?:pdf|md|py|json))', content):
                entities["files"].add(m)
        except: continue
    
    for label, items in entities.items():
        if items:
            print(f"\n  {label}:")
            for item in sorted(items)[:10]:
                print(f"    ∟ {item}")

def main():
    while True:
        show_menu()
        cmd = input("\n  > ").strip().lower()
        if cmd == "q":
            print("  Goodbye.")
            break
        elif cmd == "1":
            panel_dashboard()
        elif cmd == "2":
            panel_search()
        elif cmd == "3":
            panel_save()
        elif cmd == "4":
            panel_stats()
        elif cmd == "5":
            panel_settings()
        elif cmd == "6":
            panel_timeline()
        elif cmd == "7":
            panel_graph()
        input("\n  Press Enter to continue...")

if __name__ == "__main__":
    main()
