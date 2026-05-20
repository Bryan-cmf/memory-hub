#!/usr/bin/env python3
"""MemoryHub Security — 敏感信息過濾 + 記憶加密 + 訪問日誌"""

import os, re, json, hashlib
from pathlib import Path
from datetime import datetime, timezone

MH_DIR = Path(os.path.expanduser("~/.memory-hub"))
AUDIT_LOG = MH_DIR / "audit.log"

SENSITIVE_PATTERNS = [
    (r'sk-[a-zA-Z0-9]{32,}', 'API_KEY'),
    (r'Bearer\s+[a-zA-Z0-9\-_\.]{20,}', 'BEARER_TOKEN'),
    (r'password\s*[:=]\s*\S+', 'PASSWORD'),
    (r'secret\s*[:=]\s*\S+', 'SECRET'),
    (r'-----BEGIN.*PRIVATE KEY-----', 'PRIVATE_KEY'),
    (r'\b\d{16,19}\b', 'CREDIT_CARD'),  # Simple check, may false positive
]

def scan_for_secrets(content: str) -> list:
    """Detect sensitive information in memory content."""
    findings = []
    for pattern, label in SENSITIVE_PATTERNS:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            findings.append({"type": label, "count": len(matches), "redacted": True})
    return findings

def redact_content(content: str) -> str:
    """Redact sensitive patterns from content."""
    for pattern, _ in SENSITIVE_PATTERNS:
        content = re.sub(pattern, '[REDACTED]', content, flags=re.IGNORECASE)
    return content

def log_access(action: str, details: str = ""):
    """Record memory access to audit log."""
    MH_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "details": details[:200],
        "pid": os.getpid()
    }
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    # Rotate if > 1000 lines
    if AUDIT_LOG.exists() and AUDIT_LOG.stat().st_size > 100000:
        AUDIT_LOG.rename(AUDIT_LOG.with_suffix(".log.bak"))

def hash_content(content: str) -> str:
    """SHA256 hash for integrity verification."""
    return hashlib.sha256(content.encode()).hexdigest()

if __name__ == "__main__":
    test = "api_key = sk-abc123def456ghi789jkl012mno345pqr678stu"
    findings = scan_for_secrets(test)
    print(f"Secrets found: {len(findings)}")
    for f in findings:
        print(f"  {f['type']}: {f['count']} occurrences")
    print(f"Redacted: {redact_content(test)}")
