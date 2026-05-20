#!/usr/bin/env python3
"""MemoryHub Session Scanner - v1.0.3 with B31+B35 fixes"""

import os, sys, json
from pathlib import Path
from datetime import datetime, timezone

try:
    import fcntl; _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False

STATE_FILE = Path(os.path.expanduser("~/.memory-hub/scan_state.json"))
LOCK_FILE = Path(os.path.expanduser("~/.memory-hub/.scan_lock"))
DIRS = [Path(os.path.expanduser("~/.hermes/sessions")),
        Path(os.path.expanduser("~/.openclaw/logs"))]
CM = "[CONTEXT COMPACTION"; DM = "[Duplicate tool output"

def acquire_lock():
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not _HAS_FCNTL:
        if LOCK_FILE.exists():
            try:
                pid = int(LOCK_FILE.read_text().strip())
                os.kill(pid, 0); return False
            except (ValueError, OSError, ProcessLookupError): pass
        LOCK_FILE.write_text(str(os.getpid())); return True
    try:
        global _lf; _lf = open(LOCK_FILE, "w")
        fcntl.flock(_lf, fcntl.LOCK_EX | fcntl.LOCK_NB); return True
    except (IOError, OSError): return False

def load_state():
    if STATE_FILE.exists():
        try: return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError): pass
    return {"sessions": {}, "last_scan_time": None}

def save_state(s):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")

def sc(line):
    v = line.get("content")
    if v is None: return ""
    return v if isinstance(v, str) else str(v)

def is_noise(line):
    c = sc(line)
    if CM in c or DM in c: return True
    if line.get("role") == "assistant" and not c.strip() and line.get("tool_calls"): return True
    return False

def extract_exchanges(lines):
    exs, cu, ap, tc, lts = [], None, [], 0, ""
    for ln in lines:
        if is_noise(ln): continue
        r = ln.get("role"); c = sc(ln).strip()
        ts = ln.get("timestamp", "")
        if ts: lts = ts
        if r == "user":
            if cu and ap:
                exs.append({"user": cu, "assistant": " ".join(ap), "tool_count": tc, "timestamp": lts})
            cu, ap, tc = c, [], 0
        elif r == "assistant" and c: ap.append(c)
        elif r == "tool": tc += 1
    if cu and ap:
        exs.append({"user": cu, "assistant": " ".join(ap), "tool_count": tc, "timestamp": lts})
    return exs

def is_valuable(ex):
    if ex["tool_count"] > 0: return True
    ul, al = len(ex["user"]), len(ex["assistant"])
    if al > 40: return True
    return ul >= 10 and al >= 20

def gs(ex):
    s = f"User: {ex['user'][:200]}\nAssistant: {ex['assistant'][:300]}"
    if ex["tool_count"]: s += f"\nTool calls: {ex['tool_count']}"
    return s

def read_lines(fp, offset):
    try: fsize = fp.stat().st_size
    except OSError: return [], 0, 0, False
    truncated = False
    if fsize < offset: offset = 0; truncated = True
    try:
        with open(fp, encoding="utf-8") as fh:
            fh.seek(offset); raw = fh.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"  WARN {fp.name}: {e}", file=sys.stderr)
        return [], 0, fsize, truncated
    inc = len(raw)
    if not raw.strip(): return [], 0, fsize, truncated
    rls = raw.split("\n")
    start = 1 if offset > 0 and not raw.lstrip().startswith("{") else 0
    lines, bad = [], 0
    for rl in rls[start:]:
        rl = rl.strip()
        if not rl: continue
        try: lines.append(json.loads(rl))
        except json.JSONDecodeError: bad += 1
    if bad > 0 and not lines:
        print(f"  WARN {fp.name}: {bad} malformed lines", file=sys.stderr)
    return lines, inc, fsize, truncated

def sk(d, fn): return f"{d.name}/{fn}"

def scan_sessions(dirs):
    state = load_state(); mems = []
    for d in dirs:
        if not d.exists(): continue
        for f in sorted(d.glob("*.jsonl")):
            key = sk(d, f.name); fs = state["sessions"].get(key, {}); lo = fs.get("last_offset", 0)
            try:
                lines, inc, fsize, truncated = read_lines(f, lo)
                if truncated: lo = 0
                new_off = lo + inc
                if new_off > fsize: new_off = fsize
                if not lines:
                    if new_off != lo:
                        bl = 0 if truncated else fs.get("last_line", 0)
                        state["sessions"][key] = {"last_offset": new_off, "last_line": bl,
                            "last_timestamp": fs.get("last_timestamp", ""), "channel": fs.get("channel", "unknown")}
                    continue
                exs = extract_exchanges(lines)
                entity_info = extract_entities_from_exchanges(lines)
                for ex in exs:
                    if is_valuable(ex):
                        mems.append({"session_file": f.name, "dir": d.name, "channel": fs.get("channel", "unknown"),
                            "timestamp": ex["timestamp"], "user_message": ex["user"][:200],
                            "summary": gs(ex), "tool_count": ex["tool_count"],
                            "entities": entity_info})
                pl = 0 if truncated else fs.get("last_line", 0)
                state["sessions"][key] = {"last_offset": new_off, "last_line": pl + len(lines),
                    "last_timestamp": lines[-1].get("timestamp", ""), "channel": fs.get("channel", "unknown")}
            except Exception as e:
                print(f"  WARN {f.name}: {e}", file=sys.stderr)
    state["last_scan_time"] = datetime.now(timezone.utc).isoformat(); save_state(state)
    return mems

# ── Entity Extraction (1.6-1.7) ──────────────────────

def extract_entities_from_exchanges(lines: list[dict]) -> dict:
    """Extract entities (people, files) from raw JSONL lines."""
    import re
    entities = {"people": set(), "files": set()}
    for ln in lines:
        c = sc(ln)
        # Extract file names from content
        f_matches = re.findall(r'([\w\-]+\.(?:pdf|md|py|json|csv|html|pptx|docx))', c)
        for fm in f_matches:
            entities["files"].add(fm)
        # Extract people patterns
        p_matches = re.findall(r'(?:給|發給|通知|匯報)([\u4e00-\u9fff]{1,4})(?:總|經理)?', c)
        for pm in p_matches:
            entities["people"].add(pm)
    return {"people": list(entities["people"]), "files": list(entities["files"])}

# Add entity extraction to scan_sessions — append entities to each memory
def scan_sessions_with_entities(dirs):
    mems = scan_sessions(dirs)
    # Re-scan raw lines for entities not captured in exchanges
    # (entity extraction happens inline in scan_sessions via the lines already read)
    return mems

if __name__ == "__main__":
    if not acquire_lock():
        print("Another scanner running. Exiting."); sys.exit(0)
    print(f"MemoryHub Scanner - {datetime.now().isoformat()}")
    print("=" * 50)
    mems = scan_sessions(DIRS)
    if not mems: print("No new memories")
    else:
        print(f"Found {len(mems)} new:")
        for i, m in enumerate(mems, 1):
            entities = m.get("entities", {})
            extra = ""
            if entities.get("files"):
                extra += f" files={entities['files']}"
            if entities.get("people"):
                extra += f" people={entities['people']}"
            print(f"  {i}. [{m['dir']}/{m['session_file']}] tools={m['tool_count']}{extra} | {m['user_message'][:80]}...")
