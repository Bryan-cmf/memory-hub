"""MemoryHub API Server — Dashboard + REST API.

Extracted from daemon.py per Software Architect review.
Handles HTTP serving, dashboard rendering, and state queries.
Capture logic remains in daemon.py.
"""
import json, os, sys, time, threading, re
from collections import defaultdict
from pathlib import Path
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

# Import from daemon (capture logic stays there)
from memory_hub.daemon import (
    STATE, PLATFORMS, STATE_FILE, CAPTURE_DIR, HOOK_LOG_DIR, MH_DIR, HKT,
    _check_rate_limit, _is_deepseek_noise, _classify_memory,
    _score_importance, _extract_channel, _clean_content,
    _process, _file_save,
    run_scan_cycle, auto_start_qdrant, auto_backup, unified_search,
    _discover
)

# ═══════════════════════════════════════════════════
# Dashboard HTML Template
# ═══════════════════════════════════════════════════

DASH = """<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>MemoryHub v2.0</title>
<style>*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--blue:#58a6ff;--green:#3fb950;--orange:#f0883e;--purple:#bc8cff;--red:#f85149;--text:#c9d1d9;--muted:#8b949e;--accent:#1f6feb}
body{font-family:-apple-system,'Noto Sans TC',monospace;background:var(--bg);color:var(--text);padding:20px;min-height:100vh}
.topbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px}
h1{font-size:1.4em;color:var(--blue)}.sub{color:var(--muted);font-size:.75em}
.statbar{display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap}
.stat{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px 20px;text-align:center;min-width:80px}
.stat .v{font-size:1.8em;font-weight:bold;color:var(--blue)}.stat .v.gr{color:var(--green)}.stat .v.or{color:var(--orange)}.stat .v.pu{color:var(--purple)}
.stat .l{color:var(--muted);font-size:.7em;margin-top:4px}
.search{display:flex;gap:8px;margin-bottom:16px}
#sq{flex:1;background:var(--card);border:1px solid var(--border);border-radius:6px;padding:8px 12px;color:var(--text);font-size:.85em}
button{background:var(--accent);border:none;border-radius:6px;padding:8px 16px;color:#fff;font-size:.85em;cursor:pointer}
.main{display:flex;flex-direction:column;gap:12px}
.panel{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:16px}
.panel h2{font-size:1em;color:var(--blue);margin-bottom:8px;display:flex;align-items:center;gap:8px}
.badge{background:var(--accent);color:#fff;font-size:.7em;padding:2px 8px;border-radius:10px;font-weight:normal}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px}
.pcard{background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:10px}
.ph{display:flex;align-items:center;gap:6px;margin-bottom:4px}
.pi{font-size:1.2em}.pn{font-weight:bold;font-size:.85em}.ps{color:var(--muted);font-size:.7em;margin-left:auto}
.pv{font-size:2em;font-weight:bold;color:var(--blue);margin:4px 0}
.pp{color:var(--muted);font-size:.75em;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.pb{height:3px;background:var(--border);border-radius:2px;margin-top:4px}
.pf{height:100%;border-radius:2px;transition:width .5s}
.flow{max-height:40vh;overflow-y:auto}.msg{padding:4px 0;border-bottom:1px solid var(--border);font-size:.8em;display:flex;align-items:center;gap:6px}
.mp{color:var(--blue);font-weight:bold;min-width:50px}.mr{font-size:.8em}.mc{color:var(--text);flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.mt{color:var(--muted);font-size:.7em;min-width:55px}.mr.u{color:var(--green)}.mr.a{color:var(--orange)}.mr.s{color:var(--purple)}
.empty{color:var(--muted);font-size:.85em;padding:20px;text-align:center}
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
<div class="search"><input id="sq" placeholder="Search all captured memories..." onkeydown="if(event.key=='Enter')doSearch()"><select id="chFilter" onchange="applyFilter()" style="background:var(--card);border:1px solid var(--border);border-radius:6px;padding:8px;color:var(--text);font-size:.85em"><option value="all">All Channels</option></select><button onclick="doSearch()">Search</button><button onclick="fetch('/api/clear-feed',{method:'POST'}).then(()=>r())" style="background:var(--card);border:1px solid var(--border);border-radius:6px;padding:8px 12px;color:var(--orange);font-size:.85em;cursor:pointer">Clear Feed</button></div>
<div class="main">
<div class="panel"><h2>📡 Platform Status <span class="badge" id="scanInfo">-</span></h2><div class="cards" id="cards">LOADING...</div></div>
<div class="panel"><h2>📊 Data Distribution <span class="badge" id="distTotal">0</span></h2><div class="cards" id="distribution" style="grid-template-columns:repeat(4,1fr)">LOADING...</div></div>
<div class="panel"><h2>🗄️ Collections <span class="badge" id="collTotal">0</span></h2><div class="cards" id="collections">LOADING...</div></div>
<div class="panel"><h2>🗃️ 5 Backends <span class="badge" id="beTotal">0</span></h2><div class="cards" id="backends">LOADING...</div></div>
<div class="panel" style="margin-bottom:12px"><h2>💬 Live Feed <span class="badge" id="feedCount">0</span></h2>
<div class="flow" id="flow">LOADING...</div></div>
<div class="panel"><h2 id="searchTitle" style="display:none">🔍 Search Results</h2><div id="searchResults"></div></div>
</div>
<script>
function esc(s){if(s==null)return"";var d=document.createElement("div");d.textContent=String(s);return d.innerHTML}
function fmt(n){if(n>=1e6)return(n/1e6).toFixed(1)+'M';if(n>=1e3)return(n/1e3).toFixed(1)+'K';return String(n)}
var channels={};
async function r(){try{let s=await(await fetch('/api/state')).json()
document.getElementById('tb').textContent=s.total_captured||0
document.getElementById('ma').textContent=s.mode_a_count||0
document.getElementById('mb').textContent=s.mode_b_count||0
document.getElementById('sc').textContent=s.scan_cycle||0
let up=0;if(s.started_at){up=Math.round((Date.now()-new Date(s.started_at).getTime())/3600000)}
document.getElementById('up').textContent=up+'h'
let cards='';let totalPts=0
Object.entries(s.platforms||{}).forEach(([k,p])=>{
let pts=p.points||0;totalPts+=pts;let pct=Math.min(100,pts>0?Math.round((p.captured||0)/Math.max(pts,1)*100):0)
cards+=`<div class="pcard"><div class="ph"><span class="pi">${esc(p.icon||'')}</span><span class="pn">${esc(p.name)}</span><span class="ps">${esc(p.files)} files · ${esc(pts)} pts</span></div><div class="pv">${p.captured||0}</div><div class="pp">${esc(p.last_preview||'Waiting...')}</div><div class="pb"><div class="pf" style="width:${pct}%;background:${pct>50?'var(--green)':pct>20?'var(--orange)':'var(--border)'}"></div></div></div>`
})
document.getElementById('cards').innerHTML=cards||'No data'
document.getElementById('qt').textContent=fmt(totalPts)
// Feed
let feed=s.recent||[];feed=[...feed].reverse()
document.getElementById('feedCount').textContent=feed.length
document.getElementById('flow').innerHTML=feed.slice(0,50).map(m=>{
let icon='💬',cls='s';if(m.role==='user'){icon='👤';cls='u'}else if(m.role==='agent'){icon='🤖';cls='a'}else if(m.role==='system'){icon='⚙️';cls='s'}
let impStars='';if(m.importance>=8)impStars='⭐';if(m.importance>=6)impStars='✨'
let mtIcon='';if(m.memory_type==='decision')mtIcon='📋';else if(m.memory_type==='lesson')mtIcon='📝';else if(m.memory_type==='task')mtIcon='✅';else if(m.memory_type==='fact')mtIcon='📌';else if(m.memory_type==='config')mtIcon='⚙️';else if(m.memory_type==='completion')mtIcon='🏁'
return`<div class="msg"><span class="mt">${esc((m.time||'').slice(11,19))}</span><span class="mp">${esc(m.platform||'')}</span><span class="mr ${cls}">${icon}</span><span class="mc">${mtIcon}${impStars}${esc((m.content||'').substring(0,100))}</span></div>`}).join('')
// Channels
channels={};(s.recent||[]).forEach(m=>{let ch=m.channel||'unknown';channels[ch]=(channels[ch]||0)+1})
let filter=document.getElementById('chFilter');let sel=filter.value;filter.innerHTML='<option value="all">All Channels</option>'+Object.entries(channels).sort((a,b)=>b[1]-a[1]).slice(0,20).map(([k,v])=>`<option value="${esc(k)}">${esc(k)} (${v})</option>`).join('');filter.value=sel
// Distribution
try{let d=await(await fetch('/api/distribution')).json();let dt=0;let dCards=''
Object.entries(d).forEach(([k,v])=>{dt+=v.total||0
dCards+=`<div class="pcard"><div class="ph"><span class="pn">${esc(v.name||k)}</span><span class="ps">${v.files||0} files</span></div><div class="pv">${fmt(v.total||0)}</div><div class="pp">${v.last_at||'Never'}</div></div>`})
document.getElementById('distTotal').textContent=fmt(dt)
document.getElementById('distribution').innerHTML=dCards||'No data'
}catch(e){}
// Collections
try{let c=await(await fetch('/api/collections')).json();let ct=0;let collCards=''
Object.entries(c).forEach(([name,pts])=>{ct+=pts||0
let label=name.replace(/_mem$/,'').replace(/_/g,' ')
collCards+=`<div class="pcard"><div class="ph"><span class="pn">${esc(label)}</span><span class="ps">${esc(name)}</span></div><div class="pv">${fmt(pts||0)}</div><div class="pp">vector points</div></div>`})
document.getElementById('collTotal').textContent=fmt(ct)
document.getElementById('collections').innerHTML=collCards||'No collections'
}catch(e){document.getElementById('collections').innerHTML='<div class="empty">Qdrant not running</div>'}
// Backends
try{let b=await(await fetch('/api/backends')).json();let bec=0;let beIcons={Qdrant:'🔮',Chroma:'🌈',LanceDB:'🪶','SQLite':'🗃️',FAISS:'🔍'};let beCards=''
Object.entries(b).forEach(([bn,cnt])=>{
let label=bn;let status='online';let ok=cnt>=0;if(!ok)status='offline'
bec+=ok?1:0
beCards+=`<div class="pcard"><div class="ph"><span class="pi">${esc(beIcons[bn.split('/')[0]]||'')}</span><span class="pn">${esc(bn)}</span><span class="ps">${esc(label)}</span></div><div class="pv">${cnt>=0?fmt(cnt):status}</div><div class="pp">${status} ${cnt>=0?'online':'offline'}</div></div>`})
document.getElementById('beTotal').textContent=bec+'/'+Object.keys(b).length
document.getElementById('backends').innerHTML=beCards||'No backends'
}catch(e){}
}catch(e){document.getElementById('cards').innerHTML='Daemon not running'};requestAnimationFrame(()=>setTimeout(r,2000))}
function applyFilter(){r()}
async function doSearch(){let q=document.getElementById('sq').value;document.getElementById('searchTitle').style.display='block'
let res=await(await fetch('/api/search?q='+encodeURIComponent(q)+'&limit=20')).json()
let div=document.getElementById('searchResults')
div.innerHTML=res.total?res.results.map(r=>`<div class="msg"><span class="mp">${esc(r.platform||'')}</span><span class="mc">${esc((r.content||'').substring(0,200))}</span></div>`).join(''):'<div class="empty">No matches found</div>'}
r()
</script></body></html>"""

# ═══════════════════════════════════════════════════
# HTTP Server
# ═══════════════════════════════════════════════════

class DashboardHandler(BaseHTTPRequestHandler):
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
            event_type=qs.get("type",[None])[0]
            results=unified_search(query,limit,event_type=event_type)
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Access-Control-Allow-Origin","*");self.end_headers()
            self.wfile.write(json.dumps(results,ensure_ascii=False,default=str).encode())
        elif p=="/api/messages":
            limit=int(parse_qs(urlparse(self.path).query).get("limit",["100"])[0])
            recent=list(STATE["recent"])[-limit:]
            recent.reverse()
            filtered = [m for m in recent if "deepseek" not in (m.get("platform","") or "").lower()
                        or not _is_deepseek_noise(str(m.get("content","")))]
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Access-Control-Allow-Origin","*");self.end_headers()
            self.wfile.write(json.dumps(filtered,ensure_ascii=False,default=str).encode())
        elif p=="/api/history":
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
                            except Exception: pass
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
                    except Exception: cols[cn]=-1
            except Exception: cols={}
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Access-Control-Allow-Origin","*");self.end_headers()
            self.wfile.write(json.dumps(cols,ensure_ascii=False).encode())
        elif p=="/api/backends":
            be_data=self._backend_stats()
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Access-Control-Allow-Origin","*");self.end_headers()
            self.wfile.write(json.dumps(be_data,ensure_ascii=False).encode())
        elif p=="/api/distribution":
            dist={}
            for pid,cfg in PLATFORMS.items():
                total=0; last_at=None
                d=HOOK_LOG_DIR/pid
                if d.exists():
                    for f in sorted(d.rglob("*.jsonl")):
                        try:
                            lines=[l for l in f.read_text(encoding="utf-8").strip().split("\n") if l]
                            total+=len(lines)
                            if lines: last_at=json.loads(lines[-1]).get("timestamp","")[:16]
                        except Exception: pass
                dist[pid]={"name":cfg["name"],"icon":cfg["icon"],"total":total,"files":STATE["platforms"].get(pid,{}).get("files",0),"last_at":last_at}
            self.send_response(200);self.send_header("Content-Type","application/json")
            self.send_header("Access-Control-Allow-Origin","*");self.end_headers()
            self.wfile.write(json.dumps(dist,ensure_ascii=False,default=str).encode())
        elif p=="/api/channels":
            ch_stats = defaultdict(lambda: defaultdict(int))
            for pid in STATE["platforms"]:
                pf = STATE["platforms"][pid]
                for ch, cnt in pf.get("channels", {}).items():
                    ch_stats[ch][f"{pid}_count"] = cnt
                    ch_stats[ch]["total"] = ch_stats[ch].get("total", 0) + cnt
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
                client_ip = self.client_address[0]
                if not _check_rate_limit(client_ip):
                    self.send_response(429);self.send_header("Content-Type","application/json");self.end_headers()
                    self.wfile.write(json.dumps({"error":"Rate limit exceeded (100 req/min)"}).encode())
                    return
                cl = int(self.headers.get("Content-Length", 0))
                if cl > 1024 * 1024:
                    self.send_response(413);self.send_header("Content-Type","application/json");self.end_headers()
                    self.wfile.write(json.dumps({"error":"Content too large (max 1MB)"}).encode())
                    return
                ct = self.headers.get("Content-Type", "")
                if ct and "json" not in ct.lower():
                    self.send_response(415);self.send_header("Content-Type","application/json");self.end_headers()
                    self.wfile.write(json.dumps({"error":"Content-Type must be application/json"}).encode())
                    return
                body=json.loads(self.rfile.read(cl))
                pid=body.get("platform","unknown")
                content=str(body.get("content",""))
                content = _clean_content(content)
                if not content: content = str(body.get("content",""))
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
        elif p=="/api/clear-feed":
            STATE["recent"] = []
            self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers()
            self.wfile.write(json.dumps({"status":"cleared","count":0}).encode())
        else:
            self.send_response(404);self.end_headers()

    def _backend_stats(self):
        from memory_hub.backends import _get_cached_client
        result = {}
        try:
            from qdrant_client import QdrantClient
            qc = _get_cached_client("qdrant_stats", QdrantClient, url="http://localhost:6333")
            if qc:
                for c in qc.get_collections().collections:
                    info = qc.get_collection(c.name)
                    result[f"Qdrant/{c.name}"] = info.points_count
        except Exception: result["Qdrant"] = -1
        try:
            import chromadb
            ch = _get_cached_client("chroma_stats", chromadb.PersistentClient, path=str(MH_DIR/"chroma"))
            if ch:
                for coll_obj in ch.list_collections():
                    try:
                        coll_name = coll_obj.name if hasattr(coll_obj, 'name') else str(coll_obj)
                        coll = ch.get_collection(coll_name)
                        result[f"Chroma/{coll_name}"] = coll.count()
                    except Exception: pass
        except Exception: result["Chroma"] = -1
        try:
            import lancedb
            db = _get_cached_client("lancedb_stats", lancedb.connect, str(MH_DIR/"lancedb"))
            if db:
                for t in db.table_names():
                    try:
                        tbl = db.open_table(t)
                        result[f"LanceDB/{t}"] = tbl.count_rows()
                    except Exception: pass
        except Exception: result["LanceDB"] = -1
        try:
            import sqlite3
            conn = _get_cached_client("sqlite_stats", sqlite3.connect, str(MH_DIR/"mh_sqlite_vec.db"))
            if conn:
                _ident_re = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]{0,127}$')
                for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                    if not _ident_re.match(name): continue
                    cnt = conn.execute(f"SELECT COUNT(*) FROM \"{name}\"").fetchone()[0]
                    result[f"SQLite/{name}"] = cnt
        except Exception: result["SQLite"] = -1
        try:
            import faiss
            idx_path = str(MH_DIR/"faiss")
            if os.path.exists(idx_path+"/mh.index"):
                idx = faiss.read_index(idx_path+"/mh.index")
                result["FAISS"] = idx.ntotal
        except Exception: result["FAISS"] = -1
        return result

    def log_message(self,*a):pass

# ═══════════════════════════════════════════════════
# Server Entry Point
# ═══════════════════════════════════════════════════

def run_daemon(HUB_PORT=3872):
    print("="*50,file=sys.stderr)
    print("🧠 MemoryHub Capture Daemon v2.0",file=sys.stderr)
    print("="*50,file=sys.stderr)
    srv=ThreadingHTTPServer(("127.0.0.1",HUB_PORT),DashboardHandler)
    threading.Thread(target=srv.serve_forever,daemon=True).start()
    print(f"📡 Dashboard: http://localhost:{HUB_PORT}",file=sys.stderr)
    print("🟢 MODE A: MCP intercept ready",file=sys.stderr)
    print("🟡 MODE B: Filesystem scan every 5 min",file=sys.stderr)
    auto_start_qdrant()
    auto_backup()
    found=_discover()
    for pid,files in found.items():
        cfg=PLATFORMS[pid]
        print(f"   {cfg['icon']} {cfg['name']}: {len(files)} session files -> {cfg['collection']}",file=sys.stderr)
    n=run_scan_cycle()
    print(f"   Initial: {n} messages captured",file=sys.stderr)
    print(f"\n✅ Daemon running. Open http://localhost:{HUB_PORT}\n",file=sys.stderr)
    AUTO_SAVE_EVERY = 1800
    last_save = time.time()
    try:
        while True:
            time.sleep(30)
            now = time.time()
            if now - last_save >= AUTO_SAVE_EVERY:
                STATE_FILE.write_text(json.dumps(STATE,ensure_ascii=False,default=str,indent=2),encoding="utf-8")
                last_save = now
            if int(now) % 300 < 30 and int(now / 300) != getattr(run_daemon, '_lb', 0):
                n=run_scan_cycle()
                if n: print(f"   [{datetime.now().strftime('%H:%M:%S')}] +{n} msgs",file=sys.stderr)
                run_daemon._lb = int(now / 300)
    except KeyboardInterrupt:
        print("\nShutting down...",file=sys.stderr)
        STATE_FILE.write_text(json.dumps(STATE,ensure_ascii=False,default=str,indent=2),encoding="utf-8")
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

