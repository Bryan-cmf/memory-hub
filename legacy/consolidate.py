#!/usr/bin/env python3
"""MemoryHub Consolidation Engine — Daily→Weekly→Monthly→Yearly 自動濃縮"""

import os, json, re
from pathlib import Path
from datetime import datetime, timedelta

MEMORY_ROOT = Path(os.path.expanduser("~/.openclaw/workspace/memory"))

def get_week_range(date=None):
    """Get Monday-Sunday range for a given date."""
    d = date or datetime.now()
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday

def consolidate_weekly(year=None, month=None, week=None):
    """Scan 7 daily logs → produce _weekly.md summary."""
    now = datetime.now()
    y = year or now.year
    m = month or now.month
    monday, sunday = get_week_range(datetime(y, m, 15) if month else now)
    
    daily_dir = MEMORY_ROOT / str(y) / f"{m:02d}"
    if not daily_dir.exists():
        return {"status": "no_data", "message": f"No daily logs for {y}-{m:02d}"}
    
    entries = []
    current = monday
    while current <= sunday:
        daily_file = daily_dir / f"{current.day:02d}.md"
        if daily_file.exists():
            content = daily_file.read_text(encoding="utf-8")
            entries.append({"date": current.strftime("%Y-%m-%d"), "content": content[:500]})
        current += timedelta(days=1)
    
    if not entries:
        return {"status": "no_data", "message": "No daily logs this week"}
    
    # Extract key sections
    highlights = []
    for e in entries:
        for line in e["content"].split("\n"):
            line = line.strip()
            if line.startswith("##") or line.startswith("- **") or line.startswith("|"):
                highlights.append(f"{e['date']}: {line}")
    
    summary = f"# Week of {monday.strftime('%Y-%m-%d')}\n\n"
    summary += f"## Activity ({len(entries)} days logged)\n\n"
    for h in highlights[:20]:
        summary += f"- {h}\n"
    
    week_file = daily_dir / f"_weekly-{monday.strftime('%m-%d')}.md"
    week_file.write_text(summary, encoding="utf-8")
    
    return {
        "status": "consolidated",
        "file": str(week_file),
        "days_processed": len(entries),
        "highlights": len(highlights)
    }

def consolidate_monthly(year=None, month=None):
    """Merge 4 weekly logs → _monthly.md."""
    now = datetime.now()
    y = year or now.year
    m = month or now.month
    month_dir = MEMORY_ROOT / str(y) / f"{m:02d}"
    
    weeklies = sorted(month_dir.glob("_weekly-*.md")) if month_dir.exists() else []
    if not weeklies:
        return {"status": "no_data", "message": "No weekly logs"}
    
    content_parts = []
    for w in weeklies:
        content_parts.append(w.read_text(encoding="utf-8")[:300])
    
    summary = f"# {y}-{m:02d} Monthly Review\n\n"
    summary += f"## Weeks covered: {len(weeklies)}\n\n"
    summary += "## Key themes\n\n"
    summary += "\n---\n".join(content_parts)
    
    monthly_file = month_dir / f"_monthly-{y}-{m:02d}.md"
    monthly_file.write_text(summary, encoding="utf-8")
    return {"status": "consolidated", "file": str(monthly_file)}

def consolidate_yearly(year=None):
    """Merge 12 monthly logs → _yearly.md."""
    y = year or datetime.now().year
    year_dir = MEMORY_ROOT / str(y)
    
    all_monthlies = []
    for m in range(1, 13):
        month_dir = year_dir / f"{m:02d}"
        if month_dir.exists():
            for mf in month_dir.glob("_monthly-*.md"):
                all_monthlies.append(mf.read_text(encoding="utf-8")[:200])
    
    summary = f"# {y} Year in Review\n\n"
    summary += f"## Months: {len(all_monthlies)}\n\n"
    summary += "\n---\n".join(all_monthlies)
    
    yearly_file = year_dir / f"_yearly-{y}.md"
    yearly_file.write_text(summary, encoding="utf-8")
    return {"status": "consolidated", "file": str(yearly_file)}

if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "weekly"
    
    if mode == "weekly":
        r = consolidate_weekly()
    elif mode == "monthly":
        r = consolidate_monthly()
    elif mode == "yearly":
        r = consolidate_yearly()
    elif mode.startswith("--range"):
        parts = sys.argv[2] if len(sys.argv) > 2 else ""
        if ".." in parts:
            start_str, end_str = parts.split("..")
            r = {"status": "range_consolidation", "start": start_str, "end": end_str, "message": "Range consolidation: python3 consolidate.py weekly + monthly for the specified range"}
        else:
            r = {"error": "Usage: consolidate.py --range 2026-01..2026-06"}
    else:
        r = {"error": f"Unknown mode: {mode}"}
    
    print(json.dumps(r, ensure_ascii=False, indent=2))
