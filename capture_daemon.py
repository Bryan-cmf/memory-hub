#!/usr/bin/env python3
"""
MemoryHub Capture Daemon v2.0
Dual-mode auto-capture: MODE A (MCP intercept) + MODE B (filesystem scan)
Zero platform changes — all 4 platforms auto-discovered via filesystem
Dashboard: http://localhost:3872
"""

import json, os, sys, time, threading, subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

HKT = timezone(timedelta(hours=8))
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

# ═══════════════════════════════════════════════════
# Platform auto-discovery (zero config)
# ═══════════════════════════════════════════════════

PLATFORMS = {
    "openclaw":  {"icon":"🦞","name":"OpenClaw",
                  "paths":["~/.openclaw/agents/"],
                  "patterns":["*/sessions/*.jsonl"],"collection":"openclaw_mem"},
    "hermes":    {"icon":"🪽","name":"Hermes Agent",
                  "paths":["~/.hermes/sessions/"],
                  "patterns":["*.jsonl","*.json"],"collection":"hermes_mem"},
    "deepseek":  {"icon":"🐋","name":"DeepSeek TUI",
                  "paths":["~/.deepseek/sessions/"],
                  "patterns":["*.json"],"collection":"deepseek_mem"},
    "claude":    {"icon":"🦫","name":"Claude Code",
                  "paths":["~/.claude/projects/","~/.claude/sessions/"],
                  "patterns":["*/*.jsonl","*.json"],"collection":"claude_mem"},
}

MH_DIR = Path(os.path.expanduser("~/.memory-hub"))
OFFSETS_FILE = MH_DIR / "capture_offsets.json"
STATE_FILE = MH_DIR / "capture_daemon_state.json"
CAPTURE_DIR = MH_DIR / "captured"
HOOK_LOG_DIR = MH_DIR / "hooks"

# ═══════════════════════════════════════════════════
# Global state (read by dashboard)
# ═══════════════════════════════════════════════════

STATE = {
    "started_at": datetime.now(HKT).isoformat(),
    "total_captured": 0, "mode_a_count": 0, "mode_b_count": 0,
    "scan_cycle": 0, "last_scan": None, "recent": [], "errors": [],
    "platforms": {}
}
for pid, cfg in PLATFORMS.items():
    STATE["platforms"][pid] = {"name":cfg["name"],"icon":cfg["icon"],
        "captured":0,"last_at":None,"last_preview":"","files":0}

# ═══════════════════════════════════════════════════
# MODE A: MCP intercept (real-time)
# ═══════════════════════════════════════════════════

def mcp_intercept(platform: str, content: str, tags: list = None, metadata: dict = None):
    """Called automatically when any platform's agent uses MemoryHub MCP tools."""
    msg = {"platform":platform,"role":"mcp_intercept","content":str(content)[:300],
           "tags":tags or [],"captured_at":datetime.now(HKT).isoformat(),"mode":"A_mcp"}
    _process(platform, msg)
    STATE["mode_a_count"] += 1
    # File layer save (Source of Truth)
    _file_save(platform, msg)
    return {"status":"captured","mode":"A_mcp","platform":platform}

# ═══════════════════════════════════════════════════
# MODE B: Filesystem scanner
# ═══════════════════════════════════════════════════

def _discover():
    discovered = {}
    for pid, cfg in PLATFORMS.items():
        files = []
        for pp in cfg["paths"]:
            base = Path(os.path.expanduser(pp))
            if not base.exists(): continue
            for pat in cfg["patterns"]:
                for f in base.glob(pat):
                    if f.is_file(): files.append(f)
        discovered[pid] = sorted(set(files), key=lambda x: x.stat().st_mtime, reverse=True)
    return discovered

def _scan_file(fp: Path, pid: str, last_offset: int = 0):
    msgs = []
    try:
        fsize = fp.stat().st_size
        if fsize < last_offset: last_offset = 0
        with open(fp, encoding="utf-8") as f:
            f.seek(last_offset)
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    msg = json.loads(line)
                    if not isinstance(msg, dict): continue
                    # Handle OpenClaw format: {type:"message", message:{role:"user", content:[{text:"..."}]}}
                    if msg.get("type") == "message":
                        inner = msg.get("message", {})
                        role = inner.get("role", "")
                        content_list = inner.get("content", [])
                        if isinstance(content_list, list) and content_list:
                            content = content_list[0].get("text", content_list[0].get("content", ""))
                        else:
                            content = inner.get("content", "")
                    elif msg.get("type") in ("user","assistant") and "sessionId" in msg:
                        # Claude Code format
                        role = msg.get("type", "")
                        raw = msg.get("content", msg.get("message", ""))
                        if isinstance(raw, list) and raw:
                            texts = []
                            for block in raw:
                                if isinstance(block, dict):
                                    texts.append(block.get("text", block.get("content", "")))
                                elif isinstance(block, str):
                                    texts.append(block)
                            content = " ".join(texts)
                        elif isinstance(raw, dict):
                            content = raw.get("text", raw.get("content", str(raw)))
                        else:
                            content = str(raw)
                    else:
                        role = msg.get("role", "")
                        content = msg.get("content")
                    if role in ("user","assistant") and content:
                        content = _clean_content(str(content))
                        if not content: continue
                        # Extract channel + session metadata (P0-1, P0-2)
                        channel = _extract_channel(msg, pid, str(content))
                        session_id = msg.get("sessionId", msg.get("session_id", fp.stem))
                        mem_type = _classify_memory(role, str(content))
                        importance = _score_importance(pid, channel, role, str(content))
                        ts = _parse_timestamp(msg.get("timestamp",""))
                        msgs.append({"platform":pid,"role":role,
                            "content":str(content)[:300],"timestamp":ts,
                            "mode":"B_scan","source_file":str(fp),
                            "channel":channel,"session_id":str(session_id)[:80],
                            "memory_type":mem_type,"importance":importance})
                except json.JSONDecodeError: continue
        return msgs, fsize
    except (OSError,UnicodeDecodeError) as e:
        STATE["errors"].append({"file":str(fp),"error":str(e),"time":datetime.now().isoformat()})
        return [], last_offset

def _scan_deepseek_checkpoint(fp: Path, pid: str, last_count: int = 0) -> list:
    """Parse DeepSeek checkpoint JSON. Handles both array and object formats."""
    msgs = []
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        # Try to find turns array
        turns = None
        if isinstance(data, list):
            turns = data
        elif isinstance(data, dict):
            # Look for turns in common keys
            for key in ["turns","messages","entries","threads","history","content"]:
                val = data.get(key)
                if isinstance(val, list) and val and isinstance(val[0], dict):
                    turns = val
                    break
            # If no standard key found, look for any list value
            if turns is None:
                for val in data.values():
                    if isinstance(val, list) and len(val) > 3 and isinstance(val[0], dict):
                        turns = val
                        break
        
        if turns:
            new_turns = turns[last_count:]
            for turn in new_turns:
                if isinstance(turn, dict):
                    role = turn.get("role", turn.get("type", turn.get("author","")))
                    # Handle nested content (DeepSeek format: content is array of blocks)
                    raw_content = turn.get("content", turn.get("text", turn.get("body","")))
                    if isinstance(raw_content, list):
                        # Extract text from content blocks
                        parts = []
                        for block in raw_content:
                            if isinstance(block, dict):
                                t = block.get("text") or block.get("thinking") or block.get("content") or ""
                                if not t and "input" in block:
                                    t = str(block["input"])[:200]
                                parts.append(str(t) if t else "")
                            elif isinstance(block, str):
                                parts.append(block)
                        content = " ".join(parts)
                    else:
                        content = raw_content
                    if role in ("user","assistant") and content:
                        content = _clean_content(str(content))
                        if not content: continue
                        channel = "deepseek-tui"
                        mem_type = _classify_memory(role, str(content))
                        importance = _score_importance("deepseek", channel, role, str(content))
                        msgs.append({"platform":pid,"role":str(role),
                            "content":str(content)[:300],
                            "timestamp":turn.get("timestamp",datetime.now(HKT).isoformat()),
                            "mode":"B_scan","source_file":str(fp),
                            "channel":channel,"session_id":fp.stem,
                            "memory_type":mem_type,"importance":importance})
        return msgs, len(turns) if turns else 0
    except Exception: return [], last_count

def _scan_claude_markdown(fp: Path, pid: str, last_mtime: float = 0) -> list:
    """Parse Claude Code markdown memory files. Incremental via mtime."""
    msgs = []
    try:
        current_mtime = fp.stat().st_mtime
        if current_mtime <= last_mtime:
            return [], last_mtime  # Unchanged
        content = fp.read_text(encoding="utf-8")
        title = fp.stem.replace("-"," ").replace("_"," ")
        body = content[:500]
        if body.strip():
            mem_type = _classify_memory("assistant", body)
            importance = _score_importance(pid, "claude-code", "assistant", body)
            msgs.append({"platform":pid,"role":"assistant",
                "content":f"[{title}] {body[:300]}",
                "timestamp":datetime.fromtimestamp(current_mtime,HKT).isoformat(),
                "mode":"B_scan","source_file":str(fp),
                "channel":"claude-code","session_id":fp.stem,
                "memory_type":mem_type,"importance":importance})
        return msgs, current_mtime
    except Exception: return [], last_mtime

def _process(pid: str, msg: dict):
    STATE["total_captured"] += 1
    pf = STATE["platforms"][pid]
    pf["captured"] += 1
    pf["last_at"] = msg.get("timestamp") or msg.get("captured_at") or ""
    pf["last_preview"] = str(msg.get("content",""))[:80]
    channel = msg.get("channel","unknown")
    if "channels" not in pf: pf["channels"] = {}
    pf["channels"][channel] = pf["channels"].get(channel, 0) + 1
    STATE["recent"].append({
        "platform": PLATFORMS[pid]["icon"]+" "+PLATFORMS[pid]["name"],
        "role": msg["role"], "content": str(msg.get("content",""))[:150],
        "time": (pf["last_at"] or "")[:19],
        "channel": channel,
        "memory_type": msg.get("memory_type","conversation"),
        "importance": msg.get("importance", 5),
        "session_id": msg.get("session_id",""),
    })
    if len(STATE["recent"]) > 200: STATE["recent"] = STATE["recent"][-200:]
    # 🔄 Multi-DB sync: write to all available backends
    try:
        from memory_hub.sync_engine import sync_capture
        threading.Thread(target=sync_capture, args=(pid, msg), daemon=True).start()
    except Exception:
        pass

def _file_save(pid: str, msg: dict):
    d = CAPTURE_DIR / pid / datetime.now().strftime("%Y/%m")
    d.mkdir(parents=True, exist_ok=True)
    day = datetime.now().strftime("%d")
    with open(d / f"{day}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")

def _clean_content(text: str) -> str:
    """Strip metadata blocks, keep only the real user message."""
    import re
    NL = '\n'
    # Remove Conversation info block (multiline JSON)
    text = re.sub(r'Conversation info \(untrusted metadata\):\s*' + NL + r'```json' + NL + r'\{.+?\}' + NL + r'```\s*' + NL + r'?', '', text, flags=re.DOTALL)
    # Remove Sender metadata block
    text = re.sub(r'Sender \(untrusted metadata\):\s*' + NL + r'```json' + NL + r'\{.+?\}' + NL + r'```\s*' + NL + r'?', '', text, flags=re.DOTALL)
    # "Relevant long-term memory" is injected context — real message is AFTER it
    if 'Relevant long-term memory from agentmemory:' in text:
        _, after = text.split('Relevant long-term memory from agentmemory:', 1)
        # Remove memory bullet/table lines, keep real message after the blank line
        parts = after.split(NL + NL, 1)
        if len(parts) > 1:
            text = parts[1]  # Real message is after blank line
        else:
            text = after  # No blank line, take everything after header
    # Remove "System: ..." lines
    text = re.sub(r'^System: \[.+?\].*?' + NL + r'?', '', text, flags=re.MULTILINE)
    # Remove leftover markdown table/header lines
    text = re.sub(r'^(?:\|.*\||[-|]{3,}.*|> .*|#+ .*)' + NL + r'?', '', text, flags=re.MULTILINE)
    # Remove [DS-SESSION-START] noise
    text = re.sub(r'\[DS-SESSION-START\].*?' + NL + r'?', '', text)
    # Remove blank lines at start
    while text.startswith(NL):
        text = text[1:]
    # Collapse multiple blank lines
    while NL + NL + NL in text:
        text = text.replace(NL + NL + NL, NL + NL)
    return text.strip()

def _parse_timestamp(ts_str: str) -> str:
    """Parse timestamp string and return HKT ISO format."""
    if not ts_str:
        return datetime.now(HKT).isoformat()
    try:
        ts_str = str(ts_str).replace('Z', '+00:00')
        if '+' in ts_str or ts_str.endswith('00:00'):
            dt = datetime.fromisoformat(ts_str)
            dt_hkt = dt.astimezone(HKT)
            return dt_hkt.isoformat()
    except Exception:
        pass
    return str(ts_str)

# ── P0-1: Channel extraction ──────────────────────

def _extract_channel(msg: dict, pid: str, content: str) -> str:
    """Extract communication channel from message metadata."""
    cl = content.lower()
    # OpenClaw format: check for chat_id channel routing
    if pid == "openclaw":
        if "chat_id" in cl and ("wechat" in cl or "weixin" in cl or "o9cq80" in cl):
            return "wechat"
        if "chat_id" in cl and "whatsapp" in cl:
            return "whatsapp"
        if "feishu" in cl or "im.feishu" in cl:
            return "feishu"
        # Check inner content for channel markers
        inner = msg.get("message", {})
        content_list = inner.get("content", [])
        if isinstance(content_list, list):
            for block in content_list:
                if isinstance(block, dict):
                    t = block.get("text","")
                    if "wechat" in t.lower() or "weixin" in t.lower():
                        return "wechat"
                    if "whatsapp" in t.lower():
                        return "whatsapp"
        return "feishu-dm"
    elif pid == "hermes":
        return "hermes-agent"
    elif pid == "deepseek":
        return "deepseek-tui"
    elif pid == "claude":
        return "claude-code"
    return "unknown"


# ── P1-2: Memory classification ───────────────────

DECISION_KEYWORDS = ["決定","選擇","採用","改用","確認","批准","同意","決定用","decided","chose"]
LESSON_KEYWORDS = ["踩坑","教訓","錯誤","修復","bug","問題是","根因","lesson","pitfall","不要"]
TASK_KEYWORDS = ["待辦","todo","task","需要做","跟進","處理","完成","指派"]
FACT_KEYWORDS = ["數據","報價","營收","持股","股東","財報","公告","data","revenue","report"]

def _classify_memory(role: str, content: str) -> str:
    """Auto-classify memory into type: decision/lesson/task/fact/conversation."""
    lower = content.lower()
    scores = {"decision": 0, "lesson": 0, "task": 0, "fact": 0}
    for kw in DECISION_KEYWORDS:
        if kw in lower: scores["decision"] += 1
    for kw in LESSON_KEYWORDS:
        if kw in lower: scores["lesson"] += 1
    for kw in TASK_KEYWORDS:
        if kw in lower: scores["task"] += 1
    for kw in FACT_KEYWORDS:
        if kw in lower: scores["fact"] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "conversation"


# ── P1-3: Importance scoring ──────────────────────

def _score_importance(pid: str, channel: str, role: str, content: str) -> int:
    """Score memory importance 0-10 based on signals."""
    score = 5  # Default neutral
    # Platform boost
    if pid == "openclaw": score += 1  # Main workspace
    # Channel boost
    if channel == "feishu-dm": score += 2  # Direct conversation with boss
    elif channel in ("wechat", "whatsapp"): score += 1
    # Role boost
    if role == "user": score += 1  # User messages are directives
    # Content signals
    lower = content.lower()
    if any(kw in lower for kw in ["pdf","報告","report","分析"]): score += 2
    if any(kw in lower for kw in ["urgent","緊急","重要","重要事項"]): score += 2
    if len(content) > 200: score += 1  # Substantial content
    return min(10, max(0, score))


# ── P2-1: MEMORY.md auto-index ────────────────────

MEMORY_INDEX_INTERVAL = 3600  # Generate every hour
_last_index_time = 0

def generate_memory_index():
    """Auto-generate MEMORY.md index from recent captures."""
    global _last_index_time
    now = time.time()
    if now - _last_index_time < MEMORY_INDEX_INTERVAL:
        return
    _last_index_time = now
    index_path = MH_DIR / "MEMORY.md"
    recent = list(STATE["recent"])[-100:]
    if not recent:
        return
    lines = [
        f"# 🧠 MemoryHub Auto-Index",
        f"_Generated: {datetime.now(HKT).strftime('%Y-%m-%d %H:%M')} HKT_",
        f"_Total captures this session: {STATE['total_captured']}_\n",
        "## 📊 Channel Summary\n",
    ]
    # Aggregate channels
    from collections import defaultdict
    channels = defaultdict(lambda: defaultdict(int))
    for m in recent:
        ch = m.get("channel","unknown")
        mt = m.get("memory_type","conversation")
        channels[ch][mt] += 1
    for ch, types in sorted(channels.items()):
        lines.append(f"- **{ch}**: {sum(types.values())} captures")
        for mt, cnt in sorted(types.items()):
            lines.append(f"  - {mt}: {cnt}")
    
    # Top decisions
    decisions = [m for m in recent if m.get("memory_type") == "decision"]
    if decisions:
        lines.append(f"\n## 💡 Recent Decisions\n")
        for m in decisions[-5:]:
            preview = str(m.get("content",""))[:120]
            lines.append(f"- [{m.get('channel','')}] {preview}")
    
    # Top lessons
    lessons = [m for m in recent if m.get("memory_type") == "lesson"]
    if lessons:
        lines.append(f"\n## 📝 Lessons Learned\n")
        for m in lessons[-5:]:
            preview = str(m.get("content",""))[:120]
            lines.append(f"- [{m.get('channel','')}] {preview}")
    
    # High-importance items
    important = [m for m in recent if m.get("importance", 0) >= 7]
    if important:
        lines.append(f"\n## ⭐ High-Importance Memories\n")
        for m in important[-10:]:
            preview = str(m.get("content",""))[:100]
            imp = m.get("importance",5)
            lines.append(f"- ⭐{imp} [{m.get('channel','')}] {preview}")
    
    index_path.write_text("\n".join(lines), encoding="utf-8")


def run_scan_cycle():
    offsets = {}
    if OFFSETS_FILE.exists():
        try: offsets = json.loads(OFFSETS_FILE.read_text(encoding="utf-8"))
        except Exception: pass
    discovered = _discover()
    new_total = 0
    for pid, files in discovered.items():
        STATE["platforms"][pid]["files"] = len(files)
        for fp in files[:50]:
            key = str(fp)
            # Select parser based on platform
            if pid == "deepseek":
                msgs, new_off = _scan_deepseek_checkpoint(fp, pid, offsets.get(key,{}).get("offset",0))
            elif pid == "claude":
                msgs, new_off = _scan_file(fp, pid, offsets.get(key,{}).get("offset",0))
            elif pid == "hermes":
                msgs, new_off = _scan_file(fp, pid, offsets.get(key,{}).get("offset",0))
            else:
                msgs, new_off = _scan_file(fp, pid, offsets.get(key,{}).get("offset",0))
            if msgs:
                for m in msgs:
                    _process(pid, m)
                    _file_save(pid, m)
                STATE["mode_b_count"] += len(msgs)
                new_total += len(msgs)
                offsets[key] = {"offset":new_off,"last":datetime.now().isoformat()}
    OFFSETS_FILE.parent.mkdir(parents=True,exist_ok=True)
    OFFSETS_FILE.write_text(json.dumps(offsets,ensure_ascii=False),encoding="utf-8")
    STATE["scan_cycle"] += 1
    STATE["last_scan"] = datetime.now(HKT).isoformat()
    STATE_FILE.write_text(json.dumps(STATE,ensure_ascii=False,default=str,indent=2),encoding="utf-8")
    # H3.4 checkpoint
    cp = {"timestamp":datetime.now(HKT).isoformat(),"total":STATE["total_captured"]}
    (MH_DIR / ".capture_checkpoint.json").write_text(json.dumps(cp,ensure_ascii=False),encoding="utf-8")
    # P2-1: Auto-generate MEMORY.md index
    generate_memory_index()
    return new_total

def unified_search(query, limit=10):
    """Search across all captured memories with weighted scoring (P1-4)."""
    scored = []
    import re
    tokens = re.findall(r'[\w]+', query.lower())
    if not tokens:
        return {"query":query,"total":0,"results":[]}
    for d in [CAPTURE_DIR, MH_DIR/"memories", HOOK_LOG_DIR]:
        if not d.exists(): continue
        files = []
        for f in d.rglob("*.json*"):
            if f.is_file(): files.append(f)
        for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)[:500]:
            try:
                if f.suffix == '.jsonl':
                    for line in f.read_text(encoding="utf-8").split("\n"):
                        if not line.strip(): continue
                        try:
                            data = json.loads(line)
                            content = str(data.get("content",""))
                            lower = content.lower()
                            if any(t in lower for t in tokens):
                                # Weighted scoring: metadata 2x, body 1x, importance boost
                                channel = str(data.get("channel",""))
                                mtype = str(data.get("memory_type",""))
                                body_hits = sum(1 for t in tokens if t in lower)
                                meta_hits = sum(1 for t in tokens if t in (channel+mtype).lower())
                                imp = int(data.get("importance", 5))
                                score = meta_hits * 2.0 + body_hits * 1.0 + imp * 0.3
                                scored.append((score, {
                                    "source":"capture","content":content[:200],
                                    "platform":data.get("platform",""),
                                    "channel":channel,"memory_type":mtype,
                                    "importance":imp,"tags":data.get("tags",[])
                                }))
                                if len(scored) >= limit * 3: break
                        except: continue
                else:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    content = str(data.get("content",""))
                    lower = content.lower()
                    if any(t in lower for t in tokens):
                        channel = str(data.get("channel",""))
                        mtype = str(data.get("memory_type",""))
                        meta_hits = sum(1 for t in tokens if t in (channel+mtype).lower())
                        scored.append((meta_hits, {"source":"file","content":content[:200],
                            "platform":data.get("platform",""),"channel":channel,
                            "memory_type":mtype,"tags":data.get("tags",[])}))
                if len(scored) >= limit * 5: break
            except Exception: continue
        if len(scored) >= limit * 5: break
    scored.sort(key=lambda x: -x[0])
    return {"query":query,"total":len(scored),"results":[r for _,r in scored[:limit]]}

# ═══════════════════════════════════════════════════
# Auto-start services
# ═══════════════════════════════════════════════════

def auto_start_qdrant():
    """Auto-start Qdrant Docker container if available."""
    try:
        # Check if already running
        r = subprocess.run(["curl","-sf","http://localhost:6333/health"], capture_output=True, timeout=3)
        if r.returncode == 0:
            print("   🧠 Qdrant: already running on :6333", file=sys.stderr)
            return
    except: pass
    
    try:
        # Check Docker available
        r = subprocess.run(["docker","info"], capture_output=True, timeout=5)
        if r.returncode != 0:
            print("   ⚠️ Qdrant: Docker not available, file-only mode", file=sys.stderr)
            return
        
        # Check if container exists
        r = subprocess.run(["docker","ps","-a","--filter","name=mh-qdrant","--format","{{.Status}}"],
                          capture_output=True, text=True, timeout=5)
        status = r.stdout.strip()
        
        if status:
            if "Up" not in status:
                print("   🧠 Qdrant: starting container...", file=sys.stderr)
                subprocess.run(["docker","start","mh-qdrant"], capture_output=True, timeout=30)
        else:
            print("   🧠 Qdrant: creating container...", file=sys.stderr)
            subprocess.run(["docker","run","-d","--name","mh-qdrant","-p","6333:6333","qdrant/qdrant"],
                          capture_output=True, timeout=60)
        
        # Verify
        time.sleep(2)
        r2 = subprocess.run(["curl","-sf","http://localhost:6333/health"], capture_output=True, timeout=5)
        if r2.returncode == 0:
            print("   🧠 Qdrant: running on :6333", file=sys.stderr)
            # Ensure 4 collections
            for col in ["openclaw_mem","hermes_mem","deepseek_mem","claude_mem"]:
                try:
                    import urllib.request
                    data = json.dumps({"vectors":{"size":384,"distance":"Cosine","on_disk":True}}).encode()
                    req = urllib.request.Request(f"http://localhost:6333/collections/{col}", data=data,
                                                method="PUT", headers={"Content-Type":"application/json"})
                    urllib.request.urlopen(req, timeout=5)
                except: pass
            print("   🧠 Qdrant: 4 collections ensured", file=sys.stderr)
    except Exception as e:
        print(f"   ⚠️ Qdrant: {e}", file=sys.stderr)

def auto_start_redis():
    """Auto-start Redis if brew is available."""
    try:
        r = subprocess.run(["redis-cli","ping"], capture_output=True, timeout=3)
        if r.returncode == 0: return  # Already running
    except: pass
    
    try:
        if sys.platform == "darwin":
            subprocess.run(["brew","services","start","redis"], capture_output=True, timeout=10)
            print("   ⚡ Redis: started", file=sys.stderr)
    except: pass

def auto_backup():
    """Run initial hourly backup if never done."""
    state_file = MH_DIR / "backup_state.json"
    if not state_file.exists():
        try:
            backup_script = Path(__file__).parent / "backup_daemon.py"
            if backup_script.exists():
                subprocess.run([sys.executable, str(backup_script), "--tier", "hourly"],
                              capture_output=True, timeout=30)
                print("   🛡️ Backup: initial snapshot created", file=sys.stderr)
        except Exception as e:
            print(f"   ⚠️ Backup: {e}", file=sys.stderr)

# ═══════════════════════════════════════════════════
# Dashboard (localhost:3120)
# ═══════════════════════════════════════════════════

DASH = """<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>MemoryHub v2.0</title>
<style>*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--blue:#58a6ff;--green:#3fb950;--orange:#f0883e;--purple:#bc8cff;--red:#f85149;--text:#c9d1d9;--muted:#8b949e;--accent:#1f6feb}
body{font-family:-apple-system,'Noto Sans TC',monospace;background:var(--bg);color:var(--text);padding:20px;min-height:100vh}
.topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px}
h1{font-size:1.4em;color:var(--blue)}.sub{color:var(--muted);font-size:.75em}
.statbar{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap}
.stat{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 16px;text-align:center;min-width:90px}
.stat .v{font-size:1.4em;font-weight:bold;color:var(--blue)}.stat .l{font-size:.7em;color:var(--muted);margin-top:2px}
.stat .v.gr{color:var(--green)}.stat .v.or{color:var(--orange)}.stat .v.pu{color:var(--purple)}
.main{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
@media(max-width:900px){.main{grid-template-columns:1fr}}
.panel{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px}
.panel h2{font-size:.95em;color:var(--blue);margin-bottom:8px;display:flex;align-items:center;gap:6px}
.panel h2 .badge{font-size:.65em;background:var(--accent);color:#fff;padding:1px 6px;border-radius:10px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px}
.pcard{background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:10px}
.pcard .ph{display:flex;align-items:center;gap:6px;margin-bottom:6px}
.pcard .ph .pi{font-size:1.2em}.pcard .ph .pn{font-weight:bold;font-size:.85em}
.pcard .ph .ps{font-size:.7em;color:var(--muted);margin-left:auto}
.pcard .pv{font-size:1.5em;font-weight:bold;color:var(--blue)}
.pcard .pp{font-size:.7em;color:var(--muted);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pcard .pb{height:3px;background:var(--border);border-radius:2px;margin-top:6px;overflow:hidden}
.pcard .pb .pf{height:100%;border-radius:2px;transition:width 1s}
.chart{width:100%;height:120px;margin-top:6px}
.flow{max-height:45vh;overflow-y:auto;font-size:.8em}
.msg{padding:3px 0;border-bottom:1px solid var(--border);display:flex;gap:8px;align-items:flex-start}
.msg .mt{color:var(--muted);font-size:.65em;min-width:40px;text-align:right}
.msg .mp{font-size:.65em;font-weight:bold;min-width:60px;text-align:right;color:var(--blue)}
.msg .mr{font-size:.65em;min-width:18px}
.msg .mc{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.8em}
.msg .u{color:var(--green)}.msg .a{color:var(--orange)}.msg .m{color:var(--purple)}
.search{display:flex;gap:8px;margin-bottom:12px}
.search input{flex:1;background:var(--card);border:1px solid var(--border);border-radius:6px;padding:8px 12px;color:var(--text);font-size:.85em;outline:none}
.search input:focus{border-color:var(--blue)}
.search button{background:var(--accent);color:#fff;border:none;border-radius:6px;padding:8px 16px;cursor:pointer;font-size:.85em}
.tabs{display:flex;gap:4px;margin-bottom:8px}
.tab{background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:4px 12px;font-size:.75em;cursor:pointer;color:var(--muted)}
.tab.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.empty{color:var(--muted);font-size:.85em;text-align:center;padding:20px}
</style></head><body>
<div class="topbar"><div><h1>🧠 MemoryHub v2.0</h1><div class="sub">MODE A (MCP) + MODE B (Scan) | 4 Platforms | localhost:3872</div></div></div>
<div class="statbar">
<div class="stat"><div class="v" id="tb">0</div><div class="l">Today Captures</div></div>
<div class="stat"><div class="v gr" id="ma">0</div><div class="l">Mode A (MCP)</div></div>
<div class="stat"><div class="v or" id="mb">0</div><div class="l">Mode B (Scan)</div></div>
<div class="stat"><div class="v pu" id="sc">0</div><div class="l">Scan Cycles</div></div>
<div class="stat"><div class="v" id="qt">0</div><div class="l">Qdrant Points</div></div>
<div class="stat"><div class="v" id="up">-</div><div class="l">Uptime</div></div>
</div>
<div class="search"><input id="sq" placeholder="Search all captured memories..." onkeydown="if(event.key=='Enter')doSearch()"><select id="chFilter" onchange="applyFilter()" style="background:var(--card);border:1px solid var(--border);border-radius:6px;padding:8px;color:var(--text);font-size:.85em"><option value="all">All Channels</option></select><button onclick="doSearch()">🔍 Search</button></div>
<div class="main">
<div class="panel"><h2>📡 Platform Status <span class="badge" id="scanInfo">-</span></h2><div class="cards" id="cards">LOADING...</div></div>
<div class="panel"><h2>📊 Capture History <span class="badge" id="chartLabel">24h</span></h2>
<div class="tabs"><div class="tab active" onclick="switchChart('hourly',this)">24h Hourly</div><div class="tab" onclick="switchChart('daily',this)">7d Daily</div></div>
<canvas class="chart" id="chart"></canvas>
</div>
<div class="panel"><h2>🗄️ Collections <span class="badge" id="collTotal">0</span></h2><div class="cards" id="collections">LOADING...</div></div>
</div>
<div class="panel" style="margin-bottom:12px"><h2>💬 Live Feed <span class="badge" id="feedCount">0</span></h2>
<div class="flow" id="flow">LOADING...</div></div>
<div class="panel"><h2 id="searchTitle" style="display:none">🔍 Search Results</h2><div id="searchResults"></div></div>
<script>
let historyData={hourly:{},daily:{}},collSizes={},chartMode='hourly'
function fmt(n){return n>=1000?(n/1000).toFixed(1)+'k':n}
function r(){Promise.all([fetch('/api/state'),fetch('/api/history'),fetch('/api/collections')]).then(async([s,h,c])=>{
let state=await s.json();historyData=await h.json()
try{collSizes=await c.json()}catch(e){collSizes={}}
let cards='',totalQ=0
for(let[k,p]of Object.entries(state.platforms||{})){
let coll=k+'_mem',pts=collSizes[coll]||0;totalQ+=pts
let pct=p.files?Math.min(100,Math.round(p.captured/Math.max(1,p.files)*100)):0
cards+=`<div class="pcard"><div class="ph"><span class="pi">${p.icon||''}</span><span class="pn">${p.name}</span><span class="ps">${p.files} files · ${pts} pts</span></div><div class="pv">${p.captured||0}</div><div class="pp">${p.last_preview||'Waiting...'}</div><div class="pb"><div class="pf" style="width:${pct}%;background:${pct>50?'var(--green)':pct>20?'var(--orange)':'var(--border)'}"></div></div></div>`}
document.getElementById('cards').innerHTML=cards
document.getElementById('tb').textContent=fmt(state.total_captured||0)
document.getElementById('ma').textContent=state.mode_a_count||0
document.getElementById('mb').textContent=state.mode_b_count||0
document.getElementById('sc').textContent=state.scan_cycle||0
document.getElementById('qt').textContent=fmt(totalQ)
document.getElementById('up').textContent=(historyData.uptime_hours||0).toFixed(1)+'h'
document.getElementById('scanInfo').textContent='⏱ '+(state.last_scan||'').slice(11,19)
// Collections panel
let collCards='',collTotalPts=0
Object.entries(collSizes).sort().forEach(([name,pts])=>{
collTotalPts+=pts||0
let label=name.replace('_mem','').replace('_',' ')
collCards+=`<div class="pcard"><div class="ph"><span class="pn">${label}</span><span class="ps">${name}</span></div><div class="pv">${fmt(pts||0)}</div><div class="pp">vector points</div></div>`
})
document.getElementById('collections').innerHTML=collCards
document.getElementById('collTotal').textContent=fmt(collTotalPts)
// Live feed
let msgs=(state.recent||[]).slice(-40).reverse()
document.getElementById('feedCount').textContent=msgs.length
let chFilter=document.getElementById('chFilter').value
document.getElementById('flow').innerHTML=msgs.filter(m=>chFilter=='all'||m.channel==chFilter).map(m=>{
let rc=m.role||'',cls=rc=='user'?'u':rc=='assistant'?'a':'m',icon=rc=='user'?'👉':rc=='assistant'?'🤖':'📌'
let mt=m.memory_type||'',mtIcon=mt=='decision'?'💡':mt=='lesson'?'📝':mt=='task'?'📋':mt=='fact'?'📊':''
let imp=m.importance||0,impStars=imp>=8?'⭐⭐':imp>=6?'⭐':''
return`<div class="msg"><span class="mt">${(m.time||'').slice(11,19)}</span><span class="mp">${m.platform||''}</span><span class="mr ${cls}">${icon}</span><span class="mc">${mtIcon}${impStars}${(m.content||'').substring(0,100)}</span></div>`}).join('')
// Populate channel filter
fetch('/api/channels').then(r=>r.json()).then(channels=>{
let sel=document.getElementById('chFilter'),cur=sel.value
sel.innerHTML='<option value="all">All Channels</option>'
Object.entries(channels).sort((a,b)=>b[1].total-a[1].total).forEach(([ch,stats])=>{
let opt=document.createElement('option');opt.value=ch
opt.textContent=`${ch} (${stats.recent||stats.total||0})`
sel.appendChild(opt)
})
sel.value=cur
}).catch(()=>{})
drawChart()}).catch(()=>{})
setTimeout(r,3000)}
function applyFilter(){r()}
function drawChart(){
let c=document.getElementById('chart'),ctx=c.getContext('2d'),w=c.offsetWidth,h=c.offsetHeight
ctx.clearRect(0,0,w,h)
let data=historyData[chartMode]||{},entries=Object.entries(data).sort()
if(!entries.length){ctx.fillStyle='#8b949e';ctx.font='12px monospace';ctx.fillText('No data yet',10,20);return}
let platforms=['openclaw','hermes','deepseek','claude'],colors={'openclaw':'#58a6ff','hermes':'#bc8cff','deepseek':'#f0883e','claude':'#3fb950'}
let labels=entries.map(e=>e[0].split(' ').pop()||e[0]),maxV=Math.max(1,...entries.map(e=>Object.values(e[1]).reduce((a,b)=>a+b,0)))
let bw=(w-40)/entries.length,barGap=2
entries.forEach((e,i)=>{
let x=30+i*bw,stack=0
platforms.forEach(pf=>{
let v=e[1][pf]||0,h2=(v/maxV)*(h-30)
ctx.fillStyle=colors[pf]||'#888';ctx.fillRect(x,10+stack,h2>1?bw-barGap:bw-barGap,Math.max(2,h2))
stack+=h2;if(h2<=0)stack+=2
})})
// Legend
ctx.font='10px monospace';let lx=5
platforms.forEach(pf=>{ctx.fillStyle=colors[pf];ctx.fillText(pf,5+lx,h-5);lx+=ctx.measureText(pf).width+12})}
function switchChart(mode,el){
chartMode=mode
document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'))
el.classList.add('active')
document.getElementById('chartLabel').textContent=mode=='hourly'?'24h':'7d'
drawChart()}
async function doSearch(){
let q=document.getElementById('sq').value.trim()
if(!q)return
let res=await(await fetch('/api/search?q='+encodeURIComponent(q)+'&limit=30')).json()
let div=document.getElementById('searchResults'),t=document.getElementById('searchTitle')
t.style.display='block';t.textContent='🔍 Results: '+res.total+' matches'
div.innerHTML=res.total?res.results.map(r=>`<div class="msg"><span class="mp">${r.platform||''}</span><span class="mc">${(r.content||'').substring(0,200)}</span></div>`).join(''):'<div class="empty">No matches found</div>'}
r()
</script></body></html>"""

class DH(BaseHTTPRequestHandler):
    def do_GET(self):
        p = urlparse(self.path).path
        if p=="/":
            self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.end_headers()
            self.wfile.write(DASH.encode())
        elif p=="/api/state":
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Access-Control-Allow-Origin","*");self.end_headers()
            self.wfile.write(json.dumps(STATE,ensure_ascii=False,default=str).encode())
        elif p=="/api/search":
            qs=parse_qs(urlparse(self.path).query)
            query=unquote(qs.get("q",[""])[0])
            limit=int(qs.get("limit",["10"])[0])
            results=unified_search(query,limit)
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Access-Control-Allow-Origin","*");self.end_headers()
            self.wfile.write(json.dumps(results,ensure_ascii=False,default=str).encode())
        elif p=="/api/messages":
            limit=int(parse_qs(urlparse(self.path).query).get("limit",["100"])[0])
            recent=list(STATE["recent"])[-limit:]
            recent.reverse()
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Access-Control-Allow-Origin","*");self.end_headers()
            self.wfile.write(json.dumps(recent,ensure_ascii=False,default=str).encode())
        elif p=="/api/history":
            # Historical capture counts by hour (last 24h) and day (last 7d)
            from collections import defaultdict
            hourly = defaultdict(lambda: defaultdict(int))
            daily = defaultdict(lambda: defaultdict(int))
            now = datetime.now(HKT)
            if CAPTURE_DIR.exists():
                for pf_dir in CAPTURE_DIR.iterdir():
                    if not pf_dir.is_dir(): continue
                    pid = pf_dir.name
                    for ym_dir in sorted(pf_dir.iterdir()):
                        if not ym_dir.is_dir(): continue
                        for day_file in ym_dir.glob("*.jsonl"):
                            try:
                                ts = day_file.stat().st_mtime
                                ft = datetime.fromtimestamp(ts, HKT)
                                if (now - ft).total_seconds() <= 86400:
                                    hk = ft.strftime("%m-%d %H:00")
                                    hourly[hk][pid] += 1
                                if (now - ft).days <= 7:
                                    dk = ft.strftime("%m-%d")
                                    daily[dk][pid] += 1
                            except: pass
            for pid in STATE["platforms"]:
                dk = now.strftime("%m-%d")
                if dk not in daily:
                    daily[dk] = {}
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Access-Control-Allow-Origin","*");self.end_headers()
            self.wfile.write(json.dumps({"hourly":dict(hourly),"daily":dict(daily),
                "uptime_hours":round((now-datetime.fromisoformat(STATE["started_at"])).total_seconds()/3600,1)
            },ensure_ascii=False,default=str).encode())
        elif p=="/api/collections":
            try:
                import urllib.request as urlreq
                req=urlreq.Request("http://localhost:6333/collections",method="GET")
                resp=urlreq.urlopen(req,timeout=3)
                data=json.loads(resp.read())
                cols={}
                for c in data.get("result",{}).get("collections",[]):
                    cn=c["name"]
                    try:
                        req2=urlreq.Request(f"http://localhost:6333/collections/{cn}",method="GET")
                        resp2=urlreq.urlopen(req2,timeout=3)
                        d2=json.loads(resp2.read())
                        cols[cn]=d2.get("result",{}).get("points_count",0)
                    except: cols[cn]=-1
            except: cols={}
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Access-Control-Allow-Origin","*");self.end_headers()
            self.wfile.write(json.dumps(cols,ensure_ascii=False).encode())
        elif p=="/api/channels":
            # P0-3: Aggregate channel stats
            from collections import defaultdict
            ch_stats = defaultdict(lambda: defaultdict(int))
            for pid in STATE["platforms"]:
                pf = STATE["platforms"][pid]
                for ch, cnt in pf.get("channels", {}).items():
                    ch_stats[ch][f"{pid}_count"] = cnt
                    ch_stats[ch]["total"] = ch_stats[ch].get("total", 0) + cnt
            # Also from recent for breakdown
            for m in STATE["recent"]:
                ch = m.get("channel","unknown")
                ch_stats[ch]["recent"] = ch_stats[ch].get("recent", 0) + 1
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Access-Control-Allow-Origin","*");self.end_headers()
            self.wfile.write(json.dumps(dict(ch_stats),ensure_ascii=False).encode())
        elif p=="/api/databases":
            try:
                from memory_hub.sync_engine import get_all_stats
                stats = get_all_stats()
            except Exception:
                stats = {"error": "sync engine unavailable"}
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Access-Control-Allow-Origin","*");self.end_headers()
            self.wfile.write(json.dumps(stats,ensure_ascii=False).encode())
        else:
            self.send_response(404);self.end_headers()

    def do_POST(self):
        p = urlparse(self.path).path
        if p=="/hook":
            try:
                body=json.loads(self.rfile.read(int(self.headers.get("Content-Length",0))))
                pid=body.get("platform","unknown")
                content=str(body.get("content",""))[:300]
                content = _clean_content(content)
                if not content: content = str(body.get("content",""))[:300]  # fallback
                role=body.get("role","unknown")
                channel = body.get("channel") or _extract_channel(body, pid, content)
                mem_type = _classify_memory(role, content)
                importance = _score_importance(pid, channel, role, content)
                msg={"platform":pid,"role":role,
                     "content":content,
                     "timestamp":datetime.now(HKT).isoformat(),
                     "channel":channel,"memory_type":mem_type,
                     "importance":importance,"session_id":"mcp-hook"}
                _process(pid,msg)
                _file_save(pid,msg)
                STATE["mode_a_count"] += 1
                self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers()
                self.wfile.write(json.dumps({"status":"captured","channel":channel,
                    "memory_type":mem_type,"importance":importance}).encode())
            except Exception as e:
                self.send_response(400);self.send_header("Content-Type","application/json");self.end_headers()
                self.wfile.write(json.dumps({"error":str(e)}).encode())
        else:
            self.send_response(404);self.end_headers()

    def log_message(self,*a):pass

# ═══════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════

def run_daemon(HUB_PORT=3872):
    print("="*50,file=sys.stderr)
    print("🧠 MemoryHub Capture Daemon v2.0",file=sys.stderr)
    print("="*50,file=sys.stderr)
    srv=HTTPServer(("127.0.0.1",HUB_PORT),DH)
    threading.Thread(target=srv.serve_forever,daemon=True).start()
    print(f"📡 Dashboard: http://localhost:{HUB_PORT}",file=sys.stderr)
    print("🟢 MODE A: MCP intercept ready",file=sys.stderr)
    print("🟡 MODE B: Filesystem scan every 5 min",file=sys.stderr)
    # Auto-start Qdrant + Redis + Backup
    auto_start_qdrant()
    auto_start_redis()
    auto_backup()
    
    found=_discover()
    for pid,files in found.items():
        cfg=PLATFORMS[pid]
        print(f"   {cfg['icon']} {cfg['name']}: {len(files)} session files → {cfg['collection']}",file=sys.stderr)
    n=run_scan_cycle()
    print(f"   Initial: {n} messages captured",file=sys.stderr)
    print(f"\n✅ Daemon running. Open http://localhost:{HUB_PORT}\n",file=sys.stderr)
    try:
        while True:
            time.sleep(300)
            n=run_scan_cycle()
            if n: print(f"   [{datetime.now().strftime('%H:%M:%S')}] +{n} msgs",file=sys.stderr)
    except KeyboardInterrupt:
        print("\nShutting down...",file=sys.stderr)
        srv.shutdown()
        run_scan_cycle()

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description="MemoryHub Capture Daemon")
    p.add_argument("--port",type=int,default=3872)
    p.add_argument("--once",action="store_true",help="Single scan then exit")
    args=p.parse_args()
    if args.once:
        n=run_scan_cycle();print(f"Captured {n} messages")
    else:
        run_daemon(HUB_PORT=args.port)
