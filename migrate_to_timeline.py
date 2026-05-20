#!/usr/bin/env python3
"""Migrate flat memory structure to timeline-based YYYY/MM/DD.md"""

import os, re, json
from pathlib import Path
from datetime import datetime

SOURCE = Path(os.path.expanduser("~/.openclaw/workspace/memory"))
DEST = SOURCE  # In-place migration

def migrate_daily_logs():
    """Move flat daily/*.md to YYYY/MM/DD.md structure."""
    daily_dir = SOURCE / "daily"
    if not daily_dir.exists():
        print("No daily/ directory found. Nothing to migrate.")
        return {"status": "noop"}
    
    migrated = 0
    for f in sorted(daily_dir.glob("*.md")):
        name = f.stem  # e.g., 2026-05-19
        if not re.match(r"\d{4}-\d{2}-\d{2}", name):
            continue
        parts = name.split("-")
        year, month, day = parts[0], parts[1], parts[2]
        dest_dir = DEST / year / month
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / f"{day}.md"
        dest_file.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
        migrated += 1
    
    if migrated > 0:
        print(f"Migrated {migrated} daily logs to YYYY/MM/DD.md structure")
        print(f"Original files in {daily_dir} preserved.")
    
    return {"status": "migrated", "count": migrated}

if __name__ == "__main__":
    r = migrate_daily_logs()
    print(json.dumps(r, ensure_ascii=False, indent=2))
