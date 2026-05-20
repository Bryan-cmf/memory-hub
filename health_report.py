#!/usr/bin/env python3
"""MemoryHub Health Report v1.2 — 整合 Capture Daemon + Qdrant + Scanner 健康检查"""

import json, os, sys, subprocess
from pathlib import Path
from datetime import datetime, timezone

MH_DIR = Path(os.path.expanduser("~/.memory-hub"))
MEMORY_ROOT = Path(os.path.expanduser("~/.openclaw/workspace/memory"))


def _check_qdrant() -> dict:
    """检查 Qdrant 服务状态。"""
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:6333/health")
        urllib.request.urlopen(req, timeout=3)
        return {"status": "online", "url": "http://localhost:6333"}
    except Exception as e:
        return {"status": "offline", "error": str(e)[:100]}


def _check_capture_daemon() -> dict:
    """检查 Capture Daemon 进程状态 (v1.2)。"""
    pidfile = MH_DIR / "capture_daemon.pid"
    result = {"status": "not_running", "pid": None}
    
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, 0)
            result["status"] = "running"
            result["pid"] = pid
        except (ValueError, OSError, ProcessLookupError):
            result["status"] = "stale_pidfile"
    
    # Check captured data
    captured_dir = MH_DIR / "captured"
    if captured_dir.exists():
        result["capture_files"] = len(list(captured_dir.rglob("*.jsonl")))
        result["capture_platforms"] = [d.name for d in captured_dir.iterdir() if d.is_dir()]
    else:
        result["capture_files"] = 0
        result["capture_platforms"] = []
    
    return result


def _check_scanner() -> dict:
    """检查 Session Scanner。"""
    try:
        r = subprocess.run(
            ["pgrep", "-f", "session_scanner.py"],
            capture_output=True, text=True, timeout=5
        )
        if r.stdout.strip():
            pids = r.stdout.strip().split("\n")
            return {"status": "running", "pids": [int(p) for p in pids if p]}
        return {"status": "stopped"}
    except Exception:
        return {"status": "unknown"}


def _check_memory_files() -> dict:
    """检查文件记忆层完整性。"""
    result = {
        "daily_logs": 0,
        "weeklies": 0,
        "monthlies": 0,
        "yearlies": 0,
        "entities": {},
        "total_size_bytes": 0
    }
    
    if not MEMORY_ROOT.exists():
        return result
    
    for f in MEMORY_ROOT.rglob("*.md"):
        try:
            s = f.stat().st_size
            result["total_size_bytes"] += s
            
            if "_yearly" in f.name:
                result["yearlies"] += 1
            elif "_monthly" in f.name:
                result["monthlies"] += 1
            elif "_weekly" in f.name:
                result["weeklies"] += 1
            elif not f.name.startswith("_") and f.parent.name.isdigit() and len(f.parent.name) == 2:
                result["daily_logs"] += 1
        except OSError:
            continue
    
    # Entities check
    entities_dir = MEMORY_ROOT / "entities"
    if entities_dir.exists():
        for ef in entities_dir.glob("*.md"):
            result["entities"][ef.stem] = ef.stat().st_size
    
    return result


def generate_full_health_report() -> dict:
    """生成完整健康报告（v1.2 — 整合所有组件）。"""
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.2.0",
        "components": {
            "qdrant": _check_qdrant(),
            "capture_daemon": _check_capture_daemon(),
            "scanner": _check_scanner(),
            "memory_files": _check_memory_files()
        },
        "summary": {
            "overall_status": "healthy",
            "issues": []
        }
    }
    
    # Generate summary
    if report["components"]["qdrant"]["status"] == "offline":
        report["summary"]["overall_status"] = "degraded"
        report["summary"]["issues"].append("Qdrant offline — vector search unavailable")
    
    if report["components"]["capture_daemon"]["status"] != "running":
        report["summary"]["overall_status"] = "degraded"
        report["summary"]["issues"].append("Capture daemon not running")
    
    if report["components"]["scanner"]["status"] == "stopped":
        report["summary"]["overall_status"] = "degraded"
        report["summary"]["issues"].append("Session scanner stopped")
    
    mem = report["components"]["memory_files"]
    if mem["daily_logs"] == 0:
        report["summary"]["issues"].append("No daily logs found")
    
    return report


if __name__ == "__main__":
    report = generate_full_health_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
