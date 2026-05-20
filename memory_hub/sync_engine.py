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
    results = {"qdrant": False, "chroma": False, "lancedb": False}

    # Always try Qdrant (primary)
    if _qdrant_available():
        results["qdrant"] = sync_to_qdrant(collection, content, metadata)

    # Chroma if installed
    if _chroma_available():
        results["chroma"] = sync_to_chroma(collection, content, metadata)

    # LanceDB if installed
    if _lancedb_available():
        results["lancedb"] = sync_to_lancedb(collection, content, metadata)

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
