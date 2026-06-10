#!/usr/bin/env python3
"""MemoryHub Auto-Tagger — LLM-based content tagging (F5.1)"""

import json, os, sys, re
from pathlib import Path

# Simple rule-based tagger (no LLM dependency required)
TAG_RULES = {
    "調研": ["調研", "研究", "分析", "報告", "市場", "行業", "數據"],
    "決策": ["決定", "選擇", "採用", "改為", "不再", "改回"],
    "踩坑": ["bug", "錯誤", "失敗", "修正", "修復", "問題", "踩坑"],
    "開發": ["code", "programming", "代碼", "實現", "開發", "部署"],
    "會議": ["會議", "meeting", "討論", "sync"],
    "財務": ["估值", "PE", "融資", "財務", "CFO", "IPO"],
    "安全": ["API key", "密碼", "token", "secret", "權限"],
    "部署": ["docker", "pip install", "brew", "deploy", "發布"],
}

def auto_tag(content: str) -> list:
    """Auto-tag content based on keyword rules."""
    tags = []
    content_lower = content.lower()
    for tag, keywords in TAG_RULES.items():
        if any(kw.lower() in content_lower for kw in keywords):
            tags.append(tag)
    return tags

# ═══════════════════════════════════════════════════
# Webhook Output (F5.2)
# ═══════════════════════════════════════════════════

def webhook_push(webhook_url: str, title: str, content: str, tags: list = None):
    """Push important memories to external webhook (Lark/Slack/Discord)."""
    import urllib.request
    payload = {
        "title": title,
        "content": content[:500],
        "tags": tags or [],
        "source": "MemoryHub",
        "timestamp": __import__('datetime').datetime.now().isoformat()
    }
    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=5)
        return {"status": "sent"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}

# ═══════════════════════════════════════════════════
# Multi-User Isolation (F5.3)
# ═══════════════════════════════════════════════════

def get_user_collection(user_id: str = "default") -> str:
    """Get collection name for a specific user."""
    return f"user_{user_id}_mem"

# ═══════════════════════════════════════════════════
# Knowledge Export (F5.4)
# ═══════════════════════════════════════════════════

def export_obsidian(memories: list, output_dir: str):
    """Export memories as Obsidian-compatible markdown files."""
    p = Path(output_dir); p.mkdir(parents=True, exist_ok=True)
    for mem in memories[:50]:
        fid = mem.get("point_id", mem.get("file","memory"))[:32]
        tags = mem.get("tags", [])
        content = mem.get("content", "")
        md = f"""---
tags: {json.dumps(tags, ensure_ascii=False)}
created: {mem.get("created_at", "")}
source: {mem.get("platform", "memoryhub")}
---

# {content[:80]}

{content}
"""
        (p / f"{fid}.md").write_text(md, encoding="utf-8")
    return {"exported": len(memories), "dir": str(p)}

def export_notion(memories: list, output_file: str):
    """Export memories as Notion-compatible markdown."""
    md = "# MemoryHub Export\n\n"
    for mem in memories[:100]:
        md += f"## {mem.get('content','')[:60]}\n"
        md += f"- Tags: {', '.join(mem.get('tags',[]))}\n"
        md += f"- Date: {mem.get('created_at','')}\n"
        md += f"- Platform: {mem.get('platform','')}\n\n"
        md += f"{mem.get('content','')}\n\n---\n\n"
    Path(output_file).write_text(md, encoding="utf-8")
    return {"exported": len(memories), "file": str(output_file)}

if __name__ == "__main__":
    # Test auto-tag
    tests = ["完成了香港IPO市場調研報告", "修復了記憶掃描的重複bug", "決定採用Chroma替代Qdrant"]
    for t in tests:
        tags = auto_tag(t)
        print(f"  '{t[:40]}' → {tags}")
