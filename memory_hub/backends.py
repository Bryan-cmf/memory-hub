#!/usr/bin/env python3
"""
MemoryHub Multi-Backend Engine v1.0
Embed once (BGE-m3 1024-dim) → write to all configured backends.

Backends: Qdrant | Chroma | LanceDB | SQLite-vec | FAISS | Redis | PostgreSQL | Elasticsearch | MongoDB | Neo4j
"""

import json, os, sys, re, uuid, time, logging, hashlib, threading
from pathlib import Path
from datetime import datetime, timezone, timedelta

MH_DIR = Path(os.path.expanduser("~/.memory-hub"))
CONFIG_FILE = MH_DIR / "backend_config.json"
DIM = 1024  # BGE-m3, auto-detected at runtime via get_embedding_dim()

# Initialize logging and constants
from memory_hub import logging_config
from memory_hub.logging_config import get_logger
from memory_hub.constants import HKT
logger = get_logger("backends")

# SQL injection prevention: whitelist for table/collection/index names
_IDENT_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]{0,127}$')

def _safe_ident(name: str) -> str:
    """Validate a SQL/table/collection identifier. Raises ValueError if unsafe."""
    if not _IDENT_RE.match(name):
        raise ValueError(f"Invalid identifier (must match [a-zA-Z_][a-zA-Z0-9_]{{0,127}}): {name!r}")
    return name

# ── Client cache (avoid re-creating connections) ──────────────────
_CLIENT_CACHE = {}
_CLIENT_LOCK = threading.Lock()

def _get_cached_client(backend_name: str, factory_fn, *args, **kwargs):
    """Get or create a cached client instance for a backend."""
    if backend_name in _CLIENT_CACHE:
        return _CLIENT_CACHE[backend_name]
    with _CLIENT_LOCK:
        if backend_name in _CLIENT_CACHE:
            return _CLIENT_CACHE[backend_name]
        try:
            client = factory_fn(*args, **kwargs)
            _CLIENT_CACHE[backend_name] = client
            return client
        except Exception as e:
            logging.getLogger(__name__).debug(f"Failed to create {backend_name} client: {e}")
            return None

DEFAULT_CONFIG = {
    "qdrant":        {"enabled": True, "url": os.getenv("QDRANT_URL", "http://localhost:6333"), "collection": "openclaw_mem"},
    "chroma":        {"enabled": False, "path": str(MH_DIR / "chroma"), "collection": "memories"},
    "lancedb":       {"enabled": False, "path": str(MH_DIR / "lancedb"), "table": "memories"},
    "sqlite_vec":    {"enabled": True, "path": str(MH_DIR / "mh_sqlite_vec.db"), "table": "memories"},
    "faiss":         {"enabled": False, "path": str(MH_DIR / "faiss"), "index": "mh.index"},
    "redis":         {"enabled": False, "url": os.getenv("REDIS_URL", "redis://localhost:6379"), "key_prefix": "mh:"},
    "postgresql":    {"enabled": False, "url": os.getenv("POSTGRESQL_URL", "postgresql://postgres:postgres@localhost:5433/memoryhub"), "table": "memories"},
    "elasticsearch": {"enabled": False, "url": os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"), "index": "mh_memories"},
    "mongodb":       {"enabled": False, "url": os.getenv("MONGODB_URL", "mongodb://localhost:27017"), "db": "memoryhub", "collection": "memories"},
    "neo4j":         {"enabled": False, "url": os.getenv("NEO4J_URL", "bolt://localhost:7687"), "user": os.getenv("NEO4J_USER", "neo4j"), "password": os.getenv("NEO4J_PASSWORD", ""), "label": "Memory"},
}

def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

# ═══════════════════════════════════════════
# Embedding (BGE-m3, 1024-dim, cached)
# ═══════════════════════════════════════════

from memory_hub.embed import embed, get_embedding_dim

# ═══════════════════════════════════════════
# Backend Writers
# ═══════════════════════════════════════════

def _write_qdrant(cfg, pid, vec, payload):
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    qc = _get_cached_client(f"qdrant_write_{cfg['url']}", QdrantClient, url=cfg["url"])
    if not qc:
        return "error: failed to create qdrant client"
    col = cfg["collection"]
    existing = {c.name for c in qc.get_collections().collections}
    if col not in existing:
        qc.create_collection(col, vectors_config=VectorParams(size=DIM, distance=Distance.COSINE, on_disk=True))
    qc.upsert(col, points=[PointStruct(id=pid, vector=vec, payload=payload)])
    return "ok"


def _write_chroma(cfg, pid, vec, payload):
    import chromadb
    c = _get_cached_client(f"chroma_write_{cfg['path']}", chromadb.PersistentClient, path=cfg["path"])
    if not c: return "error: failed to create chroma client"
    col_name = cfg["collection"]
    try:
        coll = c.get_collection(col_name)
    except Exception:
        coll = c.create_collection(col_name, metadata={"hnsw:space": "cosine"})
    # Chroma requires non-empty metadata values
    safe = {}
    for k, v in payload.items():
        if v is None or v == "":
            safe[k] = "none"
        elif isinstance(v, list) and len(v) == 0:
            safe[k] = ["none"]
        elif isinstance(v, list):
            safe[k] = [str(x) for x in v]
        else:
            safe[k] = str(v)
    coll.upsert(ids=[pid], embeddings=[vec], metadatas=[safe],
                documents=[str(payload.get("content",""))[:500]])
    return "ok"


def _write_lancedb(cfg, pid, vec, payload):
    import lancedb
    import pyarrow as pa
    db = _get_cached_client(f"lancedb_write_{cfg['path']}", lancedb.connect, cfg["path"])
    if not db: return "error: failed to create lancedb client"
    tbl = cfg["table"]
    row = {"id": pid, "vector": vec, "content": str(payload.get("content",""))[:2000],
           "platform": str(payload.get("platform","")), "created_at": str(payload.get("created_at",""))}
    try:
        t = db.open_table(tbl)
        t.add([row])
    except Exception:
        try:
            db.drop_table(tbl)
        except Exception:
            pass
        schema = pa.schema([
            pa.field("id", pa.string()), pa.field("vector", pa.list_(pa.float32(), DIM)),
            pa.field("content", pa.string()), pa.field("platform", pa.string()),
            pa.field("created_at", pa.string())
        ])
        db.create_table(tbl, schema=schema, mode="overwrite")
        db.open_table(tbl).add([row])
    return "ok"


def _write_sqlite_vec(cfg, pid, vec, payload):
    import sqlite3
    db_path = cfg["path"]
    table = _safe_ident(cfg["table"])
    conn = sqlite3.connect(db_path)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id TEXT PRIMARY KEY, content TEXT, platform TEXT, created_at TEXT, embedding TEXT
        )
    """)
    conn.execute(f"INSERT OR REPLACE INTO {table} VALUES (?,?,?,?,?)",
                 [pid, str(payload.get("content",""))[:2000], str(payload.get("platform","")),
                  str(payload.get("created_at","")), json.dumps(vec)])
    conn.commit()
    conn.close()
    return "ok"


def _write_faiss(cfg, pid, vec, payload):
    import faiss
    import numpy as np
    index_path = cfg.get("path", str(MH_DIR / "faiss")) + "/" + cfg.get("index", "mh.index")
    Path(cfg.get("path", str(MH_DIR / "faiss"))).mkdir(parents=True, exist_ok=True)
    vec_np = np.array([vec], dtype=np.float32)
    if os.path.exists(index_path):
        idx = faiss.read_index(index_path)
        idx.add(vec_np)
    else:
        idx = faiss.IndexFlatIP(DIM)
        idx.add(vec_np)
    faiss.write_index(idx, index_path)
    # Metadata sidecar
    meta_path = cfg.get("path", str(MH_DIR / "faiss")) + "/meta.jsonl"
    with open(meta_path, "a") as f:
        f.write(json.dumps({"id": pid, "content": str(payload.get("content",""))[:500],
                           "platform": payload.get("platform",""), "created_at": payload.get("created_at","")},
                          ensure_ascii=False) + "\n")
    return "ok"


def _write_redis(cfg, pid, vec, payload):
    import redis as redispy
    r = _get_cached_client(f"redis_write_{cfg['url']}", redispy.from_url, cfg["url"])
    if not r: return "error: failed to create redis client"
    prefix = cfg.get("key_prefix", "mh:")
    r.json().set(f"{prefix}{pid}", "$", {
        "id": pid, "vec": vec, "content": str(payload.get("content",""))[:1000],
        "platform": str(payload.get("platform","")), "tags": payload.get("tags",[]),
        "created_at": str(payload.get("created_at",""))
    })
    return "ok"


def _write_postgresql(cfg, pid, vec, payload):
    import psycopg2
    table = _safe_ident(cfg["table"])
    conn = _get_cached_client(f"pg_write_{cfg['url']}", psycopg2.connect, cfg["url"])
    if not conn: return "error: failed to create postgresql client"
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id TEXT PRIMARY KEY, content TEXT, platform TEXT,
            tags TEXT[], created_at TIMESTAMPTZ, embedding vector({DIM})
        )
    """)
    cur.execute(f"INSERT INTO {table} (id, content, platform, tags, created_at, embedding) "
                f"VALUES (%s, %s, %s, %s, %s, %s::vector) ON CONFLICT (id) DO NOTHING",
                [pid, str(payload.get("content",""))[:2000], str(payload.get("platform","")),
                 payload.get("tags", []), payload.get("created_at",""), vec])
    conn.commit()
    cur.close(); conn.close()
    return "ok"


def _write_elasticsearch(cfg, pid, vec, payload):
    from elasticsearch import Elasticsearch
    es = _get_cached_client(f"es_write_{cfg['url']}", Elasticsearch, cfg["url"], request_timeout=10)
    if not es: return "error: failed to create elasticsearch client"
    idx = _safe_ident(cfg["index"])
    if not es.indices.exists(index=idx):
        es.indices.create(index=idx, body={
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
            "mappings": {"properties": {
                "content": {"type": "text"}, "platform": {"type": "keyword"},
                "tags": {"type": "keyword"}, "created_at": {"type": "date"},
                "embedding": {"type": "dense_vector", "dims": DIM, "index": True, "similarity": "cosine"}
            }}
        })
    es.index(index=idx, id=pid, document={
        "content": str(payload.get("content",""))[:2000],
        "platform": str(payload.get("platform","")),
        "tags": payload.get("tags", []),
        "created_at": str(payload.get("created_at","")),
        "embedding": vec
    }, refresh=False)
    return "ok"


def _write_mongodb(cfg, pid, vec, payload):
    from pymongo import MongoClient
    c = _get_cached_client(f"mongo_write_{cfg['url']}", MongoClient, cfg["url"], serverSelectionTimeoutMS=5000)
    if not c: return "error: failed to create mongodb client"
    col = c[cfg["db"]][cfg["collection"]]
    col.replace_one({"_id": pid}, {
        "_id": pid, "content": str(payload.get("content",""))[:2000],
        "platform": str(payload.get("platform","")), "tags": payload.get("tags", []),
        "created_at": str(payload.get("created_at","")), "embedding": vec
    }, upsert=True)
    return "ok"


def _write_neo4j(cfg, pid, vec, payload):
    from neo4j import GraphDatabase
    user = cfg.get("user", "neo4j")
    pwd = cfg.get("password", "")
    label = _safe_ident(cfg.get("label", "Memory"))
    driver = GraphDatabase.driver(cfg["url"], auth=(user, pwd))
    with driver.session() as s:
        s.run(f"MERGE (m:{label} {{id: $id}}) "
              "SET m.content = $content, m.platform = $platform, "
              "m.tags = $tags, m.created_at = $created_at, m.embedding = $embedding",
              id=pid, content=str(payload.get("content",""))[:2000],
              platform=str(payload.get("platform","")), tags=payload.get("tags", []),
              created_at=str(payload.get("created_at","")), embedding=vec)
    return "ok"


WRITERS = {
    "qdrant": _write_qdrant, "chroma": _write_chroma,
    "lancedb": _write_lancedb, "sqlite_vec": _write_sqlite_vec,
    "faiss": _write_faiss, "redis": _write_redis,
    "postgresql": _write_postgresql, "elasticsearch": _write_elasticsearch,
    "mongodb": _write_mongodb, "neo4j": _write_neo4j,
}

# ═══════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════

def multi_save(content: str, platform: str = "openclaw", tags=None,
                metadata=None, collection=None):
    """Embed once, write to all enabled backends. Returns {ok, fail, embed_ms, total_ms, point_id}."""
    global DIM
    t0 = time.time()
    cfg = load_config()
    tags = tags or []; metadata = metadata or {}
    pid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{platform}:{content}:{metadata.get('timestamp','')}"))
    payload = {"content": content, "platform": platform, "tags": tags,
               "created_at": datetime.now(HKT).isoformat(), **metadata}

    te = time.time()
    vec = embed(content)
    embed_ms = int((time.time() - te) * 1000)
    # Update DIM from model
    DIM = get_embedding_dim()

    if vec is None:
        return {"ok": [], "fail": [{"name": n, "error": "no embedding"} for n in WRITERS],
                "embed_time_ms": embed_ms, "total_time_ms": embed_ms, "point_id": pid}

    ok_list, fail_list = [], []
    # Route to platform-specific collection (openclaw → openclaw_mem, etc.)
    pf_collection = f"{platform}_mem"
    for name, writer in WRITERS.items():
        be_cfg = cfg.get(name, {}).copy()
        if not be_cfg.get("enabled", False):
            continue
        # Override collection/table/index for platform routing
        if name == "qdrant":
            be_cfg["collection"] = pf_collection
        elif name in ("chroma", "lancedb", "postgresql", "mongodb"):
            be_cfg["collection" if name != "lancedb" else "table"] = pf_collection
        elif name == "elasticsearch":
            be_cfg["index"] = pf_collection
        elif name == "neo4j":
            be_cfg["label"] = pf_collection.capitalize()
        try:
            writer(be_cfg, pid, vec, payload)
            ok_list.append(name)
        except Exception as e:
            fail_list.append({"name": f"{name}→{pf_collection}", "error": str(e)[:120]})

    return {"ok": ok_list, "fail": fail_list, "embed_time_ms": embed_ms,
            "total_time_ms": int((time.time() - t0) * 1000), "point_id": pid}


def health_check():
    """Quick connectivity test for all backends (uses cached clients)."""
    cfg = load_config()
    results = {}
    for name in WRITERS:
        if not cfg.get(name, {}).get("enabled", False):
            results[name] = "disabled"; continue
        try:
            c = cfg[name]
            if name == "qdrant":
                from qdrant_client import QdrantClient
                qc = _get_cached_client("qdrant", QdrantClient, url=c["url"])
                if qc: qc.get_collections()
            elif name == "chroma":
                import chromadb
                cc = _get_cached_client("chroma", chromadb.PersistentClient, path=c["path"])
                if cc: cc.list_collections()
            elif name == "lancedb":
                import lancedb; lancedb.connect(c["path"]).table_names()
            elif name in ("sqlite_vec", "faiss"):
                pass  # File-based, always available
            elif name == "redis":
                import redis as r
                rc = _get_cached_client("redis", r.from_url, c["url"])
                if rc: rc.ping()
            elif name == "postgresql":
                import psycopg2; psycopg2.connect(c["url"]).close()
            elif name == "elasticsearch":
                from elasticsearch import Elasticsearch
                ec = _get_cached_client("elasticsearch", Elasticsearch, c["url"], request_timeout=5)
                if ec: ec.ping()
            elif name == "mongodb":
                from pymongo import MongoClient
                mc = _get_cached_client("mongodb", MongoClient, c["url"], serverSelectionTimeoutMS=3000)
                if mc: mc.server_info()
            elif name == "neo4j":
                from neo4j import GraphDatabase
                u, p = c.get("user","neo4j"), c.get("password","")
                with GraphDatabase.driver(c["url"], auth=(u,p)).session() as s: s.run("RETURN 1")
            results[name] = "ok"
        except Exception as e:
            results[name] = f"error: {str(e)[:100]}"
    return results
