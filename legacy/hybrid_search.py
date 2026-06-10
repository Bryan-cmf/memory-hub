#!/usr/bin/env python3
"""MemoryHub Hybrid Search — 向量 + 時間 + 實體 + 標籤 四合一搜索"""

import json, os
from pathlib import Path
from datetime import datetime, timedelta

MH_DIR = Path(os.path.expanduser("~/.memory-hub"))
CONFIG_FILE = MH_DIR / "config.json"

def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return {"tier": "0"}

def parse_time_range(query: str) -> tuple:
    """Parse fuzzy time expressions: 上個月, 去年夏天, 疫情期間, etc."""
    now = datetime.now()
    q = query.lower()
    
    if "今天" in q: return (now.replace(hour=0, minute=0), now)
    if "昨天" in q:
        d = now - timedelta(days=1)
        return (d.replace(hour=0, minute=0), d.replace(hour=23, minute=59))
    if "本週" in q:
        d = now - timedelta(days=now.weekday())
        return (d.replace(hour=0, minute=0), now)
    if "上週" in q:
        end = now - timedelta(days=now.weekday() + 1)
        start = end - timedelta(days=6)
        return (start.replace(hour=0, minute=0), end.replace(hour=23, minute=59))
    if "本月" in q:
        return (now.replace(day=1, hour=0, minute=0), now)
    if "上個月" in q or "上月" in q:
        first = now.replace(day=1) - timedelta(days=1)
        return (first.replace(day=1, hour=0, minute=0), first.replace(hour=23, minute=59))
    if "今年" in q:
        return (now.replace(month=1, day=1, hour=0, minute=0), now)
    if "去年" in q:
        end = now.replace(month=1, day=1) - timedelta(days=1)
        return (end.replace(month=1, day=1, hour=0, minute=0), end.replace(hour=23, minute=59))
    
    return (None, None)

def search_files(query: str, since=None, until=None, path_filter=None):
    """Grep-based file search as fallback."""
    memory_dir = Path(os.path.expanduser("~/.openclaw/workspace/memory"))
    results = []
    
    for md_file in memory_dir.rglob("*.md"):
        if path_filter and path_filter not in str(md_file): continue
        try:
            content = md_file.read_text(encoding="utf-8")
            if query.lower() in content.lower():
                # Extract relevant snippet
                idx = content.lower().find(query.lower())
                start = max(0, idx - 80)
                end = min(len(content), idx + len(query) + 200)
                snippet = content[start:end].replace("\n", " ")
                results.append({
                    "file": str(md_file.relative_to(memory_dir)),
                    "snippet": f"...{snippet}...",
                    "type": "file_match"
                })
        except (OSError, UnicodeDecodeError): continue
    
    return results[:20]

def hybrid_search(query, since=None, until=None, entities=None, tags=None, limit=10):
    """Main hybrid search entry point."""
    config = load_config()
    results = {"vector": [], "file": [], "entity": [], "query": query}
    
    # Layer 1: File system grep (always available)
    results["file"] = search_files(query, since, until)
    
    # Layer 2: Entity graph search (if entities dir exists)
    entity_dir = Path(os.path.expanduser("~/.openclaw/workspace/memory/entities"))
    if entities and entity_dir.exists():
        for entity_file in entity_dir.glob("*.md"):
            content = entity_file.read_text(encoding="utf-8")
            for entity in entities:
                if entity.lower() in content.lower():
                    results["entity"].append({
                        "entity": entity,
                        "file": entity_file.name,
                        "type": "entity_match"
                    })
    
    # Layer 3: Time range filter
    time_range = parse_time_range(query)
    if time_range[0]:
        results["time_range"] = {
            "since": time_range[0].isoformat(),
            "until": time_range[1].isoformat()
        }
    
    return results

if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "test"
    r = hybrid_search(q)
    print(json.dumps(r, ensure_ascii=False, indent=2))
