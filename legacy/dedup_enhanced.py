#!/usr/bin/env python3
"""
MemoryHub 增強去重引擎 v2.2 (Per-Platform Dedup)
===================================================
🔴 核心原則：每個平台（OpenClaw/Hermes/DeepSeek/Claude）是獨立智能體，
  各自記憶不互相去重。只在同一文件內去重。

功能：
  1. 按文件獨立掃描、獨立去重
  2. MD5 內容 hash（跨重啟穩定）
  3. 每個 hash 組保留最新一條（按 timestamp）
  4. 自動備份（.dedup_backup）

用法：
  python dedup_enhanced.py --dry-run     # 預覽
  python dedup_enhanced.py               # 執行
  python dedup_enhanced.py --stats        # 統計
"""

import json, sys, hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

HKT = timezone(timedelta(hours=8))
NOW = datetime.now(HKT)
CAPTURE_DIR = Path.home() / ".memory-hub" / "captured"


def content_hash(content: str) -> str:
    """穩定的內容 hash (MD5)，正規化空白後取前 500 字"""
    normalized = " ".join(str(content).split())[:500]
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def dedup_file(filepath: Path, dry_run: bool = True) -> dict:
    """
    對單一文件進行去重：
    - 讀取所有行
    - 按 content hash 分組
    - 每組保留 timestamp 最新的 1 條
    - 其餘標記為重複
    """
    if not filepath.exists():
        return {"file": str(filepath), "error": "not found"}
    
    messages = []
    parse_errors = 0
    
    for line in filepath.read_text(encoding="utf-8").split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            content = str(msg.get("content", ""))
            if len(content) < 10:  # 跳過太短的噪音
                continue
            messages.append({
                "hash": content_hash(content),
                "content": content,
                "timestamp": msg.get("timestamp", msg.get("captured_at", "")),
                "raw": line,
            })
        except json.JSONDecodeError:
            parse_errors += 1
    
    if not messages:
        return {
            "file": str(filepath),
            "original": 0, "kept": 0, "removed": 0,
            "unique_hashes": 0, "multi_groups": 0,
            "parse_errors": parse_errors, "dry_run": dry_run,
        }
    
    # 按 hash 分組（只在此文件內）
    hash_groups = defaultdict(list)
    for i, m in enumerate(messages):
        hash_groups[m["hash"]].append(i)
    
    # 標記保留的索引
    keep_indices = set()
    multi_groups = 0
    
    for h, indices in hash_groups.items():
        if len(indices) == 1:
            keep_indices.add(indices[0])  # 唯一拷貝，直接保留
        else:
            multi_groups += 1
            # 取 timestamp 最新的
            best_idx = max(indices, key=lambda i: messages[i].get("timestamp", ""))
            keep_indices.add(best_idx)
    
    # 構建輸出
    kept = sorted([messages[i] for i in keep_indices], key=lambda m: m.get("timestamp", ""))
    removed = len(messages) - len(kept)
    
    if not dry_run and removed > 0:
        # 備份
        backup_path = Path(str(filepath) + ".dedup_backup")
        import shutil
        shutil.copy2(filepath, backup_path)
        
        # 寫入去重後的內容
        with open(filepath, "w", encoding="utf-8") as f:
            for m in kept:
                f.write(m["raw"] + "\n")
    
    return {
        "file": str(filepath),
        "original": len(messages),
        "kept": len(kept),
        "removed": removed,
        "unique_hashes": len(hash_groups),
        "multi_groups": multi_groups,
        "parse_errors": parse_errors,
        "dry_run": dry_run,
    }


def scan_all_files() -> list[Path]:
    """掃描所有 captured 目錄下的 jsonl 文件"""
    files = []
    if CAPTURE_DIR.exists():
        for f in CAPTURE_DIR.rglob("*.jsonl"):
            if f.is_file() and "dedup_backup" not in str(f):
                files.append(f)
    return sorted(files)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="MemoryHub Per-Platform Dedup v2.2")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--stats", action="store_true", help="Show stats only")
    args = parser.parse_args()
    
    files = scan_all_files()
    print(f"🔍 MemoryHub Dedup v2.2 (Per-Platform)")
    print(f"   Scanning: {CAPTURE_DIR}")
    print(f"   Files: {len(files)}")
    print(f"   Mode: {'DRY RUN' if args.dry_run else 'LIVE'}  |  Dedup scope: within each file only")
    print()
    
    total_original = 0
    total_kept = 0
    total_removed = 0
    
    results = []
    for fp in files:
        r = dedup_file(fp, dry_run=args.dry_run or args.stats)
        results.append(r)
        
        total_original += r["original"]
        total_kept += r["kept"]
        total_removed += r["removed"]
        
        if r["removed"] > 0:
            pct = r["removed"] / max(1, r["original"]) * 100
            platform = fp.parent.parent.name if fp.parent.parent.name != "captured" else fp.parent.name
            print(f"  {'🔍' if args.dry_run or args.stats else '✅'} {platform}/{fp.parent.name}/{fp.name}: "
                  f"{r['original']} → {r['kept']} ({r['removed']} dupes, {pct:.0f}%) "
                  f"[{r['unique_hashes']} unique, {r['multi_groups']} multi-groups]")
    
    print()
    print(f"{'='*60}")
    print(f"📊 Summary: {total_original} → {total_kept} ({total_removed} dupes removed, {total_removed/max(1,total_original)*100:.1f}%)")
    
    if args.stats:
        # Show platform-level summary
        from collections import defaultdict
        platform_stats = defaultdict(lambda: {"orig": 0, "kept": 0, "removed": 0})
        for r in results:
            p = Path(r["file"]).parent.parent.name
            platform_stats[p]["orig"] += r["original"]
            platform_stats[p]["kept"] += r["kept"]
            platform_stats[p]["removed"] += r["removed"]
        
        print()
        print("📊 By Platform:")
        for p in sorted(platform_stats.keys()):
            s = platform_stats[p]
            pct = s["removed"] / max(1, s["orig"]) * 100
            print(f"  {p}: {s['orig']} → {s['kept']} ({s['removed']} dupes, {pct:.0f}%)")
    
    if args.dry_run:
        print(f"\n🔍 DRY RUN — 不修改文件")
        print(f"   將移除 {total_removed} 條文件內重複消息")


if __name__ == "__main__":
    main()
