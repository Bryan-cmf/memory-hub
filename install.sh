#!/usr/bin/env python3
"""MemoryHub One-Click Installer
Preferred: pip install memory-hub
Fallback: curl | python3 (from GitHub)
Usage:
    pip install memory-hub
    OR
    curl -fsSL https://raw.githubusercontent.com/bryan-cmf/memory-hub/main/install.sh | python3
"""

import os, sys, subprocess, tempfile, shutil
from pathlib import Path

REPO_URL = "https://github.com/bryan-cmf/memory-hub.git"
B = "\033[1m"; G = "\033[32m"; C = "\033[36m"; Y = "\033[33m"; N = "\033[0m"

def _post_install():
    """Post-install: check PATH and run setup."""
    # 4. Check if memory-hub is on PATH
    try:
        r = subprocess.run(["memory-hub", "--help"], capture_output=True, timeout=5)
        on_path = r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        on_path = False

    v = f"{sys.version_info.major}.{sys.version_info.minor}"
    if not on_path:
        # Find where pip installed it
        r = subprocess.run([sys.executable, "-m", "pip", "show", "memory-hub"],
                          capture_output=True, text=True)
        loc = "~/Library/Python/*/bin"
        for line in r.stdout.split("\n"):
            if line.startswith("Location:"):
                loc = line.split(":", 1)[1].strip() + "/../../bin"
        print(f"\n   {Y}⚠️  'memory-hub' not on PATH{N}")
        print(f"   Add this to your shell config:")
        print(f"   {C}export PATH=\"$HOME/Library/Python/{v}/bin:\\$PATH\"{N}")
        print(f"   Or use: {C}python3 -m memory_hub.cli{N}\n")

    # 5. Run setup
    print(f"\n{B}Starting setup wizard...{N}\n")
    if on_path:
        subprocess.run(["memory-hub", "setup"])
    else:
        subprocess.run([sys.executable, "-m", "memory_hub.cli", "setup"])

def main():
    print(f"{C}{B}🧠 MemoryHub Installer{N}\n")

    # 1. Check Python
    v = f"{sys.version_info.major}.{sys.version_info.minor}"
    if sys.version_info < (3, 9):
        print(f"❌ Python 3.9+ required (you have {v})")
        sys.exit(1)
    print(f"   ✅ Python {v}")

    # 2. Try pip install first (preferred — verified package)
    print(f"   📦 Installing from PyPI...")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "memory-hub", "--quiet"],
                       capture_output=True, text=True)
    if r.returncode == 0:
        print(f"   ✅ Installed from PyPI")
        _post_install()
        return

    # 3. Fallback: clone from GitHub
    print(f"   {Y}PyPI install failed, falling back to GitHub clone{N}")
    tmp = Path(tempfile.mkdtemp(prefix="memoryhub_"))
    print(f"   📥 Cloning {REPO_URL}...")
    r = subprocess.run(["git", "clone", "--depth", "1", REPO_URL, str(tmp)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"   ❌ Clone failed: {r.stderr[:200]}")
        sys.exit(1)
    # Verify we cloned the right repo
    r = subprocess.run(["git", "-C", str(tmp), "remote", "get-url", "origin"],
                       capture_output=True, text=True)
    if "bryan-cmf/memory-hub" not in r.stdout.lower():
        print(f"   ❌ Repository URL mismatch: {r.stdout.strip()}")
        shutil.rmtree(tmp, ignore_errors=True)
        sys.exit(1)
    print(f"   ✅ Cloned to {tmp}")

    # 3. pip install (handle externally-managed env)
    print(f"   📦 Installing...")
    install_cmds = [
        [sys.executable, "-m", "pip", "install", str(tmp), "--user", "--quiet"],
        [sys.executable, "-m", "pip", "install", str(tmp), "--break-system-packages", "--quiet"],
    ]
    installed = False
    for cmd in install_cmds:
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            installed = True
            break
        if "externally-managed" not in r.stderr:
            print(f"   ❌ Install failed: {r.stderr[:300]}")
            sys.exit(1)
    if not installed:
        print(f"   ❌ All install methods failed. Try manually:")
        print(f"      {sys.executable} -m pip install --user {tmp}")
        sys.exit(1)
    print(f"   ✅ Installed")

    # 4. Cleanup
    shutil.rmtree(tmp, ignore_errors=True)

    # 5. Post-install
    _post_install()

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
