#!/usr/bin/env python3
"""MemoryHub Embedding — single source of truth for embedding model.

All modules that need embeddings should import from here:
    from memory_hub.embed import embed, get_embedding_dim

This prevents multiple model loads (which waste ~2GB RAM each).
"""

import os
import sys
import hashlib
import threading

_embedding_model = None
_vec_cache = {}
_EM_LOCK = threading.Lock()
EMBEDDING_DIM = None


def get_model():
    """Get or load the embedding model (thread-safe, singleton)."""
    global _embedding_model, EMBEDDING_DIM
    if _embedding_model is not None:
        return _embedding_model if _embedding_model is not False else None
    with _EM_LOCK:
        if _embedding_model is not None:
            return _embedding_model if _embedding_model is not False else None
        try:
            from sentence_transformers import SentenceTransformer
            dev = os.getenv("EMBEDDING_DEVICE", "mps" if sys.platform == "darwin" else "cpu")
            model_name = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
            print(f"[MH] Loading {model_name} on {dev}", file=sys.stderr)
            _embedding_model = SentenceTransformer(model_name, device=dev)
            try:
                EMBEDDING_DIM = _embedding_model.get_embedding_dimension() or 1024
            except AttributeError:
                try:
                    EMBEDDING_DIM = _embedding_model.get_sentence_embedding_dimension() or 1024
                except Exception:
                    EMBEDDING_DIM = 1024
        except Exception as e:
            print(f"[MH] Embedding load failed: {e}", file=sys.stderr, flush=True)
            _embedding_model = False
    return _embedding_model if _embedding_model is not False else None


def get_embedding_dim() -> int:
    """Get the embedding dimension (auto-detected from model)."""
    global EMBEDDING_DIM
    if EMBEDDING_DIM is None:
        get_model()
    return EMBEDDING_DIM or 1024


def embed(text: str):
    """Generate embedding vector for text (cached, thread-safe)."""
    if not text or not text.strip():
        return None
    key = hashlib.sha256(text[:500].encode()).hexdigest()
    with _EM_LOCK:
        if key in _vec_cache:
            return _vec_cache[key]
    model = get_model()
    if model is None:
        return None
    vec = model.encode(text[:8000], normalize_embeddings=True).tolist()
    with _EM_LOCK:
        _vec_cache[key] = vec
    return vec
