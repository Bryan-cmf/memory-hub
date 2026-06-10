#!/usr/bin/env python3
"""MemoryHub Dedup Engine v1.2 — 三层去重机制

Layer A: UUID5 内容级去重 — 相同内容只存一份
Layer B: Offset 级增量扫描 — 已扫过的字节不再重扫
Layer C: 跨 Session 语义相似度去重 — Jaccard > 0.85 合并

配合 capture_daemon.py 在捕获管道中拦截重复。
"""

import re, json, uuid, hashlib
from datetime import datetime

# ── Layer A: UUID5 内容级去重 ──────────────────

def content_uuid5(content: str) -> str:
    """为内容生成确定性 UUID5。相同内容 → 相同 UUID。"""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, content[:2000]))

class DedupFilter:
    """三层去重过滤器，可在 capture_daemon 管道中调用。"""
    
    def __init__(self):
        self._uuid5_seen = set()        # Layer A: UUID5 缓存
        self._offsets = {}              # Layer B: 文件偏移量
        self._history = []              # Layer C: 近期记忆（语义去重用）
        self.stats = {
            "layer_a_uuid5_skipped": 0,
            "layer_b_offset_skipped": 0,
            "layer_c_similarity_skipped": 0,
            "total_passed": 0
        }
    
    def should_capture(self, content: str, source_key: str = "", offset: int = 0) -> bool:
        """
        三层去重判断。返回 True 表示应该捕获。
        
        调用顺序：Layer A → Layer B → Layer C
        任一命中 = 跳过 = 返回 False
        """
        # ── Layer A: UUID5 内容级去重 ──
        uid = content_uuid5(content)
        if uid in self._uuid5_seen:
            self.stats["layer_a_uuid5_skipped"] += 1
            return False
        
        # ── Layer B: Offset 级增量 ──
        if source_key and offset > 0:
            last_offset = self._offsets.get(source_key, 0)
            if offset <= last_offset:
                self.stats["layer_b_offset_skipped"] += 1
                return False
            self._offsets[source_key] = offset
        
        # ── Layer C: 语义相似度去重 ──
        for hist_content in self._history[-100:]:
            sim = text_similarity(content, hist_content)
            if sim > 0.85:
                self.stats["layer_c_similarity_skipped"] += 1
                return False
        
        # 全部通过
        self._uuid5_seen.add(uid)
        self._history.append(content)
        self.stats["total_passed"] += 1
        return True
    
    def reset_stats(self):
        self.stats = {k: 0 for k in self.stats}


def text_similarity(a: str, b: str) -> float:
    """Simple Jaccard similarity based on word overlap (no embedding needed)."""
    words_a = set(re.findall(r'\w+', a.lower()))
    words_b = set(re.findall(r'\w+', b.lower()))
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def deduplicate_entries(entries: list[dict], threshold: float = 0.85) -> list[dict]:
    """Merge entries with similarity > threshold (batch mode)."""
    if not entries:
        return entries
    
    merged = []
    used = set()
    
    for i, entry in enumerate(entries):
        if i in used:
            continue
        group = [entry]
        used.add(i)
        
        for j in range(i + 1, len(entries)):
            if j in used:
                continue
            sim = text_similarity(
                entry.get("content", ""),
                entries[j].get("content", "")
            )
            if sim > threshold:
                group.append(entries[j])
                used.add(j)
        
        if len(group) > 1:
            combined = entry.copy()
            combined["content"] = " | ".join(g.get("content", "")[:100] for g in group)
            combined["merged_from"] = len(group)
            merged.append(combined)
        else:
            merged.append(entry)
    
    return merged


def detect_milestones(entries: list[dict]) -> list[dict]:
    """Detect milestone events from memory entries."""
    milestones = []
    milestone_keywords = [
        "完成", "发布", "上线", "部署", "启动", "建立", "发布",
        "v1.0", "v2.0", "v3.0", "正式", "上线", "交付"
    ]
    
    for entry in entries:
        content = entry.get("content", "")
        for kw in milestone_keywords:
            if kw in content:
                milestones.append({
                    "date": entry.get("date", ""),
                    "keyword": kw,
                    "content": content[:150],
                    "type": "milestone"
                })
                break
    
    return milestones


if __name__ == "__main__":
    # Test Layer A
    filt = DedupFilter()
    assert filt.should_capture("hello world", "test.jsonl", 100) == True
    assert filt.should_capture("hello world", "test.jsonl", 100) == False  # UUID5 hit
    print(f"Layer A (UUID5): {filt.stats['layer_a_uuid5_skipped']} skipped")
    
    # Test Layer B
    assert filt.should_capture("different content", "test.jsonl", 100) == False  # offset hit
    print(f"Layer B (offset): {filt.stats['layer_b_offset_skipped']} skipped")
    
    # Test Layer C
    assert filt.should_capture("hello world again", "test.jsonl", 200) == False  # similar
    print(f"Layer C (similarity): {filt.stats['layer_c_similarity_skipped']} skipped")
    
    print(f"Total passed: {filt.stats['total_passed']}")
    print("Three-layer dedup: OK")
