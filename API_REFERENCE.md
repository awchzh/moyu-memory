# MOYU API Reference

> **Status:** Draft — covering core APIs. Lower-level module APIs coming soon.

## `moyu_toolkit.agent_memory`

Core memory engine — TEMPR retrieval, add/delete/search.

### `add_memory(summary, source="user", metadata=None) -> dict | None`

Add a memory entry. Goes through content security gate + PII redaction + optional LLM summary enhancement.

```python
from moyu_toolkit import agent_memory as mem

# Basic usage
mem.add_memory("User prefers concise responses")

# With namespace (v2.5.2+)
mem.add_memory("Decision: use FastEmbed for local vectors",
               metadata={"namespace": "project-moyu"})
```

**Returns:** `{"id": "mem_...", "timestamp": "...", "summary": "...", ...}` or `None` if blocked by security gate.

### `search(query, top_k=5, namespace=None) -> list[dict]`

TEMPR multi-strategy retrieval: semantic + BM25 + time-weighted + optional LLM rerank.

```python
results = mem.search("what did we talk about last time")
results = mem.search("defense chain design", namespace="project-moyu")
```

**Returns:** `[{"memory_id", "summary", "timestamp", "source", "score", "entities"}, ...]`

### `stats()`

Print memory statistics to stdout.

### `_load_memories() -> list[dict]`

Load all memories from JSON (useful for debugging).

---

## `moyu_toolkit.defense_toolkit.integrity_checker`

Security gate and integrity checker.

### `content_scan(text) -> list[str]`

Scan text against 513 injection patterns. Returns list of matched labels (empty = clean).

### `llm_scan(text) -> dict`

Optional second layer — LLM-based semantic injection detection.

---

## `moyu_toolkit.knowledge_graph`

Entity-relation knowledge graph with time-travel.

### `search(entity, snapshot=None)`
### `invalidate(source, target, relation)`
### `history(entity)`

---

## `moyu_toolkit.learner`

Correction learning and user profile extraction.

### `learn(text)`
### `detect_corrections(text)`
### `signals()`

---

## `moyu_toolkit.forgetting_curve`

Memory lifecycle management — 4-gate review + knowledge distillation.

### `run() -> dict`
### `stats()`

---

## `moyu_toolkit.context_manager`

Context-aware compression and task map.

### `compress()`
### `task_map()`

---

## `moyu_toolkit.active_context`

Working memory — survives context compression.

### `get(key)`
### `set(key, value)`

---

# CLI Command Reference

| Command | Description | Since |
|---------|-------------|-------|
| `moyu search <query>` | Search memories | v2.0 |
| `moyu search <query> --ns <ns>` | Search within namespace | v2.5.2 |
| `moyu learn <text>` | Learn from correction / teach security rule | v2.4 |
| `moyu learn <text> --ns <ns>` | Learn with namespace | v2.5.2 |
| `moyu rules` | List custom security rules | v2.5.2 |
| `moyu benchmark` | Run security benchmark | v2.5.2 |
| `moyu mutate` | Scan injection blind spots | v2.5.2 |
| `moyu doctor` | Memory health check | v2.5.2 |
| `moyu snapshot` | Export/restore memory snapshots | v2.5.2 |
| `moyu demo-attack` | Interactive attack demo | v2.5.2 |
| `moyu stats` | Show all statistics | v2.0 |
| `moyu setup` | Set security password | v2.3 |
| `moyu audit` | Full security audit | v2.3 |
| `moyu check` | File integrity check | v2.3 |
| `moyu init` | Initialize integrity manifest | v2.3 |
| `moyu compress` | Compression status | v2.4 |
| `moyu forget` | Forgetting curve status | v2.4 |
| `moyu reflect` | Self-reflection | v2.4 |
| `moyu context` | Behavioral rules | v2.4 |
| `moyu update` | Check/apply updates | v2.4 |
| `moyu kg` | Knowledge graph commands | v2.4 |
| `moyu kb` | Knowledge base commands | v2.4 |

---

# Architecture

```
┌─────────────────────────────────────────────────────┐
│                    user input                        │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│  🛡️  Layer 1: Content Security Gate (513 patterns)  │
│  └─ content_scan()                                   │
│     ├─ Regex match? → BLOCK + log                    │
│     └─ Custom rules? → BLOCK + log                   │
└────────────────────┬────────────────────────────────┘
                     │ (clean)
                     ▼
┌─────────────────────────────────────────────────────┐
│  🧠  Layer 2: LLM Security Guard (optional)          │
│  └─ llm_scan()                                       │
│     ├─ Semantic injection? → BLOCK                   │
│     └─ No API key? → Silent degrade                  │
└────────────────────┬────────────────────────────────┘
                     │ (clean)
                     ▼
┌─────────────────────────────────────────────────────┐
│  📝  PII Redaction + Smart Summary (LLM optional)   │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│  💾  MD5 Dedup → TEMPR Index → Write + Backup       │
│  └─ memory_search.db (SQLite FTS5)                  │
│  └─ vector_index.json (semantic vectors)             │
│  └─ conversation_memory.json (raw data)              │
└─────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────┐
│               TEMPR Multi-Strategy Retrieval          │
│                                                       │
│   query ──► Semantic ──┐                              │
│            ├─ BM25 ────┤                              │
│            ├─ Recency ─┼─► score_and_rank ──► results │
│            └─ Entities ┘        │                     │
│                                  ▼                     │
│                         LLM Rerank (optional)          │
└─────────────────────────────────────────────────────┘
```

---

> **Doc version:** 1.0 | **Last updated:** 2026-05-22
> **TODO:** Add examples for each API, expand module-level docs, add sequence diagrams.
