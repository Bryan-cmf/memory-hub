#!/usr/bin/env python3
"""MemoryHub Association Search — 追溯完整決策鏈 (2.5)"""

import json, os, re
from pathlib import Path

MEMORY_ROOT = Path(os.path.expanduser("~/.openclaw/workspace/memory"))

def trace_decision_chain(keyword: str, max_depth: int = 3) -> dict:
    """Trace a decision from keyword through related files."""
    chain = {"keyword": keyword, "steps": [], "entities_found": []}
    visited = set()
    queue = [(keyword, 0)]
    
    while queue and len(chain["steps"]) < 10:
        current, depth = queue.pop(0)
        if depth > max_depth or current in visited:
            continue
        visited.add(current)
        
        for md_file in sorted(MEMORY_ROOT.rglob("*.md")):
            if md_file.name.startswith("_"):
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
                if current.lower() in content.lower():
                    chain["steps"].append({
                        "depth": depth,
                        "keyword": current,
                        "file": str(md_file.relative_to(MEMORY_ROOT)),
                        "lines": len(content.split("\n"))
                    })
                    
                    # Extract related entities for next iteration
                    entities_found = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', content)
                    for label, link in entities_found[:3]:
                        if link not in visited:
                            queue.append((label, depth + 1))
                    
                    # Extract "see also" references
                    see_also = re.findall(r'(?:see also|see|相關)[:\s]*\[?([^\]]+)\]?', content, re.IGNORECASE)
                    for ref in see_also[:3]:
                        if ref not in visited:
                            queue.append((ref, depth + 1))
            except (OSError, UnicodeDecodeError):
                continue
    
    chain["total_steps"] = len(chain["steps"])
    return chain

if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "Qdrant"
    result = trace_decision_chain(q)
    print(json.dumps(result, ensure_ascii=False, indent=2))
