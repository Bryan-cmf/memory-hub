#!/usr/bin/env python3
"""MemoryHub Export — 記憶匯出為 JSON/CSV/Markdown"""

import json, csv, os
from pathlib import Path
from datetime import datetime

MEMORY_ROOT = Path(os.path.expanduser("~/.openclaw/workspace/memory"))

def export_json(output_path=None):
    """Export all memory files as JSON."""
    data = {"exported_at": datetime.now().isoformat(), "files": []}
    
    for md_file in sorted(MEMORY_ROOT.rglob("*.md")):
        if md_file.name.startswith("_"): continue
        try:
            content = md_file.read_text(encoding="utf-8")
            data["files"].append({
                "path": str(md_file.relative_to(MEMORY_ROOT)),
                "size": len(content),
                "lines": len(content.split("\n")),
                "preview": content[:200]
            })
        except (OSError, UnicodeDecodeError): continue
    
    out = output_path or f"memoryhub_export_{datetime.now().strftime('%Y%m%d')}.json"
    Path(out).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "exported", "file": out, "count": len(data["files"])}

def export_csv(output_path=None):
    """Export memory index as CSV."""
    out = output_path or f"memoryhub_export_{datetime.now().strftime('%Y%m%d')}.csv"
    
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "path", "size_bytes", "lines", "type"])
        
        for md_file in sorted(MEMORY_ROOT.rglob("*.md")):
            if md_file.name.startswith("_"): continue
            try:
                content = md_file.read_text(encoding="utf-8")
                date_str = md_file.stem if md_file.stem.replace("-", "").isdigit() else ""
                mem_type = "weekly" if "_weekly" in md_file.name else "monthly" if "_monthly" in md_file.name else "daily"
                writer.writerow([date_str, str(md_file.relative_to(MEMORY_ROOT)),
                               len(content), len(content.split("\n")), mem_type])
            except (OSError, UnicodeDecodeError): continue
    
    return {"status": "exported", "file": out}

def generate_stats():
    """Generate memory statistics."""
    stats = {"total_files": 0, "total_size_bytes": 0, "total_lines": 0, "by_year": {}}
    
    for md_file in MEMORY_ROOT.rglob("*.md"):
        if md_file.name.startswith("_"): continue
        try:
            content = md_file.read_text(encoding="utf-8")
            year = md_file.parts[-3] if len(md_file.parts) >= 3 and md_file.parts[-3].isdigit() else "unknown"
            stats["total_files"] += 1
            stats["total_size_bytes"] += len(content)
            stats["total_lines"] += len(content.split("\n"))
            if year not in stats["by_year"]:
                stats["by_year"][year] = {"files": 0, "size": 0}
            stats["by_year"][year]["files"] += 1
            stats["by_year"][year]["size"] += len(content)
        except (OSError, UnicodeDecodeError): continue
    
    return stats

if __name__ == "__main__":
    import sys
    fmt = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if fmt == "json":
        print(json.dumps(export_json(), ensure_ascii=False, indent=2))
    elif fmt == "csv":
        print(json.dumps(export_csv(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(generate_stats(), ensure_ascii=False, indent=2))
