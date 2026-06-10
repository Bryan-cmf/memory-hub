#!/usr/bin/env python3
"""
MemoryHub Capture Daemon v2.0
Dual-mode auto-capture: MODE A (MCP intercept) + MODE B (filesystem scan)
Zero platform changes — all 4 platforms auto-discovered via filesystem
Dashboard: http://localhost:3872
"""

import json, os, sys, re, time, threading, subprocess, hashlib, logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Initialize logging and constants
from memory_hub import logging_config
from memory_hub.logging_config import get_logger
from memory_hub.constants import HKT
logger = get_logger("daemon")

# Thread pool for sync operations — prevents thread explosion kernel panics
_SYNC_POOL = ThreadPoolExecutor(max_workers=5, thread_name_prefix="mh-sync")

from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

# ═══════════════════════════════════════════════════
# Rate limiting for /hook endpoint
# ═══════════════════════════════════════════════════

_RATE_LIMIT = {}  # {ip: [timestamps]}
_RATE_LIMIT_LOCK = threading.Lock()
RATE_LIMIT_MAX_REQUESTS = 100  # per minute
RATE_LIMIT_WINDOW = 60  # seconds

def _check_rate_limit(client_ip: str) -> bool:
    """Check if client has exceeded rate limit. Returns True if allowed."""
    now = time.time()
    with _RATE_LIMIT_LOCK:
        if client_ip not in _RATE_LIMIT:
            _RATE_LIMIT[client_ip] = []
        # Remove old timestamps
        _RATE_LIMIT[client_ip] = [t for t in _RATE_LIMIT[client_ip] if now - t < RATE_LIMIT_WINDOW]
        # Check limit
        if len(_RATE_LIMIT[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
            return False
        _RATE_LIMIT[client_ip].append(now)
        return True

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
MTIME_STATE_FILE = MH_DIR / "scan_mtimes.json"
# 修復 P2-2: 用有序 set 模擬 LRU 滾動窗口，避免 .clear() 丟失全部去重歷史
# ordered_set() -> (fifo_list, hash_set)
# 當達到上限時只清理最早的 25%，保留 75% 歷史去重
_SEEN_HASHES_FIFO = []  # type: list
_SEEN_HASHES_SET = set()  # type: set
_SEEN_HASHES_MAX = 10000
_SEEN_HASHES_TRIM_RATIO = 0.25  # 清理最早的 25%
STATE_FILE = MH_DIR / "capture_daemon_state.json"
_STATE_LOCK = threading.Lock()
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

# 🔄 Restore previous state on restart
if STATE_FILE.exists():
    try:
        saved = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        STATE["total_captured"] = saved.get("total_captured", 0)
        STATE["mode_a_count"] = saved.get("mode_a_count", 0)
        STATE["mode_b_count"] = saved.get("mode_b_count", 0)
        STATE["recent"] = (saved.get("recent", []) or [])[-100:]
        STATE["errors"] = (saved.get("errors", []) or [])[-50:]
        for pid, pdata in (saved.get("platforms", {}) or {}).items():
            if pid in STATE["platforms"]:
                STATE["platforms"][pid].update({k:v for k,v in pdata.items() if k in STATE["platforms"][pid]})
        logger.info(f"Restored state: {STATE['total_captured']} captures from {len(STATE['platforms'])} platforms")
    except Exception as e:
        logger.warning(f"State restore failed: {e}")

# ═══════════════════════════════════════════════════
# MODE A: MCP intercept (real-time)
# ═══════════════════════════════════════════════════

def mcp_intercept(platform: str, content: str, tags: list = None, metadata: dict = None):
    """Called automatically when any platform's agent uses MemoryHub MCP tools."""
    msg = {"platform":platform,"role":"mcp_intercept","content":str(content)[:5000],
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

def _scan_file(fp: Path, pid: str, last_mtime: float = 0):
    """mtime-based incremental scan. Re-reads full file if mtime changed.
    Safer than offset-based: no data loss on crash, always captures complete file."""
    msgs = []
    try:
        current_mtime = fp.stat().st_mtime
        if current_mtime <= last_mtime:
            return [], last_mtime  # Unchanged
        fsize = fp.stat().st_size
        with open(fp, encoding="utf-8") as f:
            f.seek(0)  # Read full file (mtime-based)
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
                        # Claude Code format — extract text blocks only (skip tool_use/tool_result/thinking)
                        role = msg.get("type", "")
                        inner = msg.get("message", {})
                        blocks = inner.get("content", msg.get("content", []))
                        if isinstance(blocks, list):
                            texts = []
                            for block in blocks:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    texts.append(block.get("text", ""))
                            content = " ".join(t for t in texts if t.strip())
                            if not content:
                                continue  # Skip pure tool/thinking messages
                        elif isinstance(blocks, dict):
                            content = blocks.get("text", "")
                        elif isinstance(blocks, str):
                            content = blocks
                        else:
                            content = ""
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
                            "content":str(content)[:5000],"timestamp":ts,
                            "mode":"B_scan","source_file":str(fp),
                            "channel":channel,"session_id":str(session_id)[:80],
                            "memory_type":mem_type,"importance":importance})
                except json.JSONDecodeError: continue
        return msgs, current_mtime
    except (OSError,UnicodeDecodeError) as e:
        STATE["errors"].append({"file":str(fp),"error":str(e),"time":datetime.now().isoformat()})
        return [], last_mtime

def _is_deepseek_noise(content: str) -> bool:
    """Filter out DeepSeek TUI noise: build output, test results, tool call JSON."""
    c = content.strip()
    if len(c) < 15:
        return True  # too short to be meaningful
    if c.startswith("{") and ("toolCall" in c or "command" in c or "arguments" in c):
        return True  # raw tool call JSON
    if c.startswith("{") and len(c) < 80:
        return True  # tiny JSON (status objects)
    noise_patterns = [
        "BUILD SUCCESSFUL", "BUILD FAILED", "actionable tasks",
        "TEST-", "tests passed", "tests failed", "test results",
        "Executing tasks", "All build files", "> Task",
        "Todo list updated", "(reasoning omitted)",
        "PASSED", "FAILED", "> Configure project",
    ]
    for p in noise_patterns:
        if p in c:
            return True
    if c.replace(" ","").replace("\n","").isdigit():
        return True  # pure numbers (test counts)
    return False


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
                        if _is_deepseek_noise(str(content)): continue
                        channel = "deepseek-tui"
                        mem_type = _classify_memory(role, str(content))
                        importance = _score_importance("deepseek", channel, role, str(content))
                        msgs.append({"platform":pid,"role":str(role),
                            "content":str(content)[:5000],
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
                "content":f"[{title}] {body[:2000]}",
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
    # 🔄 Multi-DB sync: write to all available backends (POOLED — prevents thread explosion)
    try:
        from memory_hub.sync_engine import sync_capture
        _SYNC_POOL.submit(sync_capture, pid, msg)
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
    # "Relevant long-term memory" — remove memory block, keep real message (before or after)
    if 'Relevant long-term memory from agentmemory:' in text:
        before, after = text.split('Relevant long-term memory from agentmemory:', 1)
        # Real message is the non-empty part (can be before or after memory block)
        before = before.strip()
        # Try to extract real message from after (skip bullet/table lines until blank line)
        after_clean = re.sub(r'^[-|#>] .*' + NL + r'?', '', after, flags=re.MULTILINE)
        after_clean = re.sub(r'^\|[^' + NL + r']+\|.*' + NL + r'?', '', after_clean, flags=re.MULTILINE)
        after_clean = after_clean.strip()
        # Use whichever has content, prefer 'before'
        if before:
            text = before
        elif after_clean:
            text = after_clean
        else:
            text = ''
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


# ── P1-2: Memory classification (v2.1 — 2026-06-05 結構化事件升級) ──

DECISION_KEYWORDS = [
    "決定","選擇","採用","改用","確認","批准","同意","決定用","decided","chose",
    "以後都要","永久規則","永久","鐵律","從今以後","從現在開始","永不",
    "老闆指示","老闆要求","老闆說","強制","必須","不准","禁止",
    "R1","R2","R3","R4","R5","R6","R7","R8","R9","R10","R11","R12","R13","R14","R15","R16",
    "P0","P1","P2","policy","rule","永久性","標準化","固化",
]
LESSON_KEYWORDS = [
    "踩坑","教訓","錯誤","修復","bug","問題是","根因","lesson","pitfall","不要",
    "lesson learned","學到","下次要","改進","避免","不再",
    "致命","故障","當機","崩潰","crash","timeout","OOM",
    "忘記","失憶","漏掉","跳過","忽略","沒查到","忘了查",
]
TASK_KEYWORDS = [
    "待辦","todo","task","需要做","跟進","處理","完成","指派",
    "部署","發布","上線","deploy","ship","🔥","⏳","🔄",
    "下一步","接下來","要做","準備做","計劃","安排",
]
FACT_KEYWORDS = [
    "數據","報價","營收","持股","股東","財報","公告","data","revenue","report",
    "市值","PE","PB","ROE","EPS","毛利率","淨利率",
    "HK$","RMB","USD","million","billion","億","萬",
    "CCASS","披露易","hkexnews","年報","PDF","分析報告",
]
# 🆕 結構化事件類型（2026-06-05）
CONFIG_KEYWORDS = [
    "安裝","新增","配置","設定","Gateway","重啟","restart",
    "provider","model","模型","plugin","skill","cron",
    "修改","更新","升級","install","setup","launchctl",
    "binding","路由","route","channel","開通","開設",
    "CNAME","DNS","Tunnel","域名","端口","port",
]
COMPLETION_KEYWORDS = [
    "✅","完成","成功","done","deployed","ok",
    "pass","通過","驗證","verified","confirmed",
    "已發送","已發布","已部署","已安裝","已修復",
]
WARNING_KEYWORDS = [
    "⚠️","注意","小心","風險","warning","caution",
    "deprecated","過時","不再支援","EOL","到期",
    "待解決","pending","blocked","卡住",
]

def _classify_memory(role: str, content: str) -> str:
    """Auto-classify memory into type: decision/lesson/task/fact/config/completion/conversation.
    v2.1: 擴充分類類別 + 結構化事件關鍵詞 (2026-06-05)"""
    lower = content.lower()
    scores = {"decision": 0, "lesson": 0, "task": 0, "fact": 0, "config": 0, "completion": 0}
    for kw in DECISION_KEYWORDS:
        if kw in lower: scores["decision"] += 1
    for kw in LESSON_KEYWORDS:
        if kw in lower: scores["lesson"] += 1
    for kw in TASK_KEYWORDS:
        if kw in lower: scores["task"] += 1
    for kw in FACT_KEYWORDS:
        if kw in lower: scores["fact"] += 1
    for kw in CONFIG_KEYWORDS:
        if kw in lower: scores["config"] += 1
    for kw in COMPLETION_KEYWORDS:
        if kw in lower: scores["completion"] += 1
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    return "conversation"


# ── P1-3: Importance scoring ──────────────────────

def _score_importance(pid: str, channel: str, role: str, content: str) -> int:
    """Score memory importance 0-10 based on signals.
    v2.1: 增強評分邏輯 — 配置變更+2 / 決策關鍵詞+2 / 警告詞+1 (2026-06-05)"""
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
    # 🆕 v2.1: 配置變更信號
    if any(kw in lower for kw in CONFIG_KEYWORDS[:10]): score += 2
    # 🆕 v2.1: 決策信號
    if any(kw in lower for kw in ["決定","以後都要","永久","鐵律","強制","禁止","R1"]): score += 2
    # 🆕 v2.1: 警告/問題信號
    if any(kw in lower for kw in WARNING_KEYWORDS[:5]): score += 1
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
    # Load mtime state (timestamp-based, crash-safe)
    mtimes = {}
    if MTIME_STATE_FILE.exists():
        try: mtimes = json.loads(MTIME_STATE_FILE.read_text(encoding="utf-8"))
        except Exception: mtimes = {}
    discovered = _discover()
    new_total = 0
    for pid, files in discovered.items():
        STATE["platforms"][pid]["files"] = len(files)
        for fp in files[:100]:  # Increased from 50 since mtime check is O(1)
            key = str(fp)
            last_mtime = mtimes.get(key, 0)
            # Select parser based on platform
            if pid == "deepseek":
                msgs, new_val = _scan_deepseek_checkpoint(fp, pid, mtimes.get(key+"_deepseek_count",0))
            elif pid == "claude":
                msgs, new_val = _scan_file(fp, pid, last_mtime)
            elif pid == "hermes":
                msgs, new_val = _scan_file(fp, pid, last_mtime)
            else:
                msgs, new_val = _scan_file(fp, pid, last_mtime)
            if msgs:
                for m in msgs:
                    # Dedup: skip if we've seen this content hash before (for full-file re-reads)
                    chash = hashlib.sha256((str(m.get("content",""))[:200] + str(m.get("timestamp",""))).encode()).hexdigest()[:16]
                    if chash in _SEEN_HASHES_SET:
                        continue
                    # 滾動窗口：只清理最早的 25%，保留 75% 歷史去重
                    if len(_SEEN_HASHES_SET) >= _SEEN_HASHES_MAX:
                        trim_count = int(_SEEN_HASHES_MAX * _SEEN_HASHES_TRIM_RATIO)
                        for _ in range(trim_count):
                            if _SEEN_HASHES_FIFO:
                                old = _SEEN_HASHES_FIFO.pop(0)
                                _SEEN_HASHES_SET.discard(old)
                    _SEEN_HASHES_FIFO.append(chash)
                    _SEEN_HASHES_SET.add(chash)
                    _process(pid, m)
                    _file_save(pid, m)
                STATE["mode_b_count"] += len(msgs)
                new_total += len(msgs)
            # Save mtime (or deepseek turn count)
            if pid == "deepseek":
                mtimes[key+"_deepseek_count"] = new_val
            else:
                mtimes[key] = new_val  # file mtime
    MTIME_STATE_FILE.parent.mkdir(parents=True,exist_ok=True)
    MTIME_STATE_FILE.write_text(json.dumps(mtimes,ensure_ascii=False),encoding="utf-8")
    STATE["scan_cycle"] += 1
    STATE["last_scan"] = datetime.now(HKT).isoformat()
    STATE_FILE.write_text(json.dumps(STATE,ensure_ascii=False,default=str,indent=2),encoding="utf-8")
    # H3.4 checkpoint
    cp = {"timestamp":datetime.now(HKT).isoformat(),"total":STATE["total_captured"]}
    (MH_DIR / ".capture_checkpoint.json").write_text(json.dumps(cp,ensure_ascii=False),encoding="utf-8")
    # P2-1: Auto-generate MEMORY.md index
    generate_memory_index()
    return new_total

def unified_search(query, limit=10, event_type=None):
    """Search across all captured memories with weighted scoring (P1-4).
    v2.1: 支援 event_type 過濾 (decision/lesson/task/fact/config/completion/conversation)"""
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
                                # 🆕 v2.1: event_type filter
                                # 🆕 v2.1: runtime re-classify if stored type doesn't match
                                if event_type:
                                    rt_type = _classify_memory("", content) if len(content) > 10 else mtype
                                    if mtype != event_type and rt_type != event_type:
                                        continue
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
                        except Exception as _e:

                            logger.debug(f'Suppressed: {_e}')

                            continue
                else:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    content = str(data.get("content",""))
                    lower = content.lower()
                    if any(t in lower for t in tokens):
                        channel = str(data.get("channel",""))
                        mtype = str(data.get("memory_type",""))
                        # 🆕 v2.1: runtime re-classify if stored type doesn't match
                        if event_type:
                            rt_type = _classify_memory("", content) if len(content) > 10 else mtype
                            if mtype != event_type and rt_type != event_type:
                                continue
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
        r = subprocess.run(["curl","-sf","http://localhost:6333/collections"], capture_output=True, timeout=3)
        if r.returncode == 0:
            print("   🧠 Qdrant: already running on :6333", file=sys.stderr)
            return
    except Exception as _e:

        logger.debug(f'Suppressed: {_e}')

        pass
    
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
        r2 = subprocess.run(["curl","-sf","http://localhost:6333/collections"], capture_output=True, timeout=5)
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
                except Exception as _e:

                    logger.debug(f'Suppressed: {_e}')

                    pass
            print("   🧠 Qdrant: 4 collections ensured", file=sys.stderr)
    except Exception as e:
        print(f"   ⚠️ Qdrant: {e}", file=sys.stderr)

def auto_start_redis():
    """Auto-start Redis if brew is available."""
    try:
        r = subprocess.run(["redis-cli","ping"], capture_output=True, timeout=3)
        if r.returncode == 0: return  # Already running
    except Exception as _e:

        logger.debug(f'Suppressed: {_e}')

        pass
    
    try:
        if sys.platform == "darwin":
            subprocess.run(["brew","services","start","redis"], capture_output=True, timeout=10)
            print("   ⚡ Redis: started", file=sys.stderr)
    except Exception as _e:

        logger.debug(f'Suppressed: {_e}')

        pass

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
# HTTP Server → extracted to api_server.py
# Delegation: avoids circular import
# ═══════════════════════════════════════════════════

def run_daemon(HUB_PORT=3872):
    '''Start dashboard + capture daemon. Delegates to api_server module.'''
    from memory_hub.api_server import run_daemon as _run
    return _run(HUB_PORT=HUB_PORT)

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
