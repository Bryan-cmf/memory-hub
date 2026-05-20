#!/usr/bin/env python3
"""MemoryHub Hub Server v2.0 — preserves original capture_daemon dashboard style"""
import json,os,sys,time; from pathlib import Path; from datetime import datetime,timezone
from http.server import HTTPServer,BaseHTTPRequestHandler; from urllib.parse import urlparse,parse_qs,unquote

HUB_PORT=int(os.getenv("HUB_PORT","3120")); MH_DIR=Path(os.path.expanduser("~/.memory-hub"))
STATE_FILE=MH_DIR/"hub_state.json"; HOOK_LOG_DIR=MH_DIR/"hooks"

STATE={"started_at":datetime.now(timezone.utc).isoformat(),"total_messages":0,"platforms":{},"recent":[],"errors":[]}

def process_hook(platform,message):
    pid=platform or message.get("platform","unknown"); content=str(message.get("content",""))[:500]
    role=message.get("role","unknown"); STATE["total_messages"]+=1
    if pid not in STATE["platforms"]: STATE["platforms"][pid]={"name":pid,"captured":0,"last_preview":""}
    STATE["platforms"][pid]["captured"]+=1; STATE["platforms"][pid]["last_preview"]=content[:80]
    STATE["recent"].append({"platform":pid,"role":role,"content":content[:150],"time":datetime.now().strftime("%H:%M:%S")})
    if len(STATE["recent"])>200: STATE["recent"]=STATE["recent"][-200:]
    d=HOOK_LOG_DIR/pid/datetime.now().strftime("%Y/%m"); d.mkdir(parents=True,exist_ok=True)
    with open(d/f"{datetime.now().strftime('%d')}.jsonl","a",encoding="utf-8") as f:
        f.write(json.dumps({"platform":pid,"role":role,"content":content,"timestamp":datetime.now(timezone.utc).isoformat()},ensure_ascii=False)+"\n")

def unified_search(query,limit=10):
    r=[]
    for dd in [HOOK_LOG_DIR, MH_DIR/"memories"]:
        if not dd.exists(): continue
        for f in sorted(dd.rglob("*.json*"),key=lambda x:x.stat().st_mtime,reverse=True)[:100]:
            try:
                data=json.loads(f.read_text(encoding="utf-8"))
                c=data.get("content","")
                if query.lower() in c.lower():
                    r.append({"source":"file","content":c[:200],"tags":data.get("tags",[])})
                    if len(r)>=limit: break
            except: continue
    return {"query":query,"total":len(r),"results":r[:limit]}

DASH="""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>MemoryHub</title>
<style>*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,'Noto Sans TC',sans-serif;background:#0d1117;color:#c9d1d9;padding:16px}
h1{font-size:1.2em;color:#58a6ff;margin-bottom:2px}.sub{color:#8b949e;font-size:.8em;margin-bottom:10px}
.stats{display:flex;gap:16px;font-size:.8em;color:#8b949e;margin-bottom:10px}.stats b{color:#58a6ff}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:8px;margin-bottom:10px}
.card{background:#161b22;border:1px solid#30363d;border-radius:6px;padding:12px}
.card h2{font-size:1em;margin-bottom:4px}.card .n{font-size:2em;font-weight:bold;color:#58a6ff}
.card .pre{color:#8b949e;font-size:.8em;margin-top:4px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.flow{background:#161b22;border:1px solid#30363d;border-radius:6px;padding:12px;max-height:55vh;overflow-y:auto}
.msg{padding:4px 0;border-bottom:1px solid#21262d;font-size:.85em}
.msg .pf{color:#58a6ff;font-weight:bold}.msg .u{color:#7ee787}.msg .a{color:#f0883e}
.msg .t{color:#484f58;font-size:.75em;margin-left:6px}
#sq{background:#161b22;border:1px solid#30363d;color:#c9d1d9;padding:2px 8px;border-radius:3px;width:140px}
</style></head><body>
<h1>🧠 MemoryHub Hub Server v2.0</h1>
<div class="sub">POST /hook + GET /api/search | localhost:3120</div>
<div class="stats">Total: <b id="tb">0</b> | Platforms: <b id="pc">0</b> | <input id="sq" placeholder="Search..." onkeyup="if(event.key=='Enter')doSearch()"></div>
<div class="cards" id="cards">LOADING...</div>
<div class="flow" id="flow">LOADING...</div>
<script>
async function r(){try{let s=await(await fetch('/api/state')).json()
document.getElementById('cards').innerHTML=Object.entries(s.platforms||{}).map(([k,p])=>
`<div class="card"><h2>${p.name||k}</h2><div class="n">${p.captured||0}</div>
<div class="pre">${p.last_preview||'Waiting...'}</div></div>`).join('')
document.getElementById('flow').innerHTML=(s.recent||[]).slice(-30).reverse().map(m=>
`<div class="msg"><span class="pf">${m.platform||''}</span> <span class="${(m.role||'')=='user'?'u':'a'}">${(m.role||'')=='user'?'👉':'🤖'}</span> ${(m.content||'').substring(0,100)} <span class="t">${(m.time||'').slice(11,19)}</span></div>`).join('')
document.getElementById('tb').textContent=s.total_messages||0
document.getElementById('pc').textContent=Object.keys(s.platforms||{}).length}catch(e){}setTimeout(r,2000)}
async function doSearch(){let q=document.getElementById('sq').value
let s=await(await fetch('/api/search?q='+encodeURIComponent(q))).json()
document.getElementById('flow').innerHTML='<h2>Search: '+q+' ('+s.total+' results)</h2>'+(s.results||[]).slice(0,15).map(r=>
`<div class="msg"><span class="pf">[${r.source}]</span> ${(r.content||'').substring(0,120)}</div>`).join('')}
r()
</script></body></html>"""

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        p=urlparse(self.path).path
        if p=="/": self._h(DASH)
        elif p=="/api/state": self._j(STATE)
        elif p=="/api/search":
            qs=parse_qs(urlparse(self.path).query); q=unquote(qs.get("q",[""])[0])
            self._j(unified_search(q,int(qs.get("limit",["10"])[0])))
        elif p=="/health": self._j({"status":"ok","version":"2.0.0"})
        else: self.send_response(404);self.end_headers()
    def do_POST(self):
        if self.path=="/hook":
            try:
                body=json.loads(self.rfile.read(int(self.headers.get("Content-Length",0))))
                process_hook(body.get("platform","unknown"),body.get("message",body))
                self._j({"status":"captured"})
            except Exception as e: self._j({"error":str(e)},400)
        else: self.send_response(404);self.end_headers()
    def _h(self,html): self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.end_headers();self.wfile.write(html.encode())
    def _j(self,data,code=200): self.send_response(code);self.send_header("Content-Type","application/json");self.send_header("Access-Control-Allow-Origin","*");self.end_headers();self.wfile.write(json.dumps(data,ensure_ascii=False,default=str).encode())
    def log_message(self,*a):pass

def run():
    print("🧠 MemoryHub Hub v2.0",file=sys.stderr)
    print(f"📡 http://localhost:{HUB_PORT}",file=sys.stderr)
    if STATE_FILE.exists():
        try: saved=json.loads(STATE_FILE.read_text(encoding="utf-8"));STATE["total_messages"]=saved.get("total_messages",0);STATE["platforms"]=saved.get("platforms",{})
        except:pass
    srv=HTTPServer(("127.0.0.1",HUB_PORT),H)
    try: srv.serve_forever()
    except KeyboardInterrupt:
        STATE_FILE.write_text(json.dumps(STATE,ensure_ascii=False,default=str,indent=2),encoding="utf-8");srv.shutdown()

if __name__=="__main__": run()
