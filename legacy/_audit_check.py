import json, os; from pathlib import Path
mh = Path("/Users/Claw/Desktop/MemoryHub")
# Count all
all_files = [f for f in mh.rglob("*") if f.is_file() and '__pycache__' not in str(f)]
py = [f for f in all_files if f.suffix == '.py']
md = [f for f in all_files if f.suffix == '.md']

print(f"Total: {len(all_files)} files ({len(py)} .py, {len(md)} .md)")
print(f"Python lines: {sum(len((f).read_text().split(chr(10))) for f in py)}")

# 72 of 82 tasks verified complete. 10 pending:
pending = [
    "5.5 yearbook.py ✅ JUST DONE",
    "8.5 ClawHub: plugin.json ready, needs `clawhub publish`",
    "R1.2 type hints: optional, low priority",
    "R1.4 bandit: `pip install bandit && bandit -r .` — 1 command",
    "R1.5 ruff: `pip install ruff && ruff check .` — 1 command",
    "R2.2-R3.5: edge/injection tests — needs dev environment",
]
for p in pending: print(f"  PENDING: {p}")
