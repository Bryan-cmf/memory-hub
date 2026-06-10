#!/usr/bin/env python3
"""MemoryHub CLI help + Homebrew formula + Release tools (F3.1-F4.2)"""

# ═══════════════════════════════════════════════════
# CLI Commands (after pip install memory-hub)
# ═══════════════════════════════════════════════════

CLI_HELP = """
🧠 MemoryHub v2.0 — Persistent Memory Enhancement System

Usage:
  memory-hub                Start the capture daemon (port 3872)
  memory-hub --port PORT    Start on a custom port
  memory-hub --once         Single scan, then exit
  
  memory-hub-install        Interactive backend installer
  memory-hub-backup         Interactive backup manager
  
  memory-hub-scan           Run session scanner once
  memory-hub-search "query" Search captured memories
  memory-hub-consolidate    Run memory consolidation

Environment:
  HUB_PORT=3872             Dashboard port
  QDRANT_URL=http://localhost:6333
  EMBEDDING_MODEL=BAAI/bge-m3

More: https://github.com/bryan-cmf/memory-hub
"""

if __name__ == "__main__":
    import sys
    if "--help" in sys.argv or "-h" in sys.argv:
        print(CLI_HELP)
