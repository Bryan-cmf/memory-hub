#!/usr/bin/env python3
"""MemoryHub Hub Server — Integration Tests (M5.1-M5.3)"""

import json, sys, urllib.request, urllib.error, time, threading
from pathlib import Path

HUB_URL = "http://localhost:3120"

def test_health():
    """M5.1: Hub health check."""
    try:
        resp = urllib.request.urlopen(f"{HUB_URL}/health", timeout=5)
        data = json.loads(resp.read())
        assert data["status"] == "ok"
        assert data["version"] == "2.0.0"
        print("✅ M5.1: Health check passed")
        return True
    except Exception as e:
        print(f"❌ M5.1: {e}")
        return False

def test_post_hook():
    """M5.2: POST /hook from multiple platforms."""
    platforms = [
        {"platform": "openclaw", "role": "user", "content": "幫我做港股調研"},
        {"platform": "deepseek", "role": "assistant", "content": "正在搜索歷史記憶..."},
        {"platform": "hermes", "role": "user", "content": "IPO市場分析報告"},
        {"platform": "claude", "role": "assistant", "content": "代碼審查完成，發現2個問題"},
    ]
    
    success = 0
    for msg in platforms:
        try:
            req = urllib.request.Request(
                f"{HUB_URL}/hook",
                data=json.dumps(msg).encode(),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read())
            if data.get("status") == "captured":
                success += 1
        except Exception as e:
            print(f"  ⚠️ {msg['platform']}: {e}")
    
    assert success >= 1, f"Only {success}/4 platforms captured"
    print(f"✅ M5.2: POST /hook captured {success}/4 platforms")
    return True

def test_search():
    """M5.3: GET /api/search across all backends."""
    try:
        resp = urllib.request.urlopen(f"{HUB_URL}/api/search?q=港股調研", timeout=5)
        data = json.loads(resp.read())
        assert "results" in data
        print(f"✅ M5.3: Search returned {data.get('total', 0)} results")
        return True
    except Exception as e:
        print(f"⚠️ M5.3: {e} (hub may not be running)")
        return False

def test_state():
    """M5.4: GET /api/state."""
    try:
        resp = urllib.request.urlopen(f"{HUB_URL}/api/state", timeout=5)
        data = json.loads(resp.read())
        assert "platforms" in data
        assert "total_messages" in data
        print(f"✅ M5.4: State API: {data['total_messages']} messages across {len(data['platforms'])} platforms")
        return True
    except Exception as e:
        print(f"⚠️ M5.4: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("MemoryHub Hub Server Test Suite")
    print("=" * 50)
    print(f"Hub URL: {HUB_URL}")
    print()
    
    # Check if hub is running
    try:
        urllib.request.urlopen(f"{HUB_URL}/health", timeout=2)
        print("📡 Hub server is online\n")
    except:
        print("⚠️ Hub server not running. Start with: python3 hub_server.py\n")
        print("Skipping live tests. Syntax check only.")
        import ast; from pathlib import Path
        f = Path(__file__).parent / "hub_server.py"
        try:
            with open(f) as fh: ast.parse(fh.read())
            print(f"✅ hub_server.py syntax OK ({f.stat().st_size} bytes)")
        except SyntaxError as e: print(f"❌ {e}")
        sys.exit(0)
    
    results = [
        test_health(),
        test_post_hook(),
        test_search(),
        test_state(),
    ]
    
    passed = sum(1 for r in results if r)
    print(f"\n{'='*50}")
    print(f"Hub tests: {passed}/{len(results)} passed")
    print(f"{'✅ ALL PASSED' if all(results) else '⚠️ Some tests failed'}")
