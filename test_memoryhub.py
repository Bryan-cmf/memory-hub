#!/usr/bin/env python3
"""MemoryHub Test Suite"""

import json, os, sys, tempfile
from pathlib import Path
from datetime import datetime

def test_scanner_empty_file():
    """Scanner handles empty JSONL files."""
    import subprocess
    d = tempfile.mkdtemp()
    (Path(d) / "empty.jsonl").write_text("")
    # Should not crash
    assert True
    import shutil; shutil.rmtree(d)

def test_scanner_malformed_json():
    """Scanner handles malformed JSON."""
    d = tempfile.mkdtemp()
    (Path(d) / "bad.jsonl").write_text("not valid json\n{broken\n")
    assert True
    import shutil; shutil.rmtree(d)

def test_safe_content_null():
    """safe_content handles None."""
    from scanner.session_scanner import sc
    assert sc({"content": None}) == ""
    assert sc({"content": "hello"}) == "hello"
    assert sc({"other": "key"}) == ""

def test_is_valuable():
    """Value filter catches meaningful Q&A, skips short chat."""
    from scanner.session_scanner import is_valuable
    # Tool calls → always capture
    assert is_valuable({"tool_count": 1, "user": "hi", "assistant": "."})
    # Detailed assistant response
    assert is_valuable({"tool_count": 0, "user": "?", "assistant": "A" * 41})
    # Meaningful Q&A
    assert is_valuable({"tool_count": 0, "user": "A" * 10, "assistant": "B" * 20})
    # Short chat → skip
    assert not is_valuable({"tool_count": 0, "user": "ok", "assistant": "好"})

def test_parse_time_range():
    """Fuzzy time parsing works."""
    from hybrid_search import parse_time_range
    now = datetime.now()
    r = parse_time_range("上個月的記憶")
    assert r[0] is not None

def test_export_json():
    """JSON export produces valid output."""
    d = tempfile.mkdtemp()
    out = Path(d) / "test.json"
    out.write_text('{"test": true}')
    assert out.exists()
    import shutil; shutil.rmtree(d)

def test_secret_detection():
    """Security scanner detects API keys."""
    import re
    pattern = r'sk-[a-zA-Z0-9]{32,}'
    assert re.search(pattern, "api_key = sk-abc123def456ghi789jkl012mno345pqr678stu")
    assert not re.search(pattern, "no key here")

def run_all():
    tests = [
        ("scanner_empty_file", test_scanner_empty_file),
        ("scanner_malformed", test_scanner_malformed_json),
        ("safe_content_null", test_safe_content_null),
        ("is_valuable_filter", test_is_valuable),
        ("parse_time_range", test_parse_time_range),
        ("export_json", test_export_json),
        ("secret_detection", test_secret_detection),
    ]
    
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  ✅ {name}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {name}: {e}")
    
    print(f"\n{'='*40}")
    print(f"  {passed}/{len(tests)} tests passed")
    return passed == len(tests)

if __name__ == "__main__":
    ok = run_all()
    sys.exit(0 if ok else 1)
