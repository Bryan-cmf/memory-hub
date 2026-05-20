#!/usr/bin/env python3
"""MemoryHub CLI — unified command-line interface."""

import argparse
import sys
import os
from pathlib import Path

def cmd_setup(args):
    """Interactive setup wizard."""
    from .installer import run_setup
    run_setup()

def cmd_start(args):
    """Start the capture daemon."""
    port = args.port or int(os.getenv("MEMORYHUB_PORT", "3872"))
    print(f"🧠 Starting MemoryHub daemon on port {port}...")
    from . import daemon
    daemon.run_daemon(HUB_PORT=port)

def cmd_status(args):
    """Show rich system status."""
    from .verify import status_detail
    status_detail()

def cmd_stop(args):
    """Stop the capture daemon."""
    import subprocess
    r = subprocess.run(["pgrep", "-f", "capture_daemon.py"], capture_output=True, text=True)
    if r.stdout.strip():
        for pid in r.stdout.strip().split("\n"):
            try:
                os.kill(int(pid), 15)
                print(f"🛑 Stopped daemon (PID {pid})")
            except Exception:
                pass
    else:
        print("⚠️  No daemon running")

def cmd_verify(args):
    """Run verification checks."""
    from .verify import run_verify
    run_verify()

def cmd_backup(args):
    """Run backup."""
    tier = args.tier or "hourly"
    print(f"🛡️ Running {tier} backup...")
    from . import backup
    backup.run_backup(tier)

def main():
    parser = argparse.ArgumentParser(
        prog="memory-hub",
        description="🧠 MemoryHub — Persistent Memory for AI Agents"
    )
    sub = parser.add_subparsers(dest="command", title="commands")

    p_setup = sub.add_parser("setup", help="Run interactive setup wizard")
    p_setup.set_defaults(func=cmd_setup)

    p_start = sub.add_parser("start", help="Start the capture daemon")
    p_start.add_argument("--port", type=int, help="Dashboard port (default: 3872)")
    p_start.set_defaults(func=cmd_start)

    p_status = sub.add_parser("status", help="Show system status")
    p_status.set_defaults(func=cmd_status)

    p_stop = sub.add_parser("stop", help="Stop the capture daemon")
    p_stop.set_defaults(func=cmd_stop)

    p_verify = sub.add_parser("verify", help="Run health verification")
    p_verify.set_defaults(func=cmd_verify)

    p_backup = sub.add_parser("backup", help="Run backup")
    p_backup.add_argument("--tier", choices=["hourly","daily","weekly"], help="Backup tier")
    p_backup.set_defaults(func=cmd_backup)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
    else:
        args.func(args)

if __name__ == "__main__":
    main()
