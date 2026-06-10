# MemoryHub Architecture

> C4 Model, v2.0 · Last updated: 2026-06-11

## System Context

```
                        ┌─────────────┐
                        │   👤 User    │
                        └──────┬──────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  OpenClaw    │    │  Hermes      │    │  DeepSeek    │
│  Agent       │    │  Agent       │    │  Agent       │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                   │
       │  MCP / Filesystem │                   │
       ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────┐
│                   MemoryHub                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Capture  │  │ Storage  │  │   Dashboard      │  │
│  │ Engine   │──▶ Qdrant   │  │   :3872          │  │
│  │          │──▶ Files    │  │                  │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## Container Diagram

```
┌─────────────────────────────────────────────────────┐
│                   memory_hub/                        │
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ daemon   │  │ backends │  │  api_server      │  │
│  │ Capture  │──▶ Qdrant   │  │  Dashboard HTML   │  │
│  │ MODE A+B │  │ Chroma   │  │  REST /hook       │  │
│  │ Scanner  │  │ (10 BE)  │  │  /api/state       │  │
│  └────┬─────┘  └──────────┘  │  /api/search       │  │
│       │                      └──────────────────┘  │
│       ▼                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ sync     │  │ server/  │  │  cli              │  │
│  │ engine   │  │ mcp      │  │  CLI interface    │  │
│  │          │  │ stdio    │  │                  │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## Component Diagram: Capture Engine

```
     MODE A (MCP Real-time)        MODE B (Filesystem Scan)
     ┌──────────────┐              ┌──────────────┐
     │ mcp_intercept│              │ _discover()  │
     │ (hook)       │              │ _scan_file() │
     └──────┬───────┘              └──────┬───────┘
            │                             │
            ▼                             ▼
     ┌─────────────────────────────────────────┐
     │            _process()                    │
     │    De-duplicate → Classify → Score      │
     └──────────────┬──────────────────────────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ Qdrant  │ │ File    │ │ STATE   │
   │ Vector  │ │ JSONL   │ │ (live)  │
   └─────────┘ └─────────┘ └─────────┘
```

## Data Flow

```
Session JSONL (4 platforms)
    │
    ▼
capture_daemon (Mode B scan, every 60s)
    │
    ├──→ Qdrant (vector index, BGE-m3 1024-dim)
    ├──→ ~/.memory-hub/captured/{platform}/ (source files)
    └──→ STATE (in-memory, dashboard reads)
    
MCP tools (mem_search, mem_save)
    │
    ▼
capture_daemon (Mode A intercept)
    │
    └──→ _process() → Qdrant + Files + STATE
```

## Design Decisions (ADR)

### ADR-1: Why Qdrant as Primary Vector DB?
**Decision:** Qdrant as default, others optional.
**Rationale:** Highest performance for semantic search, native Docker support, REST API.
**Trade-off:** Requires Docker runtime. Users without Docker use file-only mode.

### ADR-2: Why dual capture (MCP + Filesystem)?
**Decision:** Both Mode A (real-time MCP intercept) and Mode B (filesystem scan).
**Rationale:** Mode A is fast but platform-specific. Mode B is universal but delayed. Together they cover all platforms.

### ADR-3: Why in-memory STATE + file persistence?
**Decision:** STATE in memory for dashboard performance, backed by JSON files for restart survival.
**Rationale:** Dashboard needs sub-millisecond reads. Qdrant is the source of truth; STATE is a cache.
**Trade-off:** STATE loss on crash is acceptable (rebuilds from Qdrant on restart).

## Current Limitations

| Area | Issue | Planned Fix |
|------|-------|-------------|
| daemon.py | 1280 lines, 5 responsibilities | Extract api_server, state_manager |
| Reliability | No circuit breaker on Qdrant calls | Add tenacity retry + timeout |
| Scalability | Single-node only | Add Qdrant cluster support |
| Platform config | Hard-coded dict | External YAML/JSON config |
