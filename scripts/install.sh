#!/usr/bin/env python3
"""
MemoryHub Installer
Usage: python3 install.py [--tier 0|1|2|3]
"""

import argparse, subprocess, sys, json, stat
from pathlib import Path

HOME = Path.home()
ROOT = Path(__file__).resolve().parent.parent
SKILL_SRC = ROOT / "skill" / "SKILL.md"
SCANNER_SRC = ROOT / "scanner" / "session_scanner.py"
GUARD_SRC = ROOT / "guard" / "health_check.sh"
CRON_SRC = ROOT / "guard" / "crontab.template"
MH_DIR = HOME / ".memory-hub"
CFG_FILE = MH_DIR / "config.json"

TIER_DESC = {
    "0": "Pure Skill - Zero deps, 1 min, all platforms",
    "1": "Lite - Python + SQLite-vec, 3 min",
    "2": "Full - Python + Qdrant + BGE-m3, 10 min",
    "3": "Cloud - API-based, 2 min",
}

def copy_file(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text())

def run(cmd, **kw):
    return subprocess.run(cmd, **kw)

def pip_install(*packages):
    """Install pip packages with --user fallback."""
    args = [sys.executable, "-m", "pip", "install", "--user"] + list(packages)
    r = run(args, check=False)
    if r.returncode != 0:
        # Retry without --user (for virtualenvs)
        args = [sys.executable, "-m", "pip", "install"] + list(packages)
        run(args, check=False)

def load_existing_config():
    """Load existing config to preserve user customizations on upgrade."""
    if CFG_FILE.exists():
        try:
            return json.loads(CFG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}

def save_config(updates: dict, secure: bool = False):
    """Merge updates into existing config, preserving user settings."""
    existing = load_existing_config()
    existing.update(updates)
    CFG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CFG_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    if secure:
        os.chmod(CFG_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 0o600

# ── Tier 0 ───────────────────────────────────────

def install_tier_0():
    print("Tier 0: Pure Skill mode")
    for t in [
        HOME / ".deepseek/skills/memory-hub/SKILL.md",
        HOME / ".openclaw/skills/memory-hub/SKILL.md",
        HOME / ".claude/skills/memory-hub/SKILL.md",
        HOME / ".hermes/skills/memory-hub/SKILL.md",
    ]:
        if SKILL_SRC.exists():
            copy_file(SKILL_SRC, t)
            print(f"  OK {t}")
        else:
            print(f"  SKIP {t} (source missing)")
    print("Done. Use: /skill memory-hub")

# ── Tier 1 ───────────────────────────────────────

def install_tier_1():
    print("Tier 1: Lite mode (Python + SQLite-vec)")
    try:
        r = run([sys.executable, "--version"], capture_output=True, text=True)
        print(f"  Python {r.stdout.strip()}")
    except Exception:
        print("  ERROR: Python not found"); return

    print("  Installing packages...")
    pip_install("sentence-transformers", "sqlite-vec", "httpx", "apscheduler")

    copy_file(SCANNER_SRC, MH_DIR / "scanner/session_scanner.py")
    copy_file(GUARD_SRC, MH_DIR / "guard/health_check.sh")
    copy_file(CRON_SRC, MH_DIR / "guard/crontab.template")
    print(f"  Scanner + guard -> {MH_DIR}")

    save_config({"tier": "1", "embedding_model": "all-MiniLM-L6-v2"})
    install_tier_0()
    print("\nDone!")
    print("  python3 ~/.memory-hub/scanner/session_scanner.py")
    print("  crontab from ~/.memory-hub/guard/crontab.template")

# ── Tier 2 ───────────────────────────────────────

def install_tier_2():
    print("Tier 2: Full mode (Qdrant + BGE-m3)")
    try:
        run(["docker", "--version"], capture_output=True)
        print("  Docker found")
        r = run(["curl", "-s", "-f", "http://localhost:6333/health"], capture_output=True)
        if r.returncode != 0:
            print("  WARN: Qdrant not running. docker run -d -p 6333:6333 qdrant/qdrant")
    except Exception:
        print("  WARN: Docker not found.")

    print("  Installing packages...")
    pip_install("sentence-transformers", "qdrant-client", "mcp", "httpx", "apscheduler")

    copy_file(SCANNER_SRC, MH_DIR / "scanner/session_scanner.py")
    copy_file(GUARD_SRC, MH_DIR / "guard/health_check.sh")
    copy_file(CRON_SRC, MH_DIR / "guard/crontab.template")
    print(f"  Scanner + guard -> {MH_DIR}")

    save_config({"tier": "2", "embedding_model": "BAAI/bge-m3",
                  "qdrant_url": "http://localhost:6333"})
    install_tier_0()
    print("\nDone! python3 ~/.memory-hub/scanner/session_scanner.py")

# ── Tier 3 ───────────────────────────────────────

def install_tier_3():
    print("Tier 3: Cloud mode")
    provider = input("  Provider (openai/deepseek) [openai]: ").strip() or "openai"
    api_key = input("  API Key: ").strip()
    if not api_key:
        print("  ERROR: API Key required"); return

    save_config({"tier": "3", "cloud_provider": provider,
                  "cloud_api_key": api_key}, secure=True)
    print("  Config saved (permissions: 600)")
    install_tier_0()
    print("Done. WARNING: Data leaves your machine.")

# ── Main ─────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="MemoryHub Installer")
    p.add_argument("--tier", choices=["0","1","2","3"], default="0")
    args = p.parse_args()
    print("MemoryHub Installer")
    print("=" * 50)
    print(f"  Tier {args.tier} - {TIER_DESC[args.tier]}\n")
    {"0": install_tier_0, "1": install_tier_1,
     "2": install_tier_2, "3": install_tier_3}[args.tier]()

if __name__ == "__main__":
    main()
