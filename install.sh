#!/usr/bin/env python3
"""MemoryHub One-Click Installer — curl | python3
Usage:
    curl -fsSL https://raw.githubusercontent.com/Bryan-cmf/memory-hub/main/install.sh | python3
"""

import os, sys, subprocess, tempfile, shutil
from pathlib import Path

REPO_URL = "https://github.com/Bryan-cmf/memory-hub.git"
B = "\033[1m"; G = "\033[32m"; C = "\033[36m"; Y = "\033[33m"; N = "\033[0m"

def main():
    print(f"{C}{B}🧠 MemoryHub Installer{N}\n")

    # 1. Check Python
    v = f"{sys.version_info.major}.{sys.version_info.minor}"
    if sys.version_info < (3, 9):
        print(f"❌ Python 3.9+ required (you have {v})")
        sys.exit(1)
    print(f"   ✅ Python {v}")

    # 2. Clone repo to temp
    tmp = Path(tempfile.mkdtemp(prefix="memoryhub_"))
    print(f"   📥 Cloning {REPO_URL}...")
    r = subprocess.run(["git", "clone", "--depth", "1", REPO_URL, str(tmp)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"   ❌ Clone failed: {r.stderr[:200]}")
        print(f"   {Y}Fallback: download ZIP from https://github.com/Bryan-cmf/memory-hub/archive/refs/heads/main.zip{N}")
        sys.exit(1)
    print(f"   ✅ Cloned to {tmp}")

    # 3. pip install
    print(f"   📦 Installing...")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", str(tmp), "--quiet"],
        capture_output=True, text=True
    )
    if r.returncode != 0:
        print(f"   ❌ Install failed: {r.stderr[:300]}")
        sys.exit(1)
    print(f"   ✅ Installed")

    # 4. Check if memory-hub is on PATH
    try:
        r = subprocess.run(["memory-hub", "--help"], capture_output=True, timeout=5)
        on_path = r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        on_path = False

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

    # 5. Cleanup
    shutil.rmtree(tmp, ignore_errors=True)

    # 6. Run setup
    print(f"\n{B}Starting setup wizard...{N}\n")
    if on_path:
        subprocess.run(["memory-hub", "setup"])
    else:
        subprocess.run([sys.executable, "-m", "memory_hub.cli", "setup"])

if __name__ == "__main__":
    main()
