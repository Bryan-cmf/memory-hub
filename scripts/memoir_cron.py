#!/usr/bin/env python3
"""
Memory Value Platform — Cron Memoir Generator
Called by crontab to prepare memoir generation tasks.

Flow:
  1. Run memoir.py --dry-run to prepare prompt
  2. Create a task file in ~/.memory-hub/tasks/
  3. Next heartbeat picks up the task and generates the memoir
"""

import sys
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

HKT = timezone(timedelta(hours=8))
TASKS_DIR = Path.home() / ".memory-hub" / "tasks"
MEMOIR_DIR = Path.home() / ".memory-hub" / "memoirs"
MEMOIR_SCRIPT = Path.home() / "MemoryHub" / "memory_hub" / "memoir.py"


def create_task(mode: str, date_str: str = ""):
    """Create a memoir generation task file."""
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    MEMOIR_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Run --dry-run to prepare prompt
    cmd = [sys.executable, "-m", "memory_hub.memoir", mode, "--dry-run"]
    if date_str:
        cmd.extend(["--date", date_str])

    result = subprocess.run(
        cmd,
        cwd=str(MEMOIR_SCRIPT.parent.parent),
        capture_output=True,
        text=True,
        timeout=60,
    )

    print(result.stdout)
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}")
        return False

    # Step 2: Find the generated prompt file
    if mode == "week":
        prompt_pattern = "weekly/*_prompt.md"
    else:
        prompt_pattern = "monthly/*_prompt.md"

    prompt_files = sorted(MEMOIR_DIR.glob(prompt_pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    if not prompt_files:
        print(f"ERROR: No prompt file found for {mode}")
        return False

    prompt_path = prompt_files[0]

    # Step 3: Create task file
    task = {
        "type": f"memoir_{mode}",
        "mode": mode,
        "prompt_file": str(prompt_path),
        "created_at": datetime.now(HKT).isoformat(),
        "status": "pending",
    }

    task_file = TASKS_DIR / f"memoir_{mode}_{datetime.now(HKT).strftime('%Y%m%d_%H%M%S')}.json"

    import json
    task_file.write_text(json.dumps(task, indent=2, ensure_ascii=False))

    print(f"✅ Task created: {task_file}")
    print(f"📝 Prompt: {prompt_path}")
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["week", "month"])
    parser.add_argument("--date", type=str, default="")
    args = parser.parse_args()
    create_task(args.mode, args.date)
