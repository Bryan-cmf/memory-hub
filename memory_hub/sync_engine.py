#!/usr/bin/env python3
"""Multi-Database Sync Engine — writes every capture to all available backends."""

import json, sys, os, uuid, hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

HKT = timezone(timedelta(hours=8))
MH_DIR = Path(os.path.expanduser("~/.memory-hub"))

# ── Embedding ─────────────────────────────────────

_embedding_model = None

def _get_embedding():
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("BAAI/bge-m3", device="mps" if sys.platform == "darwin" else "cpu")
    except Exception:
        _embedding_model = None
    return _embedding_model

def _vectorize(text: str) -> list:
    """Generate embedding vector (384-dim)."""
    em = _get_embedding()
    if not em:
        return None
    try:
        return em.encode(text[:8000], normalize_embeddings=True).tolist()
    except Exception:
        return None

# ── Qdrant ────────────────────────────────────────

def _qdrant_available() -> bool:
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:6333/collections", method="GET")
        resp = urllib.request.urlopen(req, timeout=3)
        return True
    except Exception:
        return False

def _qdrant_ensure_collection(name: str):
    try:
        import urllib.request
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams
        qc = QdrantClient(url="http://localhost:6333")
        existing = {x.name for x in qc.get_collections().collections}
        if name not in existing:
            qc.create_collection(name, vectors_config=VectorParams(size=384, distance=Distance.COSINE, on_disk=True))
        return qc
    except Exception:
        return None

def sync_to_qdrant(collection: str, content: str, metadata: dict) -> bool:
    """Write a capture to Qdrant."""
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct
        qc = _qdrant_ensure_collection(collection)
        if not qc:
            return False
        vec = _vectorize(content)
        if not vec:
            return False
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content + str(metadata.get("timestamp", ""))))
        payload = {"content": content, **metadata}
        qc.upsert(collection, points=[PointStruct(id=point_id, vector=vec, payload=payload)])
        return True
    except Exception:
        return False

# ── Chroma ────────────────────────────────────────

def _chroma_available() -> bool:
    try:
        import subprocess
        r = subprocess.run([sys.executable, "-m", "pip", "show", "chromadb"],
                          capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False

def sync_to_chroma(collection: str, content: str, metadata: dict) -> bool:
    """Write a capture to Chroma."""
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(MH_DIR / "chroma_data"))
        try:
            col = client.get_collection(collection)
        except Exception:
            col = client.create_collection(collection)
        vec = _vectorize(content)
        if not vec:
            return False
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content + str(metadata.get("timestamp", ""))))
        col.add(ids=[point_id], embeddings=[vec], documents=[content[:2000]],
                metadatas=[{k: str(v)[:500] for k, v in metadata.items()}])
        return True
    except Exception:
        return False

# ── LanceDB ───────────────────────────────────────

def _lancedb_available() -> bool:
    try:
        import subprocess
        r = subprocess.run([sys.executable, "-m", "pip", "show", "lancedb"],
                          capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False

def sync_to_lancedb(collection: str, content: str, metadata: dict) -> bool:
    """Write a capture to LanceDB."""
    try:
        import lancedb
        import pandas as pd
        db = lancedb.connect(str(MH_DIR / "lancedb_data"))
        vec = _vectorize(content)
        if not vec:
            return False
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content + str(metadata.get("timestamp", ""))))
        table_name = collection.replace("-", "_")
        data = pd.DataFrame([{
            "id": point_id, "vector": vec, "content": content[:2000],
            "platform": metadata.get("platform", ""), "channel": metadata.get("channel", ""),
            "memory_type": metadata.get("memory_type", ""), "importance": metadata.get("importance", 5),
            "timestamp": str(metadata.get("timestamp", "")),
        }])
        try:
            db.open_table(table_name).add(data)
        except Exception:
            db.create_table(table_name, data)
        return True
    except Exception:
        return False

# ── Unified Sync ──────────────────────────────────

def sync_capture(pid: str, msg: dict):
    """Sync a single capture to all available backends."""
    content = str(msg.get("content", ""))
    collection = f"{pid}_mem"
    metadata = {
        "platform": pid, "role": msg.get("role", ""), "channel": msg.get("channel", ""),
        "memory_type": msg.get("memory_type", ""), "importance": msg.get("importance", 5),
        "session_id": msg.get("session_id", ""), "timestamp": msg.get("timestamp", ""),
    }
    results = {}

    # Vector DBs
    if _qdrant_available():
        results["qdrant"] = sync_to_qdrant(collection, content, metadata)
    if _chroma_available():
        results["chroma"] = sync_to_chroma(collection, content, metadata)
    if _lancedb_available():
        results["lancedb"] = sync_to_lancedb(collection, content, metadata)
    if _sqlitevec_available():
        results["sqlite_vec"] = sync_to_sqlitevec(collection, content, metadata)
    if _faiss_available():
        results["faiss"] = sync_to_faiss(collection, content, metadata)

    # Traditional DBs with vector support
    if _redis_available():
        results["redis"] = sync_to_redis(collection, content, metadata)
    if _pgvector_available():
        results["pgvector"] = sync_to_pgvector(collection, content, metadata)
    if _elasticsearch_available():
        results["elasticsearch"] = sync_to_elasticsearch(collection, content, metadata)
    if _mongodb_available():
        results["mongodb"] = sync_to_mongodb(collection, content, metadata)

    return results


def get_all_stats() -> dict:
    """Get stats from all available databases."""
    stats = {}

    # Qdrant
    try:
        import urllib.request, json
        req = urllib.request.Request("http://localhost:6333/collections", method="GET")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        qdrant = {}
        for c in data.get("result", {}).get("collections", []):
            try:
                req2 = urllib.request.Request(f"http://localhost:6333/collections/{c['name']}", method="GET")
                resp2 = urllib.request.urlopen(req2, timeout=3)
                d2 = json.loads(resp2.read())
                qdrant[c["name"]] = d2.get("result", {}).get("points_count", 0)
            except:
                qdrant[c["name"]] = -1
        stats["qdrant"] = qdrant
    except Exception:
        stats["qdrant"] = {"error": "unavailable"}

    # Chroma
    if _chroma_available():
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(MH_DIR / "chroma_data"))
            chroma = {}
            for col in client.list_collections():
                chroma[col.name] = col.count()
            stats["chroma"] = chroma
        except Exception:
            stats["chroma"] = {"error": "unavailable"}

    # LanceDB
    if _lancedb_available():
        try:
            import lancedb
            db = lancedb.connect(str(MH_DIR / "lancedb_data"))
            ldb = {}
            for tn in db.table_names():
                t = db.open_table(tn)
                ldb[tn] = t.count_rows()
            stats["lancedb"] = ldb
        except Exception:
            stats["lancedb"] = {"error": "unavailable"}

    # SQLite-vec
    if _sqlitevec_available():
        try:
            import sqlite_vec
            import sqlite3
            db = sqlite3.connect(str(MH_DIR / "sqlite_vec.db"))
            db.enable_load_extension(True)
            sqlite_vec.load(db)
            rows = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'mem_%'").fetchall()
            sv = {}
            for (tn,) in rows:
                cnt = db.execute(f"SELECT COUNT(*) FROM \"{tn}\"").fetchone()[0]
                sv[tn] = cnt
            db.close()
            stats["sqlite_vec"] = sv
        except Exception:
            stats["sqlite_vec"] = {"error": "unavailable"}

    # FAISS (in-memory, non-persistent)
    stats["faiss"] = {"mode": "in-memory index (session only)", "indexes": len(_faiss_indexes) if "_faiss_indexes" in dir() else 0}

    # Redis
    if _redis_available():
        try:
            r = _get_redis()
            keys = r.keys("mh:*")
            stats["redis"] = {"keys": len(keys), "status": "connected"}
        except Exception:
            stats["redis"] = {"error": "unavailable"}

    # PostgreSQL + pgvector
    if _pgvector_available():
        try:
            conn = _get_pg()
            cur = conn.cursor()
            cur.execute("SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE relname LIKE 'mem_%'")
            pg = {}
            for name, rows in cur.fetchall():
                pg[name] = rows
            conn.close()
            stats["pgvector"] = pg
        except Exception:
            stats["pgvector"] = {"error": "unavailable"}

    # Elasticsearch
    if _elasticsearch_available():
        try:
            es = _get_es()
            indices = es.cat.indices(format="json")
            es_stats = {}
            for idx in indices:
                if idx["index"].startswith("mh-"):
                    cnt = es.count(index=idx["index"])["count"]
                    es_stats[idx["index"]] = cnt
            stats["elasticsearch"] = es_stats
        except Exception:
            stats["elasticsearch"] = {"error": "unavailable"}

    # MongoDB
    if _mongodb_available():
        try:
            db = _get_mongo()
            mongo_stats = {}
            for coll_name in db.list_collection_names():
                mongo_stats[coll_name] = db[coll_name].count_documents({})
            stats["mongodb"] = mongo_stats
        except Exception:
            stats["mongodb"] = {"error": "unavailable"}

    # File Storage
    file_stats = {}
    for label, subdir in [("captures", "captured"), ("memories", "memories"), ("hooks", "hooks")]:
        d = MH_DIR / subdir
        if d.exists():
            files = list(d.rglob("*.json*"))
            size = sum(f.stat().st_size for f in files if f.is_file())
            file_stats[label] = {"files": len(files), "size_bytes": size}
    stats["file"] = file_stats

    return stats


# ── SQLite-vec ────────────────────────────────────

def _sqlitevec_available() -> bool:
    try:
        import sqlite_vec
        return True
    except Exception:
        return False

def sync_to_sqlitevec(collection: str, content: str, metadata: dict) -> bool:
    try:
        import sqlite_vec, sqlite3, struct
        db = sqlite3.connect(str(MH_DIR / "sqlite_vec.db"))
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        vec = _vectorize(content)
        if not vec: return False
        tbl = f"mem_{collection.replace('-','_')}"
        db.execute(f"CREATE TABLE IF NOT EXISTS \"{tbl}\" (id TEXT PRIMARY KEY, content TEXT, platform TEXT, channel TEXT, memory_type TEXT, importance INTEGER, timestamp TEXT)")
        # Store vector as blob via virtual table
        vec_tbl = f"{tbl}_vec"
        db.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS \"{vec_tbl}\" USING vec0(embedding float[384])")
        db.execute(f"INSERT OR REPLACE INTO \"{tbl}\" VALUES (?,?,?,?,?,?,?)",
                   (str(uuid.uuid5(uuid.NAMESPACE_DNS, content)), content[:2000],
                    metadata.get("platform",""), metadata.get("channel",""),
                    metadata.get("memory_type",""), metadata.get("importance",5),
                    str(metadata.get("timestamp",""))))
        db.execute(f"INSERT INTO \"{vec_tbl}\" (rowid, embedding) VALUES (last_insert_rowid(), ?)",
                   (struct.pack(f'{len(vec)}f', *vec),))
        db.commit(); db.close()
        return True
    except Exception:
        return False


# ── FAISS ─────────────────────────────────────────

_faiss_indexes = {}

def _faiss_available() -> bool:
    try:
        import faiss
        return True
    except Exception:
        return False

def sync_to_faiss(collection: str, content: str, metadata: dict) -> bool:
    try:
        import faiss, numpy as np
        vec = _vectorize(content)
        if not vec: return False
        global _faiss_indexes
        if collection not in _faiss_indexes:
            _faiss_indexes[collection] = {"index": faiss.IndexFlatL2(384), "ids": [], "metas": []}
        idx = _faiss_indexes[collection]["index"]
        arr = np.array([vec], dtype=np.float32)
        idx.add(arr)
        _faiss_indexes[collection]["ids"].append(str(uuid.uuid5(uuid.NAMESPACE_DNS, content)))
        _faiss_indexes[collection]["metas"].append(metadata)
        return True
    except Exception:
        return False


# ── Redis ─────────────────────────────────────────

_redis_client = None

def _redis_available() -> bool:
    try:
        import redis
        r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=2)
        r.ping()
        return True
    except Exception:
        return False

def _get_redis():
    global _redis_client
    if _redis_client is None:
        import redis
        _redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
    return _redis_client

def sync_to_redis(collection: str, content: str, metadata: dict) -> bool:
    try:
        r = _get_redis()
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content))
        key = f"mh:{collection}:{point_id}"
        r.setex(key, 86400 * 90, json.dumps({"content": content[:2000], **metadata}))
        return True
    except Exception:
        return False


# ── PostgreSQL + pgvector ─────────────────────────

_pg_conn = None

def _pgvector_available() -> bool:
    try:
        import psycopg2
        conn = psycopg2.connect(host="localhost", port=5433, dbname="postgres", user="postgres", password="***", connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False

def _get_pg():
    import psycopg2
    return psycopg2.connect(host="localhost", port=5433, dbname="postgres", user="postgres", password="***")

def sync_to_pgvector(collection: str, content: str, metadata: dict) -> bool:
    try:
        conn = _get_pg()
        cur = conn.cursor()
        vec = _vectorize(content)
        if not vec: return False
        tbl = f"mem_{collection.replace('-','_')}"
        cur.execute(f"CREATE EXTENSION IF NOT EXISTS vector")
        cur.execute(f"CREATE TABLE IF NOT EXISTS {tbl} (id TEXT PRIMARY KEY, content TEXT, embedding vector(384), platform TEXT, channel TEXT, memory_type TEXT, importance INTEGER, timestamp TEXT)")
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content))
        vec_str = "[" + ",".join(str(v) for v in vec) + "]"
        cur.execute(f"INSERT INTO {tbl} VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING",
                    (point_id, content[:2000], vec_str, metadata.get("platform",""),
                     metadata.get("channel",""), metadata.get("memory_type",""),
                     metadata.get("importance",5), str(metadata.get("timestamp",""))))
        conn.commit(); conn.close()
        return True
    except Exception:
        return False


# ── Elasticsearch ─────────────────────────────────

_es_client = None

def _elasticsearch_available() -> bool:
    try:
        from elasticsearch import Elasticsearch
        es = Elasticsearch("http://localhost:9200", request_timeout=3)
        es.info()
        return True
    except Exception:
        return False

def _get_es():
    global _es_client
    if _es_client is None:
        from elasticsearch import Elasticsearch
        _es_client = Elasticsearch("http://localhost:9200")
    return _es_client

def sync_to_elasticsearch(collection: str, content: str, metadata: dict) -> bool:
    try:
        es = _get_es()
        index = f"mh-{collection.replace('_','-')}"
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content))
        vec = _vectorize(content)
        doc = {"content": content[:2000], "embedding": vec, **{k: v for k, v in metadata.items() if v is not None}}
        es.index(index=index, id=point_id, body=doc)
        return True
    except Exception:
        return False


# ── MongoDB ───────────────────────────────────────

_mongo_client = None

def _mongodb_available() -> bool:
    try:
        from pymongo import MongoClient
        c = MongoClient("mongodb://localhost:27017", serverSelectionTimeoutMS=3000)
        c.admin.command("ping")
        return True
    except Exception:
        return False

def _get_mongo():
    global _mongo_client
    if _mongo_client is None:
        from pymongo import MongoClient
        _mongo_client = MongoClient("mongodb://localhost:27017")
    return _mongo_client["memoryhub"]

def sync_to_mongodb(collection: str, content: str, metadata: dict) -> bool:
    try:
        db = _get_mongo()
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, content))
        coll = db[collection]
        coll.update_one({"_id": point_id}, {"$set": {"content": content[:2000], **metadata}}, upsert=True)
        return True
    except Exception:
        return False
