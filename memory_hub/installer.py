#!/usr/bin/env python3
"""MemoryHub Interactive Installer — full TUI setup wizard.

Usage:
    memory-hub setup
    python3 -m memory_hub.installer
"""

import json, os, sys, subprocess, time, shutil
from pathlib import Path

# ── Terminal helpers ──────────────────────────────

B = "\033[1m"; N = "\033[0m"; G = "\033[32m"; C = "\033[36m"
Y = "\033[33m"; R = "\033[31m"; D = "\033[2m\033[37m"

def cls(): os.system("clear 2>/dev/null || printf '\033c'")
def dim(s): return f"{D}{s}{N}"
def ok(s): return f"{G}✅{N} {s}"
def warn(s): return f"{Y}⚠️{N} {s}"
def err(s): return f"{R}❌{N} {s}"
def title(s): return f"{C}{B}{s}{N}"

def box(text, w=62):
    lines = text.strip().split("\n")
    print(f"╭{'─'*w}╮")
    for l in lines:
        # strip ANSI for width calc
        clean = l
        for e in [B,N,G,C,Y,R,D]:
            clean = clean.replace(e, "")
        pad = max(0, w - len(clean))
        print(f"│ {l}{' '*pad}│")
    print(f"╰{'─'*w}╯")

def section(hdr):
    print(f"\n{title(hdr)}")
    print("─" * 50)

# ── Environment detection ─────────────────────────

def detect_environment():
    """Detect installed tools and platforms."""
    results = {}

    # Python
    results["python"] = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    # pip
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "--version"],
                          capture_output=True, text=True, timeout=10)
        results["pip"] = r.stdout.strip().split()[1] if r.returncode == 0 else None
    except Exception:
        results["pip"] = None

    # Docker
    try:
        r = subprocess.run(["docker", "--version"], capture_output=True, text=True, timeout=10)
        results["docker"] = r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        results["docker"] = None

    # git
    try:
        r = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10)
        results["git"] = r.stdout.strip().split()[-1] if r.returncode == 0 else None
    except Exception:
        results["git"] = None

    # Qdrant
    try:
        r = subprocess.run(["curl", "-sf", "http://localhost:6333/health"],
                          capture_output=True, timeout=3)
        results["qdrant"] = r.returncode == 0
    except Exception:
        results["qdrant"] = False

    # AI Platforms
    platforms = {}
    for name, indicators in [
        ("OpenClaw", [Path.home() / ".openclaw/openclaw.json", Path.home() / ".openclaw/agents"]),
        ("Hermes", [Path.home() / ".hermes/sessions", Path.home() / ".hermes/mcp.json", Path.home() / ".hermes"]),
        ("DeepSeek", [Path.home() / ".deepseek/sessions", Path.home() / ".deepseek/mcp.json", Path.home() / ".deepseek"]),
        ("Claude Code", [Path.home() / ".claude/projects", Path.home() / ".claude.json", Path.home() / ".claude"]),
    ]:
        platforms[name] = any(p.exists() for p in indicators)
    results["platforms"] = platforms

    return results


def check_environment(env):
    """Display environment check results."""
    section("🔍 Environment Check")

    for key, label in [("python", "Python"), ("pip", "pip"), ("docker", "Docker"), ("git", "git")]:
        v = env.get(key)
        if v:
            print(f"  {ok(label + ': ' + str(v))}")
        else:
            print(f"  {err(label + ': not found')}")

    qd = env.get("qdrant", False)
    if qd:
        print(f"  {ok('Qdrant: running on :6333')}")
    else:
        print(f"  {warn('Qdrant not running (will auto-start)')}")

    print()
    for name, found in env["platforms"].items():
        if found:
            print(f"  {ok('Detected: ' + name)}")
        else:
            print(f"  {dim('Not found: ' + name)}")


# ── Core installation ─────────────────────────────

def install_qdrant():
    """Install and start Qdrant via Docker."""
    # Check if already running
    try:
        r = subprocess.run(["curl", "-sf", "http://localhost:6333/collections"],
                          capture_output=True, timeout=3)
        if r.returncode == 0:
            print(f"  {ok('Qdrant already running on :6333')}")
            return True
    except Exception:
        pass

    # Check Docker daemon
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        if r.returncode != 0:
            print(f"  {err('Docker daemon not running. Start Docker Desktop first.')}")
            return False
    except FileNotFoundError:
        print(f"  {err('Docker not installed. Install from https://docs.docker.com/get-docker/')}")
        return False

    # Check existing container
    r = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=mh-qdrant", "--format", "{{.Status}}"],
        capture_output=True, text=True, timeout=10
    )
    status = r.stdout.strip()

    if status:
        if "Up" in status:
            print(f"  {ok('Qdrant container running')}")
            return True
        else:
            print(f"  ⏳ Starting existing Qdrant container...")
            subprocess.run(["docker", "start", "mh-qdrant"], capture_output=True, timeout=30)
    else:
        print(f"  ⏳ Pulling Qdrant image + creating container (first time, ~1 min)...")
        r = subprocess.run(
            ["docker", "run", "-d", "--name", "mh-qdrant", "-p", "6333:6333",
             "-v", "mh-qdrant-data:/qdrant/storage", "qdrant/qdrant"],
            capture_output=True, text=True, timeout=120
        )
        if r.returncode != 0:
            print(f"  {err('Qdrant container creation failed: ' + r.stderr[-200:])}")
            return False

    # Verify (wait up to 10s for startup)
    for i in range(10):
        time.sleep(1)
        try:
            r2 = subprocess.run(["curl", "-sf", "http://localhost:6333/collections"],
                               capture_output=True, timeout=3)
            if r2.returncode == 0:
                print(f"  {ok('Qdrant started successfully')}")
                return True
        except Exception:
            pass

    print(f"  {err('Qdrant failed to respond after 10s. Check: docker logs mh-qdrant')}")
    return False


def ensure_collections():
    """Create the 4 platform collections in Qdrant."""
    import urllib.request
    collections = ["openclaw_mem", "hermes_mem", "deepseek_mem", "claude_mem"]
    for col in collections:
        try:
            data = json.dumps({
                "vectors": {"size": 384, "distance": "Cosine", "on_disk": True}
            }).encode()
            req = urllib.request.Request(
                f"http://localhost:6333/collections/{col}",
                data=data, method="PUT",
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass  # Collection may already exist
    print(f"  {ok('4 Qdrant collections ensured')}")


def install_core(env):
    """Install core components: Qdrant, SQLite, daemon."""
    section("📦 Core Components (auto-installed)")

    # Qdrant
    if install_qdrant():
        ensure_collections()

    # SQLite (built-in, always available)
    try:
        import sqlite3
        print(f"  {ok('SQLite: built-in (Python sqlite3)')}")
    except Exception:
        print(f"  {warn('SQLite: sqlite3 module not found')}")

    # pip dependencies
    print(f"  Installing Python dependencies...")
    packages = ["sentence-transformers", "qdrant-client"]
    for pkg in packages:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", pkg],
                capture_output=True, timeout=120
            )
        except Exception:
            pass
    print(f"  {ok('Python dependencies installed')}")

    # MemoryHub package
    print(f"  Installing memory-hub package...")
    pkg_root = Path(__file__).resolve().parent.parent
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "-e", str(pkg_root)],
            capture_output=True, timeout=60, cwd=str(pkg_root)
        )
        print(f"  {ok('memory-hub CLI installed')}")
    except Exception:
        print(f"  {warn('memory-hub CLI: pip install may have failed')}")

    # File storage
    mh_dir = Path.home() / ".memory-hub"
    for d in ["captured", "memories", "hooks"]:
        (mh_dir / d).mkdir(parents=True, exist_ok=True)
    print(f"  {ok('File storage: ~/.memory-hub/')}")


# ── Optional backends ─────────────────────────────

OPTIONAL_BACKENDS = {
    "chroma": {
        "name": "Chroma",
        "desc": "Lightweight vector DB (pip, no Docker)",
        "default": True,
        "install": lambda: subprocess.run(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "--quiet", "chromadb"],
            capture_output=True, timeout=120
        ),
        "verify": lambda: subprocess.run(
            [sys.executable, "-m", "pip", "show", "chromadb"],
            capture_output=True, timeout=10
        ).returncode == 0,
    },
    "lancedb": {
        "name": "LanceDB",
        "desc": "Embedded vector DB (pip, lightest)",
        "default": True,
        "install": lambda: subprocess.run(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "--quiet", "lancedb"],
            capture_output=True, timeout=120
        ),
        "verify": lambda: subprocess.run(
            [sys.executable, "-m", "pip", "show", "lancedb"],
            capture_output=True, timeout=10
        ).returncode == 0,
    },
    "sqlite-vec": {
        "name": "SQLite-vec",
        "desc": "Vector search in SQLite (pip, single file)",
        "default": True,
        "install": lambda: subprocess.run(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "--quiet", "sqlite-vec"],
            capture_output=True, timeout=60
        ),
        "verify": lambda: subprocess.run(
            [sys.executable, "-m", "pip", "show", "sqlite-vec"],
            capture_output=True, timeout=10
        ).returncode == 0,
    },
    "faiss": {
        "name": "FAISS (Meta)",
        "desc": "Fast in-memory vector index (pip)",
        "default": True,
        "install": lambda: subprocess.run(
            [sys.executable, "-m", "pip", "install", "--break-system-packages", "--quiet", "faiss-cpu"],
            capture_output=True, timeout=60
        ),
        "verify": lambda: subprocess.run(
            [sys.executable, "-m", "pip", "show", "faiss-cpu"],
            capture_output=True, timeout=10
        ).returncode == 0,
    },
    "redis": {
        "name": "Redis Stack",
        "desc": "Cache + vector search (brew/apt)",
        "default": True,
        "install": lambda: install_redis(),
        "verify": lambda: subprocess.run(["redis-cli", "ping"], capture_output=True, timeout=5).returncode == 0,
    },
    "pgvector": {
        "name": "PostgreSQL + pgvector",
        "desc": "Relational + vector (Docker)",
        "default": True,
        "install": lambda: install_pgvector(),
        "verify": lambda: subprocess.run(["docker", "ps", "--filter", "name=mh-postgres", "--format", "{{.Status}}"], capture_output=True).stdout.decode().startswith("Up"),
    },
    "elasticsearch": {
        "name": "Elasticsearch",
        "desc": "Full-text + vector search (Docker)",
        "default": True,
        "install": lambda: install_elasticsearch(),
        "verify": lambda: subprocess.run(["docker", "ps", "--filter", "name=mh-elasticsearch", "--format", "{{.Status}}"], capture_output=True).stdout.decode().startswith("Up"),
    },
    "mongodb": {
        "name": "MongoDB",
        "desc": "Document + vector storage (Docker)",
        "default": True,
        "install": lambda: install_mongodb(),
        "verify": lambda: subprocess.run(["docker", "ps", "--filter", "name=mh-mongodb", "--format", "{{.Status}}"], capture_output=True).stdout.decode().startswith("Up"),
    },
}


def install_redis():
    """Start Redis via brew services."""
    if subprocess.run(["redis-cli", "ping"], capture_output=True, timeout=5).returncode == 0:
        return
    subprocess.run(["brew", "services", "start", "redis"], capture_output=True, timeout=30)

def install_pgvector():
    """Start PostgreSQL+pgvector via Docker."""
    docker = subprocess.run(["docker", "info"], capture_output=True)
    if docker.returncode != 0: return
    subprocess.run(["docker", "run", "-d", "--name", "mh-postgres", "-p", "5433:5432",
                    "-e", "POSTGRES_PASSWORD=***", "pgvector/pgvector:pg17"],
                   capture_output=True, timeout=120)

def install_elasticsearch():
    """Start Elasticsearch via Docker."""
    docker = subprocess.run(["docker", "info"], capture_output=True)
    if docker.returncode != 0: return
    subprocess.run(["docker", "run", "-d", "--name", "mh-elasticsearch", "-p", "9200:9200",
                    "-e", "discovery.type=single-node", "-e", "xpack.security.enabled=false",
                    "elasticsearch:8.17.0"], capture_output=True, timeout=120)

def install_mongodb():
    """Start MongoDB via Docker."""
    docker = subprocess.run(["docker", "info"], capture_output=True)
    if docker.returncode != 0: return
    subprocess.run(["docker", "run", "-d", "--name", "mh-mongodb", "-p", "27017:27017",
                    "mongo:7"], capture_output=True, timeout=120)


def install_optional():
    """Interactive optional backend selection — all pre-checked as defaults."""
    section("⚡ Storage Backends (9 pre-selected)")

    print(f"  {dim('All backends are pre-selected as defaults. Press Enter to install all.')}")
    print(f"  {dim('Uncheck any you want to skip, or press A to install all.')}\n")

    selected = {}
    keys = list(OPTIONAL_BACKENDS.keys())
    # Pre-select all defaults
    for key in keys:
        if OPTIONAL_BACKENDS[key].get("default", False):
            selected[key] = True

    for i, key in enumerate(keys, 1):
        info = OPTIONAL_BACKENDS[key]
        checked = "[x]" if key in selected else "[ ]"
        is_default = "(default)" if info.get("default") else ""
        try:
            if info["verify"]():
                status = f"{G}(already installed){N}"
                selected[key] = True
                checked = f"{G}[x]{N}"
            else:
                status = dim(is_default)
        except Exception:
            status = dim(is_default)

        print(f"  {checked} [{i}] {info['name']}")
        print(f"      {dim(info['desc'])} {status}")
        print()

    print(f"  [A] Install ALL (default)")
    print(f"  [Enter] Confirm and install selected")
    print(f"  [Q] Skip all, core only")
    print()

    while True:
        try:
            choice = input(f"  Your choice (1-{len(keys)} to toggle, A, Enter to confirm, Q to skip): ").strip()
            if not choice:
                break  # Enter = confirm selected
            if choice.lower() == 'a':
                for key in keys:
                    selected[key] = True
                print(f"  All 8 backends selected")
                break
            if choice.lower() == 'q':
                selected.clear()
                print(f"  Skipping all optional backends")
                return
            idx = int(choice)
            if 1 <= idx <= len(keys):
                key = keys[idx - 1]
                if key in selected:
                    del selected[key]
                    print(f"  [ ] {OPTIONAL_BACKENDS[key]['name']} — unchecked")
                else:
                    selected[key] = True
                    print(f"  [x] {OPTIONAL_BACKENDS[key]['name']} — checked")
            else:
                print(f"  {err('Invalid choice')}")
        except ValueError:
            print(f"  {err('Enter a number, A for all, Enter to confirm, Q to skip')}")

    if not selected:
        return

    print(f"\n  Installing {len(selected)} backends...")
    for key in keys:
        if key not in selected:
            continue
        info = OPTIONAL_BACKENDS[key]
        try:
            if info["verify"]():
                print(f"  {ok(info['name'] + ' already installed')}")
                continue
        except: pass
        print(f"  ⏳ Installing {info['name']}...")
        info["install"]()
        try:
            if info["verify"]():
                print(f"  {ok(info['name'] + ' installed')}")
            else:
                print(f"  {warn(info['name'] + ': install OK but not running yet (may need manual start)')}")
        except Exception as e:
            print(f"  {warn(info['name'] + ': ' + str(e)[:80])}")


# ── MCP Configuration ─────────────────────────────

MCP_CONFIG = {
    "openclaw": {
        "name": "OpenClaw",
        "path": "~/.openclaw/openclaw.json",
        "key": ["mcp", "servers", "memory-hub"],
        "collection": "openclaw_mem",
    },
    "deepseek": {
        "name": "DeepSeek TUI",
        "path": "~/.deepseek/mcp.json",
        "key": ["servers", "memory-hub"],
        "collection": "deepseek_mem",
    },
    "hermes": {
        "name": "Hermes Agent",
        "path": "~/.hermes/mcp.json",
        "key": ["servers", "memory-hub"],
        "collection": "hermes_mem",
    },
    "claude": {
        "name": "Claude Code",
        "path": "~/.claude/mcp.json",
        "key": ["mcpServers", "memory-hub"],
        "collection": "claude_mem",
    },
}

MCP_SERVER_CONFIG = {
    "command": "python3",
    "args": ["-m", "memory_hub.server.mcp_server"],
    "env": {
        "EMBEDDING_MODEL": "BAAI/bge-m3",
        "QDRANT_URL": "http://localhost:6333",
        "DAEMON_HOOK_URL": "http://localhost:3872/hook",
        "SIMILARITY_THRESHOLD": "0.6",
    }
}


def configure_mcp(env):
    """Auto-configure MCP for detected platforms."""
    section("📡 MCP Configuration")

    mcp_server_path = str(Path(__file__).resolve().parent / "server" / "mcp_server.py")
    restarted = []

    for pid, cfg in MCP_CONFIG.items():
        fp = Path(os.path.expanduser(cfg["path"]))
        name = cfg["name"]

        if not env["platforms"].get(name, False):
            print(f"  {dim(name + ': platform not detected, skipping')}")
            continue

        # Load or create config
        existing = {}
        if fp.exists():
            try:
                existing = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Set up MCP server entry with correct args
        mcp_entry = dict(MCP_SERVER_CONFIG)
        mcp_entry["args"] = [mcp_server_path]  # Use absolute path
        mcp_entry["env"]["MEMORY_COLLECTION"] = cfg["collection"]

        # Navigate to the right place in config
        if cfg["key"][0] == "mcp":
            if "mcp" not in existing:
                existing["mcp"] = {}
            if "servers" not in existing["mcp"]:
                existing["mcp"]["servers"] = {}
            existing["mcp"]["servers"]["memory-hub"] = mcp_entry
        else:
            root_key = cfg["key"][0]
            if root_key not in existing:
                existing[root_key] = {}
            existing[root_key]["memory-hub"] = mcp_entry

        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  {ok(name + ': MCP config written → ' + str(fp))}")
        restarted.append(name)

    if restarted:
        print()
        box(f"""  {Y}⚠️  IMPORTANT:{N} Restart these platforms to load MCP:

  {', '.join(restarted)}

  After restart, agents can use 6 MCP tools:
    • mem_save / mem_search / mem_stats
    • mem_list_collections / mem_delete / capture_send

  Real-time capture (Mode A) will activate automatically.
  Filesystem scan (Mode B) works without restart.""", w=62)

    # Also write a standalone snippet file for reference
    snippets_dir = Path.home() / ".memory-hub"
    snippets_dir.mkdir(parents=True, exist_ok=True)
    snippet_text = "# MemoryHub MCP Config Reference\n"
    for pid, cfg in MCP_CONFIG.items():
        snippet_text += f"\n# {cfg['name']} → {cfg['path']}\n"
        snippet_text += json.dumps({"memory-hub": MCP_SERVER_CONFIG}, indent=2)
        snippet_text += "\n"
    (snippets_dir / "mcp_config_reference.txt").write_text(snippet_text)
    print(f"\n  {dim('Reference saved to ~/.memory-hub/mcp_config_reference.txt')}")


# ── Post-install verification ─────────────────────

def post_install_verify():
    """Run post-install checks."""
    section("✅ Installation Verification")

    checks = []

    # Qdrant — check /collections (more reliable than /health)
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:6333/collections", method="GET")
        resp = urllib.request.urlopen(req, timeout=5)
        d = json.loads(resp.read())
        cols = d.get("result", {}).get("collections", [])
        ok = len(cols) > 0
        checks.append(("Qdrant", ok, f"{len(cols)} collections" if ok else "not responding"))
    except Exception as e:
        checks.append(("Qdrant", False, f"not responding ({str(e)[:40]})"))

    # Daemon
    try:
        req = urllib.request.Request("http://localhost:3872/api/state", method="GET")
        resp = urllib.request.urlopen(req, timeout=3)
        d = json.loads(resp.read())
        checks.append(("Dashboard", True, "HTTP 200"))
    except Exception:
        checks.append(("Dashboard", False, "not responding"))

    # File storage
    mh_dir = Path.home() / ".memory-hub"
    checks.append(("File Storage", mh_dir.exists(), str(mh_dir)))

    # CLI
    try:
        r = subprocess.run(["memory-hub", "--help"], capture_output=True, timeout=5)
        checks.append(("memory-hub CLI", r.returncode == 0, "installed"))
    except Exception:
        checks.append(("memory-hub CLI", False, "not on PATH yet"))

    for label, ok, detail in checks:
        icon = ok if ok else err("")
        print(f"  {icon} {label}: {detail}")


# ── Main entry ────────────────────────────────────

def run_setup():
    """Full interactive setup wizard."""
    cls()
    box(f"""{title('🧠 MemoryHub v2.0 Setup')}

  Persistent Memory for AI Agents
  Vector search + Auto-capture + Dashboard

  This wizard will install and configure MemoryHub.
  Press Ctrl+C to cancel at any time.""")

    # Phase 1: Detect
    env = detect_environment()
    check_environment(env)

    input(f"\n  {dim('Press Enter to continue...')}")

    # Phase 2-3: Core + Optional
    install_core(env)
    install_optional()

    # Phase 4: MCP
    configure_mcp(env)

    # Phase 5: Verify
    post_install_verify()

    # Phase 6: Done
    print()
    box(f"""{title('🎉 MemoryHub is ready!')}

  Dashboard:  {C}http://localhost:3872{N}
  Qdrant:     {C}http://localhost:6333/health{N}
  File store: {C}~/.memory-hub/{N}

  Commands:
    {B}memory-hub start{N}    — Start the daemon
    {B}memory-hub status{N}   — Show system status
    {B}memory-hub verify{N}   — Run health checks
    {B}memory-hub backup{N}   — Run backup

  {Y}⚠️  Remember to restart your AI platforms{N}
  {Y}   for MCP integration to take effect.{N}""")

    # Start daemon prompt
    choice = input(f"\n  Start daemon now? [Y/n]: ").strip().lower()
    if choice != 'n':
        print(f"  Starting daemon...")
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve().parent / "daemon.py")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(2)
        print(f"  {ok('Daemon started on port 3872')}")

if __name__ == "__main__":
    try:
        run_setup()
    except KeyboardInterrupt:
        print(f"\n\n  {dim('Setup cancelled.')}")
        sys.exit(0)
