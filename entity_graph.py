#!/usr/bin/env python3
"""MemoryHub Entity Graph — 實體關係圖生成器"""

import json
from pathlib import Path
from datetime import datetime

def extract_entities_from_text(text: str) -> dict:
    """Extract entities from memory text using pattern matching."""
    entities = {"people": [], "projects": [], "files": [], "decisions": []}
    
    # Simple pattern matching
    import re
    
    # People: 「給王總」「發給xxx」「xxx要求」
    people_matches = re.findall(r'(?:給|發給|告訴|通知|匯報)([\u4e00-\u9fff]{1,4})(?:總|經理|老闆|哥|姐)?', text)
    entities["people"] = list(set(people_matches))
    
    # Projects: 「xxx項目」「xxx系統」「xxx調研」
    proj_matches = re.findall(r'([\u4e00-\u9fff]+)(?:項目|系統|調研|報告|平台|網站)', text)
    entities["projects"] = list(set(proj_matches))
    
    # Files: 「xxx.pdf」「xxx.md」「xxx.py」
    file_matches = re.findall(r'([\w\-]+\.(?:pdf|md|py|json|csv|html|pptx|docx))', text)
    entities["files"] = list(set(file_matches))
    
    # Decisions: 「決定」「選擇」「採用」
    if any(kw in text for kw in ["決定", "選擇", "採用", "改為"]):
        entities["decisions"].append("decision_detected")
    
    return entities

def build_graph(memory_dir: str = None):
    """Build entity graph from memory files."""
    from pathlib import Path
    root = Path(memory_dir) if memory_dir else Path.home() / ".openclaw/workspace/memory"
    
    graph = {"nodes": {}, "edges": [], "timestamp": datetime.now().isoformat()}
    
    for md_file in sorted(root.rglob("*.md")):
        if md_file.name.startswith("_"): continue
        try:
            content = md_file.read_text(encoding="utf-8")[:2000]
            entities = extract_entities_from_text(content)
            rel_path = str(md_file.relative_to(root))
            
            for p in entities["people"]:
                if p not in graph["nodes"]:
                    graph["nodes"][p] = {"type": "person", "mentions": []}
                graph["nodes"][p]["mentions"].append(rel_path)
            
            for pr in entities["projects"]:
                if pr not in graph["nodes"]:
                    graph["nodes"][pr] = {"type": "project", "mentions": []}
                graph["nodes"][pr]["mentions"].append(rel_path)
            
            for f in entities["files"]:
                if f not in graph["nodes"]:
                    graph["nodes"][f] = {"type": "file", "mentions": []}
                graph["nodes"][f]["mentions"].append(rel_path)
                
        except (OSError, UnicodeDecodeError):
            continue
    
    graph["summary"] = {
        "total_nodes": len(graph["nodes"]),
        "people": sum(1 for n in graph["nodes"].values() if n["type"] == "person"),
        "projects": sum(1 for n in graph["nodes"].values() if n["type"] == "project"),
        "files": sum(1 for n in graph["nodes"].values() if n["type"] == "file"),
    }
    
    return graph

if __name__ == "__main__":
    g = build_graph()
    print(json.dumps(g, ensure_ascii=False, indent=2))
