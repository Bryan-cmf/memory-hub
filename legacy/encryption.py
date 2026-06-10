#!/usr/bin/env python3
"""MemoryHub Security — Encryption + Hard Delete (7.2, 7.4)"""

import os, json, hashlib, base64
from pathlib import Path
from datetime import datetime, timezone
from cryptography.fernet import Fernet

MH_DIR = Path(os.path.expanduser("~/.memory-hub"))
KEY_FILE = MH_DIR / ".encryption_key"

def get_or_create_key() -> bytes:
    """Get existing encryption key or create a new one."""
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    key = Fernet.generate_key()
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_bytes(key)
    os.chmod(KEY_FILE, 0o600)  # Restrict permissions
    return key

def encrypt_content(content: str) -> str:
    """Encrypt content at rest."""
    key = get_or_create_key()
    f = Fernet(key)
    encrypted = f.encrypt(content.encode())
    return base64.b64encode(encrypted).decode()

def decrypt_content(encrypted: str) -> str:
    """Decrypt content."""
    key = get_or_create_key()
    f = Fernet(key)
    decrypted = f.decrypt(base64.b64decode(encrypted))
    return decrypted.decode()

def hard_delete_memory(collection: str, point_id: str, memory_dir: str = None) -> dict:
    """Hard delete: remove from both vector DB and file system (7.4)."""
    import urllib.request
    
    # Step 1: Delete from Qdrant
    try:
        req = urllib.request.Request(
            f"http://localhost:6333/collections/{collection}/points/delete",
            data=json.dumps({"points": [point_id]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        urllib.request.urlopen(req, timeout=5)
        vector_deleted = True
    except Exception as e:
        vector_deleted = False
    
    # Step 2: Remove from file system if path provided
    file_deleted = False
    if memory_dir:
        fp = Path(memory_dir)
        if fp.exists():
            fp.unlink()
            file_deleted = True
    
    return {
        "status": "deleted",
        "point_id": point_id,
        "vector_deleted": vector_deleted,
        "file_deleted": file_deleted,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

if __name__ == "__main__":
    # Test encryption
    test = "sensitive memory content"
    enc = encrypt_content(test)
    dec = decrypt_content(enc)
    print(f"Encryption test: {'✅' if test == dec else '❌'}")
    print(f"  Original: {test[:50]}")
    print(f"  Encrypted: {enc[:50]}...")
    print(f"  Decrypted: {dec[:50]}")
