#!/usr/bin/env python3
"""MemoryHub Full System Test — end-to-end automated test suite.

Usage:
    python3 tests/run_full_test.py

Simulates a complete user journey:
    1. Environment check
    2. Start Qdrant
    3. Create isolated test environment
    4. Generate mock platform sessions
    5. Install MemoryHub
    6. Start daemon
    7. Verify Mode B captures (filesystem scan)
    8. Verify Mode A captures (MCP /hook)
    9. Verify all 6 Dashboard APIs
    10. Verify memory-hub verify command
    11. Verify MCP server
    12. Cleanup
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# ── Config ────────────────────────────────────────

TEST_PORT = 3999
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_HOME = Path("/tmp/memoryhub_test_home")

# ── Helpers ───────────────────────────────────────

passed = 0
failed = 0
skipped = 0

B = "\033[1m"; R = "\033[31m"; G = "\033[32m"; Y = "\033[33m"; N = "\033[0m"


def check(name, condition, detail="", warn_only=False):
    global passed, failed, skipped
    if condition:
        passed += 1
        print(f"  {G}✅{N} {name}{' — ' + detail if detail else ''}")
    elif warn_only:
        skipped += 1
        print(f"  {Y}⚠️{N} {name}{' — ' + detail if detail else ''} [SKIPPED]")
    else:
        failed += 1
        print(f"  {R}❌{N} {name}{' — ' + detail if detail else ''}")


def get_json(url, timeout=5):
    try:
        req = urllib.request.Request(url, method="GET")
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def post_json(url, data, timeout=5):
    try:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(url, data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


# ── Test Steps ────────────────────────────────────


def step_environment():
    print(f"\n{B}Step 1-2: Environment Check{N}")
    print("─" * 50)

    check("Python 3.9+", sys.version_info >= (3, 9),
          f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    r = run([sys.executable, "-m", "pip", "--version"])
    check("pip available", r.returncode == 0, r.stdout.strip()[:40] if r.returncode == 0 else "")

    r = run(["docker", "info"])
    docker_ok = r.returncode == 0
    check("Docker available", docker_ok, warn_only=True)

    # Qdrant
    if docker_ok:
        r = run(["curl", "-sf", "http://localhost:6333/collections"])
        if r.returncode != 0:
            print("  Starting Qdrant...")
            run(["docker", "run", "-d", "--name", "mh-test-qdrant",
                 "-p", "6333:6333", "qdrant/qdrant"])
            time.sleep(5)
        r2 = run(["curl", "-sf", "http://localhost:6333/collections"])
        check("Qdrant running", r2.returncode == 0)
    else:
        check("Qdrant running", False, "Docker not found — vector tests will fail", warn_only=True)


def step_mock_data():
    print(f"\n{B}Step 3-5: Mock Data Generation{N}")
    print("─" * 50)

    # Clean + create test home
    if TEST_HOME.exists():
        shutil.rmtree(TEST_HOME)
    TEST_HOME.mkdir(parents=True)

    # Generate mock sessions
    sys.path.insert(0, str(PROJECT_ROOT))
    import importlib
    mock_data = importlib.import_module("tests.mock_data")
    generate_all = mock_data.generate_all
    count_messages = mock_data.count_messages

    os.environ["HOME"] = str(TEST_HOME)
    files = generate_all(TEST_HOME)
    expected = count_messages(files)

    for platform in ["openclaw", "hermes", "deepseek", "claude"]:
        fp = files.get(platform)
        exists = fp.exists() if fp else False
        size = fp.stat().st_size if exists else 0
        check(f"{platform} mock session created", exists and size > 100,
              f"{size} bytes, ~{expected.get(platform, 0)} msgs")

    check("Test home created", TEST_HOME.exists(), str(TEST_HOME))
    return expected


def step_install():
    print(f"\n{B}Step 6: Package Installation{N}")
    print("─" * 50)

    r = run([sys.executable, "-m", "pip", "install", "-e", str(PROJECT_ROOT), "--quiet"],
            cwd=str(PROJECT_ROOT))
    check("pip install memory-hub", r.returncode == 0,
          r.stderr.strip()[-80:] if r.returncode != 0 else "ok")

    # memory-hub may not be on PATH — use module invocation
    r = run([sys.executable, "-m", "memory_hub.cli", "--help"])
    check("memory-hub CLI installed", r.returncode == 0)


def step_start_daemon():
    global daemon_proc
    print(f"\n{B}Step 7: Daemon Startup{N}")
    print("─" * 50)

    # Clear offsets so daemon scans all mock files fresh
    mh_dir = TEST_HOME / ".memory-hub"
    mh_dir.mkdir(parents=True, exist_ok=True)
    offset_file = mh_dir / "capture_offsets.json"
    if offset_file.exists():
        offset_file.unlink()

    # Start daemon with --port flag
    daemon_proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "capture_daemon.py"), "--port", str(TEST_PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "HOME": str(TEST_HOME)},
    )

    # Wait for startup + first scan
    time.sleep(8)
    alive = daemon_proc.poll() is None
    check("Daemon process alive", alive)

    if not alive:
        return False

    # Verify dashboard
    try:
        req = urllib.request.Request(f"http://localhost:{TEST_PORT}/", method="GET")
        resp = urllib.request.urlopen(req, timeout=5)
        check("Dashboard HTTP 200", resp.status == 200, f"HTTP {resp.status}")
    except Exception as e:
        check("Dashboard HTTP 200", False, str(e)[:60])
        return False

    return True


def step_mode_b(expected_msgs):
    print(f"\n{B}Step 8: Mode B Verification (Filesystem Scan){N}")
    print("─" * 50)

    state = get_json(f"http://localhost:{TEST_PORT}/api/state")
    if "error" in state:
        check("GET /api/state", False, state["error"])
        return

    platforms = state.get("platforms", {})

    # OpenClaw, DeepSeek, Hermes should have captures
    for pid in ["openclaw", "deepseek", "hermes"]:
        captured = platforms.get(pid, {}).get("captured", 0)
        check(f"Mode B: {pid} captures > 0", captured > 0, f"got {captured}")

    # Claude Code event log has no role/content → 0 captures expected
    claude_captured = platforms.get("claude", {}).get("captured", 0)
    check("Mode B: Claude Code = 0 (event log, expected)",
          claude_captured == 0, f"got {claude_captured}")

    check("Mode B count >= 3 (platforms with captures)",
          state.get("mode_b_count", 0) >= 3, f"got {state['mode_b_count']}")

    check("Total captures > 0", state.get("total_captured", 0) > 0,
          f"got {state['total_captured']}")


def step_mode_a():
    print(f"\n{B}Step 9: Mode A Verification (MCP /hook){N}")
    print("─" * 50)

    before = get_json(f"http://localhost:{TEST_PORT}/api/state")

    for platform in ["openclaw", "hermes", "deepseek", "claude"]:
        result = post_json(f"http://localhost:{TEST_PORT}/hook", {
            "platform": platform,
            "role": "user",
            "content": f"[TEST] Mode A capture from {platform} at {time.strftime('%H:%M:%S')}",
        })
        check(f"POST /hook {platform}", result.get("status") == "captured",
              result.get("error", str(result)[:40]))

    time.sleep(1)
    after = get_json(f"http://localhost:{TEST_PORT}/api/state")

    check("Mode A count = 4", after.get("mode_a_count", 0) == 4,
          f"got {after['mode_a_count']}")

    # Claude should now have 1 capture via Mode A
    claude_after = after["platforms"]["claude"]["captured"]
    check("Claude Code now captured via Mode A", claude_after >= 1,
          f"got {claude_after}")

    check("Total increased", after["total_captured"] > before["total_captured"],
          f"{before['total_captured']} → {after['total_captured']}")


def step_apis():
    print(f"\n{B}Step 10: Dashboard API Verification{N}")
    print("─" * 50)

    # /api/state
    state = get_json(f"http://localhost:{TEST_PORT}/api/state")
    check("/api/state returns valid JSON", "platforms" in state and "total_captured" in state)

    # /api/messages
    msgs = get_json(f"http://localhost:{TEST_PORT}/api/messages?limit=10")
    check("/api/messages returns list", isinstance(msgs, list) and len(msgs) > 0,
          f"{len(msgs) if isinstance(msgs, list) else 'not a list'} messages")

    # /api/search
    search = get_json(f"http://localhost:{TEST_PORT}/api/search?q=TEST&limit=5")
    check("/api/search returns results", "results" in search,
          f"{search.get('total', '?')} matches")

    # /api/history
    history = get_json(f"http://localhost:{TEST_PORT}/api/history")
    check("/api/history returns hourly data", "hourly" in history)
    check("/api/history returns daily data", "daily" in history)

    # /api/collections
    cols = get_json(f"http://localhost:{TEST_PORT}/api/collections")
    check("/api/collections returns data", isinstance(cols, dict) and len(cols) > 0,
          f"{len(cols)} collections" if isinstance(cols, dict) else "not a dict")

    # /api/messages with limit
    msgs2 = get_json(f"http://localhost:{TEST_PORT}/api/messages?limit=3")
    check("/api/messages respects limit", isinstance(msgs2, list) and len(msgs2) <= 3,
          f"{len(msgs2) if isinstance(msgs2, list) else '?'} returned")


def step_verify():
    print(f"\n{B}Step 11: memory-hub verify{N}")
    print("─" * 50)

    r = run([sys.executable, "-m", "memory_hub.verify"],
            env={**os.environ, "HOME": str(TEST_HOME)})

    output = r.stdout + r.stderr
    check("verify.py executes", r.returncode == 0,
          f"exit code {r.returncode}")

    # Check key components reported OK
    ok_count = output.count("✅")
    fail_count = output.count("❌")
    check("verify shows passes", ok_count >= 3, f"{ok_count} OK checks")
    check("verify shows ≤1 failures (test isolation OK)", fail_count <= 1,
          f"{fail_count} failures (Qdrant/file-store in isolation)" if fail_count else "all passed")


def step_mcp_server():
    print(f"\n{B}Step 12: MCP Server Verification{N}")
    print("─" * 50)

    r = run([sys.executable, "-c",
             "from memory_hub.server.mcp_server import TOOLS; print(len(TOOLS))"],
            cwd=str(PROJECT_ROOT))
    check("MCP Server imports", r.returncode == 0,
          f"exit {r.returncode}" if r.returncode else "ok")

    n_tools = r.stdout.strip()
    check("MCP Server has 6 tools", n_tools == "6",
          f"got {n_tools} tools: mem_save, mem_search, mem_stats, mem_list, mem_delete, capture_send")

    # Verify all tool names
    r2 = run([sys.executable, "-c",
              "from memory_hub.server.mcp_server import TOOLS; print(','.join(sorted(TOOLS.keys())))"],
             cwd=str(PROJECT_ROOT))
    tools = r2.stdout.strip().split(",")
    expected = ["capture_send", "mem_delete", "mem_list", "mem_save", "mem_search", "mem_stats"]
    check("All expected tools present", sorted(tools) == sorted(expected),
          f"got {sorted(tools)}")


def step_cleanup():
    global daemon_proc
    print(f"\n{B}Step 13: Cleanup{N}")
    print("─" * 50)

    if daemon_proc:
        daemon_proc.terminate()
        daemon_proc.wait(timeout=5)
        check("Daemon stopped", True)

    if TEST_HOME.exists():
        shutil.rmtree(TEST_HOME)
        check("Test environment cleaned", not TEST_HOME.exists())
    else:
        check("Test environment cleaned", True, "already removed")


# ── Main ──────────────────────────────────────────

def main():
    global daemon_proc, passed, failed, skipped
    daemon_proc = None

    print(f"\n{B}🧪 MemoryHub Full System Test{N}")
    print(f"{'='*50}")
    print(f"  Project: {PROJECT_ROOT}")
    print(f"  Test home: {TEST_HOME}")
    print(f"  Test port: {TEST_PORT}")

    try:
        step_environment()
        expected_msgs = step_mock_data()
        step_install()

        if not step_start_daemon():
            print(f"\n{R}Daemon failed to start — aborting remaining tests.{N}")
            failed += 1
        else:
            # Wait for second scan cycle to catch all mock data
            print("\n  Waiting for scan cycle (5s)...")
            time.sleep(7)

            step_mode_b(expected_msgs)
            step_mode_a()
            step_apis()
            step_verify()
            step_mcp_server()

    except KeyboardInterrupt:
        print(f"\n{Y}Test interrupted by user.{N}")
    except Exception as e:
        print(f"\n{R}Unexpected error: {e}{N}")
        import traceback
        traceback.print_exc()
        failed += 1
    finally:
        step_cleanup()

    # Final report
    total = passed + failed + skipped
    print(f"\n{B}{'═'*50}{N}")
    print(f"{B}  MemoryHub Full Test Report{N}")
    print(f"{'═'*50}")
    print(f"  Total:   {total}")
    print(f"  {G}Passed:  {passed} ✅{N}")
    if failed:
        print(f"  {R}Failed:  {failed} ❌{N}")
    if skipped:
        print(f"  {Y}Skipped: {skipped} ⚠️{N}")
    print(f"{'═'*50}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    daemon_proc = None
    sys.exit(main())
