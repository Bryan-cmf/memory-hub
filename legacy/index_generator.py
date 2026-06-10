#!/usr/bin/env python3
"""MemoryHub Index Generator — 自動生成 INDEX.md 全文關鍵詞索引"""

import os, json
from pathlib import Path
from collections import Counter
from datetime import datetime

def generate_index(memory_root=None):
    root = Path(memory_root) if memory_root else Path(os.path.expanduser("~/.openclaw/workspace/memory"))
    index = {"generated": datetime.now().isoformat(), "files": [], "keywords": Counter(), "by_date": {}}
    
    for md_file in sorted(root.rglob("*.md")):
        if md_file.name.startswith("_"): continue
        try:
            content = md_file.read_text(encoding="utf-8")
            # Extract keywords (simple word frequency, Chinese 2-gram)
            words = [w for w in content.split() if len(w) >= 2 and not w.startswith("#")]
            for w in words[:50]:
                index["keywords"][w.lower()] += 1
            
            rel_path = str(md_file.relative_to(root))
            index["files"].append({"path": rel_path, "size": len(content)})
            
            # Date-based grouping
            parts = rel_path.split("/")
            if len(parts) >= 3 and parts[0].isdigit():
                year = parts[0]
                if year not in index["by_date"]:
                    index["by_date"][year] = []
                index["by_date"][year].append(rel_path)
        except (OSError, UnicodeDecodeError): continue
    
    # Top keywords
    index["top_keywords"] = index["keywords"].most_common(50)
    del index["keywords"]
    
    # Generate markdown
    md = f"# Memory Index\n\nGenerated: {index['generated']}\n\n"
    md += f"## Files ({len(index['files'])} total)\n\n"
    
    for year, files in sorted(index["by_date"].items()):
        md += f"### {year} ({len(files)} files)\n"
        for f in files[:10]:
            md += f"- [{f}]({f})\n"
        md += "\n"
    
    md += "## Top Keywords\n\n"
    for kw, count in index["top_keywords"][:20]:
        md += f"- {kw}: {count}\n"
    
    out = root / "INDEX.md"
    out.write_text(md, encoding="utf-8")
    return {"status": "generated", "file": str(out), "files_indexed": len(index["files"])}

if __name__ == "__main__":
    print(json.dumps(generate_index(), ensure_ascii=False, indent=2))
