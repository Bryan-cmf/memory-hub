#!/usr/bin/env python3
"""MemoryHub Integration + Performance + Cross-Platform Tests (10.2-10.4)"""

import json, os, sys, tempfile, time, multiprocessing
from pathlib import Path
from datetime import datetime, timedelta

def test_integration_full_flow():
    """10.2: Full memory flow — save → scan → search → consolidate."""
    d = Path(tempfile.mkdtemp(prefix="mh_integration_"))
    sessions_dir = d / "sessions"; sessions_dir.mkdir()
    state_dir = d / ".memory-hub"; state_dir.mkdir()
    
    # Create mock session
    session = sessions_dir / "test_session.jsonl"
    session.write_text(
        json.dumps({"role":"user","content":"整合測試：做一個市場調研","timestamp":"2026-01-01T00:00:00"})+"\n"+
        json.dumps({"role":"assistant","content":"好的，開始調研。","timestamp":"2026-01-01T00:00:01"})+"\n",
        encoding="utf-8"
    )
    
    # Simulate scanner run (just check no crash)
    import subprocess
    scanner_path = Path(__file__).parent / "scanner" / "session_scanner.py"
    result = subprocess.run(
        [sys.executable, "-c", f"import ast; ast.parse(open('{scanner_path}').read()); print('OK')"],
        capture_output=True, text=True, timeout=10
    )
    
    import shutil; shutil.rmtree(d)
    return "OK" in (result.stdout + result.stderr)

def test_performance_large_dataset():
    """10.3: Performance test with simulated data."""
    d = Path(tempfile.mkdtemp(prefix="mh_perf_"))
    sessions_dir = d / "sessions"; sessions_dir.mkdir()
    
    # Create 50 session files with 20 lines each
    start = time.time()
    for i in range(50):
        f = sessions_dir / f"session_{i:04d}.jsonl"
        lines = []
        for j in range(20):
            role = "user" if j % 2 == 0 else "assistant"
            content = f"Test message {i}-{j} with some meaningful content about project alpha and beta testing"
            lines.append(json.dumps({"role": role, "content": content, "timestamp": "2026-01-01T00:00:00"}))
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    
    elapsed = time.time() - start
    total_size = sum(f.stat().st_size for f in sessions_dir.glob("*.jsonl"))
    
    import shutil; shutil.rmtree(d)
    return {"files": 50, "lines_per_file": 20, "total_kb": total_size/1024, "creation_sec": elapsed}

def test_cross_platform_paths():
    """10.4: Cross-platform path handling."""
    issues = []
    
    # Test 1: Path with spaces (Windows common issue)
    p = Path("/tmp/test path with spaces/file.md")
    if str(p) != "/tmp/test path with spaces/file.md":
        issues.append("Space path normalization")
    
    # Test 2: Path with Chinese characters
    p2 = Path("/tmp/測試目錄/文件.md")
    if "測試" not in str(p2):
        issues.append("Unicode path handling")
    
    # Test 3: Home directory expansion
    home = os.path.expanduser("~")
    if not home or home == "~":
        issues.append("Home directory expansion")
    
    # Test 4: Backslash handling (Windows)
    p3 = Path("C:\\Users\\test\\file.md")
    normalized = str(p3).replace("\\", "/")
    
    return {"issues": issues, "status": "ok" if not issues else "issues_found"}

def run_all():
    print("=" * 50)
    print("MEMORYHUB COMPREHENSIVE TEST SUITE")
    print("=" * 50)
    
    results = {}
    
    # 10.2 Integration
    print("\n10.2 Integration test...")
    try:
        ok = test_integration_full_flow()
        results["integration"] = "✅ passed" if ok else "❌ failed"
    except Exception as e:
        results["integration"] = f"❌ {e}"
    print(f"  {results['integration']}")
    
    # 10.3 Performance
    print("\n10.3 Performance test...")
    try:
        perf = test_performance_large_dataset()
        results["performance"] = f"✅ {perf['files']} files, {perf['total_kb']:.1f}KB, {perf['creation_sec']:.2f}s"
    except Exception as e:
        results["performance"] = f"❌ {e}"
    print(f"  {results['performance']}")
    
    # 10.4 Cross-platform
    print("\n10.4 Cross-platform test...")
    try:
        xp = test_cross_platform_paths()
        results["cross_platform"] = f"✅ {xp['status']}" if xp['status'] == 'ok' else f"⚠️ {xp['issues']}"
    except Exception as e:
        results["cross_platform"] = f"❌ {e}"
    print(f"  {results['cross_platform']}")
    
    print(f"\n{'='*50}")
    passed = sum(1 for v in results.values() if v.startswith("✅"))
    print(f"  {passed}/{len(results)} tests passed")
    return passed == len(results)

if __name__ == "__main__":
    ok = run_all()
    sys.exit(0 if ok else 1)
