#!/usr/bin/env python3
"""MemoryHub Quality System — 可信度標記 + 矛盾檢測 + 完整性檢查"""

import os, json, re
from pathlib import Path
from datetime import datetime, timezone

MEMORY_ROOT = Path(os.path.expanduser("~/.openclaw/workspace/memory"))

def check_memory_integrity():
    """Check for orphaned memories, broken links, and inconsistencies."""
    issues = []
    
    # Check entities directory
    entity_dir = MEMORY_ROOT / "entities"
    if not entity_dir.exists():
        issues.append({"severity": "info", "message": "entities/ directory not found. Create it for knowledge graph support."})
    
    # Check for empty daily logs
    for year_dir in sorted(MEMORY_ROOT.glob("20*")):
        if not year_dir.is_dir(): continue
        for month_dir in sorted(year_dir.glob("*")):
            if not month_dir.is_dir(): continue
            for daily_file in month_dir.glob("*.md"):
                if daily_file.name.startswith("_"): continue
                if daily_file.stat().st_size < 50:
                    issues.append({
                        "severity": "low",
                        "message": f"Near-empty daily log: {daily_file.relative_to(MEMORY_ROOT)}"
                    })
    
    # Check for missing weekly summaries
    now = datetime.now()
    for year_dir in sorted(MEMORY_ROOT.glob("20*")):
        if not year_dir.is_dir(): continue
        for month_dir in sorted(year_dir.glob("*")):
            if not month_dir.is_dir(): continue
            weeklies = list(month_dir.glob("_weekly-*.md"))
            dailies = [f for f in month_dir.glob("*.md") if not f.name.startswith("_")]
            if len(dailies) >= 5 and not weeklies:
                issues.append({
                    "severity": "medium",
                    "message": f"Month has {len(dailies)} daily logs but no weekly summary: {month_dir.relative_to(MEMORY_ROOT)}"
                })
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_issues": len(issues),
        "issues": issues[:20]
    }

def mark_quality(content: str, source_count: int = 1) -> dict:
    """Add quality metadata to a memory entry."""
    return {
        "content": content,
        "source_count": source_count,
        "last_verified": datetime.now(timezone.utc).isoformat(),
        "verification_status": "unverified" if source_count < 2 else "verified"
    }

def detect_contradiction(new_content: str, existing_entries: list) -> list:
    """Detect if new content contradicts existing entries (basic keyword-based)."""
    contradictions = []
    new_lower = new_content.lower()
    
    negation_patterns = ["不再", "改為", "取代", "廢除", "停止", "取消"]
    for entry in existing_entries:
        existing_lower = entry.get("content", "").lower()
        for pattern in negation_patterns:
            if pattern in new_lower and any(kw in existing_lower for kw in new_lower.split()[:3]):
                contradictions.append({
                    "existing": entry.get("content", "")[:100],
                    "new": new_content[:100],
                    "pattern": pattern
                })
    
    return contradictions

if __name__ == "__main__":
    result = check_memory_integrity()
    print(json.dumps(result, ensure_ascii=False, indent=2))
