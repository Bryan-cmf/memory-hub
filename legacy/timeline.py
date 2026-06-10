#!/usr/bin/env python3
"""MemoryHub Timeline — 記憶時間線可視化"""

import json, os
from pathlib import Path
from datetime import datetime

def generate_timeline():
    root = Path(os.path.expanduser("~/.openclaw/workspace/memory"))
    events = []
    
    for md_file in sorted(root.rglob("*.md")):
        if md_file.name.startswith("_"): continue
        try:
            stat = md_file.stat()
            content = md_file.read_text(encoding="utf-8")
            first_line = content.split("\n")[0].replace("#", "").strip()[:100] or md_file.stem
            
            # Extract date from path or filename
            date_str = None
            parts = str(md_file.relative_to(root)).split("/")
            if len(parts) >= 3 and parts[0].isdigit():
                date_str = f"{parts[0]}-{parts[1]}-{md_file.stem[:2]}"
            
            events.append({
                "date": date_str or datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
                "file": str(md_file.relative_to(root)),
                "title": first_line,
                "size": len(content),
                "type": "weekly" if "_weekly" in md_file.name else "monthly" if "_monthly" in md_file.name else "daily"
            })
        except (OSError, UnicodeDecodeError): continue
    
    events.sort(key=lambda e: e["date"])
    
    # Generate markdown timeline
    md = "# Memory Timeline\n\n"
    for e in events:
        md += f"### {e['date']} — {e['title']}\n"
        md += f"[{e['file']}] ({e['size']} chars, {e['type']})\n\n"
    
    out = root / "TIMELINE.md"
    out.write_text(md, encoding="utf-8")
    return {"status": "generated", "file": str(out), "events": len(events)}

if __name__ == "__main__":
    print(json.dumps(generate_timeline(), ensure_ascii=False, indent=2))
