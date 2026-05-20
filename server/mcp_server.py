#!/usr/bin/env python3
"""MemoryHub MCP Server - 7 tools over JSON-RPC stdio
MODE A real-time capture via hook to daemon (localhost:3872)"""
import json,sys,os,uuid,asyncio,urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

HKT = timezone(timedelta(hours=8))
QDRANT_URL=os.getenv("QDRANT_URL","http://localhost:6333")
MODEL_NAME=os.getenv("EMBEDDING_MODEL","BAAI/bge-m3")
DEFAULT_COL=os.getenv("MEMORY_COLLECTION","openclaw_mem")
DAEMON_HOOK=os.getenv("DAEMON_HOOK_URL","http://localhost:3872/hook")
_em=None;_qc=None

def _notify_daemon(platform: str, content: str, role: str = "mcp_intercept"):
    """Notify capture daemon via /hook endpoint (Mode A)."""
    try:
        channel = f"{platform}-mcp" if platform else "mcp"
        data = json.dumps({"platform":platform,"role":role,
                          "content":str(content)[:300],"channel":channel}).encode()
        req = urllib.request.Request(DAEMON_HOOK, data=data, method="POST",
                                     headers={"Content-Type":"application/json"})
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass  # Daemon may not be running; non-critical

def _get_em():
    global _em
    if _em:return _em
    from sentence_transformers import SentenceTransformer
    d="mps" if sys.platform=="darwin" else "cpu"
    print(f"[MH] Loading {MODEL_NAME} on {d}",file=sys.stderr)
    _em=SentenceTransformer(MODEL_NAME,device=d)
    return _em

def _get_qc():
    global _qc
    if _qc is not None:return _qc
    try:
        from qdrant_client import QdrantClient
        _qc=QdrantClient(url=QDRANT_URL)
        _qc.get_collections()
        print(f"[MH] Qdrant OK",file=sys.stderr)
    except Exception as e:
        print(f"[MH] Qdrant unavailable: {e}",file=sys.stderr)
        _qc=None
    return _qc

def _vec(t):return _get_em().encode(t[:8000],normalize_embeddings=True).tolist()

def _ens_col(cn):
    qc=_get_qc()
    if not qc:return False
    try:
        from qdrant_client.models import Distance,VectorParams
        ex={x.name for x in qc.get_collections().collections}
        if cn not in ex:
            qc.create_collection(cn,vectors_config=VectorParams(size=384,distance=Distance.COSINE,on_disk=True))
        return True
    except Exception:return False

def _fsave(pid,payload):
    d=Path(os.path.expanduser("~/.memory-hub/memories"))
    d.mkdir(parents=True,exist_ok=True)
    (d/f"{pid}.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

def _fsearch(q,tags,lim):
    d=Path(os.path.expanduser("~/.memory-hub/memories"))
    if not d.exists():return[]
    r=[];ql=q.lower()
    for f in sorted(d.glob("*.json"),key=lambda x:x.stat().st_mtime,reverse=True):
        try:
            data=json.loads(f.read_text(encoding="utf-8"))
            c=data.get("content","")
            if ql in c.lower() or any(t in data.get("tags",[]) for t in tags):
                r.append({"rank":len(r)+1,"score":0.5,"content":c[:200],"tags":data.get("tags",[]),"created_at":data.get("created_at",""),"point_id":f.stem})
                if len(r)>=lim:break
        except Exception:continue
    return r

def mem_save(a):
    col=a.get("collection",DEFAULT_COL);cont=a["content"];tags=a.get("tags",[]);meta=a.get("metadata",{})
    pid=str(uuid.uuid5(uuid.NAMESPACE_DNS,cont))
    payload={"content":cont,"tags":tags,"created_at":datetime.now(HKT).isoformat(),**meta}
    vs=False;qc=_get_qc()
    if qc and _ens_col(col):
        try:
            from qdrant_client.models import PointStruct
            qc.upsert(col,points=[PointStruct(id=pid,vector=_vec(cont),payload=payload)])
            vs=True
        except Exception as e:print(f"[MH] upsert err: {e}",file=sys.stderr)
    _fsave(pid,payload)
    _notify_daemon(DEFAULT_COL.replace("_mem",""), cont, "mcp_save")
    return json.dumps({"status":"saved","collection":col,"point_id":pid,"vector_saved":vs,"file_saved":True,"preview":cont[:100]},ensure_ascii=False)

def mem_search(a):
    col=a.get("collection",DEFAULT_COL);q=a["query"];lim=a.get("limit",10);tags=a.get("tags",[])
    r=[];qc=_get_qc()
    if qc and _ens_col(col):
        try:
            from qdrant_client.models import Filter,FieldCondition,MatchValue
            qf=Filter(must=[FieldCondition(key="tags",match=MatchValue(value=t)) for t in tags]) if tags else None
            hits=qc.search(col,_vec(q),limit=lim,query_filter=qf,score_threshold=float(os.getenv("SIMILARITY_THRESHOLD","0.6")))
            for i,h in enumerate(hits):
                r.append({"rank":i+1,"score":round(h.score,4),"content":h.payload.get("content","")[:200],"tags":h.payload.get("tags",[]),"created_at":h.payload.get("created_at",""),"point_id":h.id})
        except Exception:pass
    if not r:r=_fsearch(q,tags,lim)
    return json.dumps({"query":q,"collection":col,"results":r,"count":len(r),"mode":"vector" if qc and r else "file_fallback"},ensure_ascii=False)

def mem_stats(a):
    col=a.get("collection",DEFAULT_COL);qc=_get_qc();s={"collection":col}
    if qc:
        try:i=qc.get_collection(col);s.update({"mode":"vector","points_count":i.points_count})
        except Exception:s.update({"mode":"vector","error":"collection not found"})
    else:
        d=Path(os.path.expanduser("~/.memory-hub/memories"))
        s.update({"mode":"file","points_count":len(list(d.glob("*.json"))) if d.exists() else 0})
    return json.dumps(s,ensure_ascii=False)

def mem_list():
    qc=_get_qc()
    if qc:
        try:return json.dumps({"collections":[{"name":x.name} for x in qc.get_collections().collections],"mode":"vector"},ensure_ascii=False)
        except Exception:return json.dumps({"error":"qdrant error"},ensure_ascii=False)
    return json.dumps({"mode":"file","collections":[{"name":"file_storage"}]},ensure_ascii=False)

def mem_delete(a):
    col=a.get("collection",DEFAULT_COL);pid=a["point_id"];vd=fd=False;qc=_get_qc()
    if qc:
        try:qc.delete(col,points_selector=[pid]);vd=True
        except Exception:pass
    fp=Path(os.path.expanduser(f"~/.memory-hub/memories/{pid}.json"))
    if fp.exists():fp.unlink();fd=True
    return json.dumps({"status":"deleted","point_id":pid,"vector_deleted":vd,"file_deleted":fd},ensure_ascii=False)

def capture_send(a):
    """Explicitly send conversation capture to daemon (Mode A)."""
    platform = a.get("platform", DEFAULT_COL.replace("_mem",""))
    role = a.get("role", "mcp_intercept")
    content = a.get("content", "")
    _notify_daemon(platform, content, role)
    return json.dumps({"status":"captured","platform":platform,"role":role,"preview":str(content)[:100]},ensure_ascii=False)

TOOLS={n:globals()[n] for n in["mem_save","mem_search","mem_stats","mem_list","mem_delete","capture_send"]}

async def run():
    print("[MH] MCP Server v2.0 ready",file=sys.stderr)
    try:_get_em()
    except Exception:pass
    while True:
        try:
            l=sys.stdin.readline()
            if not l:break
            req=json.loads(l);m=req.get("method","");rid=req.get("id");resp={"jsonrpc":"2.0","id":rid}
            if m=="initialize":resp["result"]={"protocolVersion":"2024-11-05","serverInfo":{"name":"memory-hub","version":"2.0.0"},"capabilities":{"tools":{}}}
            elif m=="tools/list":resp["result"]={"tools":[
                {"name":"mem_save","description":"Save memory","inputSchema":{"type":"object","properties":{"collection":{"type":"string"},"content":{"type":"string"},"tags":{"type":"array","items":{"type":"string"}},"metadata":{"type":"object"}},"required":["content"]}},
                {"name":"mem_search","description":"Semantic search","inputSchema":{"type":"object","properties":{"collection":{"type":"string"},"query":{"type":"string"},"limit":{"type":"integer"},"tags":{"type":"array","items":{"type":"string"}}},"required":["query"]}},
                {"name":"mem_stats","description":"Collection stats","inputSchema":{"type":"object","properties":{"collection":{"type":"string"}},"required":["collection"]}},
                {"name":"mem_list_collections","description":"List collections","inputSchema":{"type":"object","properties":{}}},
                {"name":"mem_delete","description":"Delete memory","inputSchema":{"type":"object","properties":{"collection":{"type":"string"},"point_id":{"type":"string"}},"required":["collection","point_id"]}},
                {"name":"capture_send","description":"Send conversation capture to MemoryHub daemon (Mode A MCP)","inputSchema":{"type":"object","properties":{"platform":{"type":"string"},"role":{"type":"string"},"content":{"type":"string"}},"required":["platform","content"]}}
            ]}
            elif m=="tools/call":
                tn=req["params"]["name"];args=req["params"].get("arguments",{})
                try:f=TOOLS.get(tn) or (lambda a:json.dumps({"error":f"unknown: {tn}"}))
                except Exception:f=lambda a:json.dumps({"error":"tool error"})
                resp["result"]={"content":[{"type":"text","text":f(args)}]}
            elif m!="notifications/initialized":resp["error"]={"code":-32601,"message":f"unknown: {m}"}
            sys.stdout.write(json.dumps(resp,ensure_ascii=False)+"\n");sys.stdout.flush()
        except (json.JSONDecodeError,ValueError):continue
        except KeyboardInterrupt:break

if __name__=="__main__":asyncio.run(run())
