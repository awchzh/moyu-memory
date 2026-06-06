
**Your AI remembers every conversation. But —**

- **Is someone writing garbage into your memory?**
- **Did that private info you discussed yesterday leak into a file?**
- **Context window full — will you lose what matters?**

MOYU is a **security-first memory layer for AI Agents**. Pure Python, one folder, plug and play. LLM-enhanced features are **on by default**; no API key? Silent degrade, core memory keeps working.

**Install and go:**
```bash
pip install moyu-memory
moyu quickstart    # Chinese/English launcher → 5-step interactive demo
```

[![Tests](https://github.com/awchzh/moyu-memory/actions/workflows/test.yml/badge.svg)](https://github.com/awchzh/moyu-memory/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/moyu-memory)](https://pypi.org/project/moyu-memory/)
[![Python](https://img.shields.io/badge/python-%3E%3D3.8-blue)](https://pypi.org/project/moyu-memory/)
[![License](https://img.shields.io/github/license/awchzh/moyu-memory)](LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/moyu-memory)](https://pypi.org/project/moyu-memory/)

---

### Three things that make MOYU different

- **🛡️ Security built in** — Injection detection (regex + 8-class LLM guard), PII redaction, file integrity verification, write burst protection. Security isn't an add-on, it's default.
- **⏳ Lifecycle on autopilot** — Context compression, forgetting curve, memory merge — all automatic. No more losing important things when context fills up.
- **🧠 Retrieval + adaptive tuning** — Semantic + keyword + recency + entity hybrid search with configurable weights. Search feedback feeds `moyu tune` which auto-adjusts weights over time.

---

## 🏆 Comparison

| Dimension | MOYU | Mem0 | Letta | Zep | Cognee |
|------|------|------|-------|-----|--------|
| Setup | pip, zero config | pip + API Key | Runtime setup | Cloud simple, self-host complex | uv pip install |
| External deps | Storage layer zero-dependency | LLM API + vector DB | LLM API + storage | Self-host needs graph DB | LLM API |
| Security | Injection defense + PII redaction + integrity + zero-trust, on by default | API Key + compliance | Framework isolation | Cloud SOC2/HIPAA | Tenant isolation |
| Retrieval | Semantic+BM25+time+entity, configurable weights + adaptive tuning | Semantic+BM25+entity 3-way fusion | Agent tool pagination | **Temporal graph** | Graph+vector hybrid |
| Lifecycle | Compression/forgetting/merge/scene classification, fully automatic | ADD-only, no forgetting | 3-tier, auto pagination | Temporal graph auto versioning | Feedback learning, needs config |
| Knowledge Graph | Entity extraction + time-travel + distillation | Pro $249/mo | Indirect (external tools) | **Temporal graph, all tiers** | **Core feature, full OSS** |
| Offline | **Fully offline** | Partial (local embed) | Self-hostable | Self-host only | Fully local |

**Bottom line:** MOYU excels at security, offline capability, lifecycle management, and configurable retrieval — areas where alternatives offer little to none. Choose by your scenario, not by feature count.

---

## 🎮 Who is it for

- Your AI Agent needs **persistent memory** with real security
- Frequently hit **context limits**, need auto-compression without losing important content
- Worried about **PII leaks** — don't want phone numbers, IDs, API keys in memory files
- Want **zero infrastructure** — no Docker, no databases, no signups

---

## 🔬 Full Capability Index

*New here? Start with the "Three things that make MOYU different" section above, then the comparison table.*

### 🛡️ Defense Layer (11)

| # | Capability | Description |
|---|-----------|-------------|
| 1 | Content Security Gate | Pre-write injection blocking — 516 regex patterns + 8-class LLM recheck |
| 2 | Forensic Analysis | Detect injection patterns, JSON corruption, file tampering |
| 3 | Write Burst Protection | >30 writes/60s → rollback + 5-min lock |
| 4 | Tool Call Loop Detection | SHA256 fingerprint + exhaustive cycle scan + hard abort |
| 5 | PII Redaction | Bilingual: phones, IDs, bank cards, emails, SSNs, IPs, API keys |
| 6 | Password Verification | Pre-op confirmation + auto-lock after 3 failures (30 min) |
| 7 | Integrity Check & Recovery | SHA256 manifest + daily backups (3-day retention) |
| **8** | **Memory Digital Signature** | **HMAC-SHA256 per-file signing + verification + auto-recover from signed backup. Disabled by default, set `MOYU_SIGN_KEY` to enable** |
| 9 | User Isolation & Encryption (opt-in) | Per-user directories + AES-256-GCM encryption |
| 10 | LLM Security Guard | Regex-untouched inputs → LLM verdict (8 classes). **Never blocks legitimate writes** |
| 11 | Access Behavior Monitoring | Read burst detection (>100 reads/60s → alert). Every search is tracked. |

### 🧠 Memory & Retrieval Layer (8) *2 LLM-Enhanced*

| # | Capability | Description |
|---|-----------|-------------|
| 1 | TEMPR Multi-Strategy Retrieval | Semantic + BM25 + time-weighted + entity + progressive content (summary→overview→full) + semantic dedup, configurable weights |
| 2 | Search Rerank *LLM* | LLM re-ranks candidates by semantic relevance (on by default, degrades without key) |
| 3 | Smart Summary *LLM* | Writes auto-refined by LLM — filler out, facts in |
| 4 | FastEmbed Local Embedding | Local ONNX vectorization, no API needed, auto-degrades to n-gram |
| 5 | SQLite FTS5 + MD5 Dedup | Full-text index + in-memory/batch double dedup |
| 6 | Search Feedback Collection | Explicit votes + implicit ref/correction signals — feeds adaptive tuning |
| 7 | Adaptive Weight Tuning | `moyu tune` — auto-optimizes retrieval weights from feedback data |
| 8 | Auto Memory Extraction | Dual-channel fact extraction from conversation: fast rules (27 patterns, 0 token cost) + LLM (semantic edge cases). Enabled by default on every `moyu` command. |

### 📊 Knowledge Layer (3) *1 LLM-Enhanced*

| # | Capability | Description |
|---|-----------|-------------|
| 1 | Knowledge Graph *LLM* | Entity extraction + time-travel + relation invalidation + entity timeline + conflict auto-invalidation + distillation |
| 2 | Workflow Knowledge Base | Markdown indexing + keyword search |
| 3 | User Profile | Auto-extract preferences, habits, facts from conversation |

### ⏳ Lifecycle Layer (5) *3 LLM-Enhanced*

| # | Capability | Description |
|---|-----------|-------------|
| 1 | Context-Aware Compression + Warning | Two-tier compression, originals preserved, auto-warning before compression |
| 2 | Task Map | Auto-generated Mermaid task graph on wake |
| 3 | Forgetting Curve *LLM* | Four gates (safety/access/scene/LLM semantic review) + LLM scene classification |
| 4 | Memory Merge *LLM* | Related memories auto-merged with LLM summary, originals preserved |
| 5 | Access Heat Tracking & Decay | Per-memory heat tracking (HOT/WARM/COLD) with 5%/day time decay + auto-decay on search, drives retrieval priority |

### 🔄 Learning & Reflection (2)

| # | Capability | Description |
|---|-----------|-------------|
| 1 | Learn from Corrections | Auto-detect correction signals, 3 identical → permanent behavioral rule |
| 2 | Self-Reflection | Cross-time association, contradiction detection, topic shift analysis |

### 🔗 Integration Layer (6)

| # | Capability | Description |
|:--|-----------|-------------|
| 1 | Working Memory | Independent file, survives context compression |
| 2 | Cross-Session Bridge | 10-turn summaries + 3-round conversations + state (topic, decisions, pending) auto-synced across sessions. **Hermes users**: zero-config via prefill. **Other agents**: add a line to system prompt (see below). State auto-updates from recent memories on wake — no manual `moyu session` calls needed. |
| 3 | Auto-Update | GitHub release check + TOFU checksum + in-place update |
| 4 | Wake Orchestration | Check→backup→forget→merge→reflect→context→bridge — fully automatic |
| 5 | Memory Injection | `moyu inject` — standardized injection with built-in context warning |
| **6** | **Defense Log** | **All defense events unified to `defense_log.md` — signature fails, content blocks, PII redactions, burst rollbacks, loop aborts. Hermes users get auto chat notifications. `moyu doctor` shows a 24h summary right after the health score. Others: configure `defense_log.webhook` in config.yaml** |

> **For non-Hermes agents** — add this line to your Agent's system prompt to enable session continuation:
> ```
> When starting a new conversation, read ~/.moyu/session_state.json and use its content to continue from the previous session's context.
> ```

### 🛡️ Security Assessment

MOYU's defense chain is a **layered deterrent**, not a silver bullet. Honest assessment:

| Level | Threat | Coverage |
|-------|--------|----------|
| 🟢 | Accidental misuse (fat-finger, mis-script) | **~90%** |
| 🟢 | Script-kiddie injection (known patterns) | **~70%** |
| 🟡 | Simple prompt injection (standard variants) | **~65%** |
| 🟠 | Professional adversarial injection (targeted bypass) | **~25%** |
| 🟠 | Semantic injection (metaphor, no keywords) | **~60%** (LLM layer) |
| 🟢 | **Combined defense** | 1,769 test cases, 15 attack categories, **0% false positives**. Run `moyu benchmark --full` to reproduce |

---

## 🚀 Quick Start

**One-line install:**
```bash
pip install moyu-memory
```

**5-step interactive demo with Chinese/English switcher:**
```bash
moyu quickstart
# → Launcher prompts language selection, then walks through
# → 5 real-data modules: memory → defense → retrieval → stats → cleanup.
# → Zero config, no API key needed
```

**Integrate with your Agent:**
```bash
moyu inject "current conversation topic"
# → Outputs relevant memories (with context warning), ready for System Prompt injection
```

Or from your code:
```python
from moyu_toolkit.moyu import inject_context
inject_context("current conversation topic")  # Auto-search, format, inject
```

**Copy the toolkit (no pip needed):**
```bash
pip install -r requirements.txt
```
Copy the `moyu_toolkit/` folder into your project, run `python3 moyu.py`.

---

## 🔌 MCP Integration

MOYU can be used as a **Model Context Protocol (MCP) server**, exposing 29 tools across memory, search, defense, knowledge graph, knowledge base, lifecycle, reflection, learning, and diagnostics — for any MCP-compatible client: Hermes Agent, Claude Desktop, Cherry Studio, Kimi, Cursor, and more.

**How it works:** MOYU runs as a local stdio subprocess. Client starts it on demand; no daemon, no network port.

### Setup

```bash
pip install moyu-memory
```

Then add this to your MCP client configuration:

```json
{
  "mcpServers": {
    "moyu": {
      "command": "uvx",
      "args": ["--from", "moyu-memory@latest", "moyu-mcp"]
    }
  }
}
```

Or use the Python entry point directly: `python3 -m moyu_toolkit.mcp_server`

### Available Tools

| Tool | Description |
|------|-------------|
| `search_memory` | TEMPR semantic + keyword + recency + entity hybrid search |
| `add_memory` | Store memory with auto-deduplication and content security gate |
| `get_memory` | Retrieve a single memory by ID with full content |
| `list_memories` | Paginated list of all memories (newest first) |
| `memory_stats` | Memory statistics: count, storage size, embedding status |
| `heat_rank` | Heat rankings — which memories are HOT, WARM, or COLD |
| `defense_scan` | Content security scan — injection detection |
| `forensic_scan` | Forensic analysis — injection patterns, JSON corruption, tampering |
| `integrity_check` | Verify SHA256 checksums of all managed files |
| `pii_redact` | Redact PII — phone, ID, bank card, email, IP, API key |
| `guard_status` | Write burst protection status and lock state |
| `defense_log` | Recent security events — blocks, redactions, rollbacks |
| `signature_status` | HMAC-SHA256 memory signature status and verification |
| `kg_search` | Knowledge graph search — entities and relationships |
| `kg_entity_history` | Full timeline history of a specific entity |
| `kg_stats` | Knowledge graph statistics — entities, relations, scenes |
| `kb_search` | Knowledge base search — indexed Markdown files |
| `kb_list` | List all files in the knowledge base |
| `kb_read` | Read a knowledge base file by name |
| `forget_run` | Run forgetting curve demotion cycle |
| `forget_protect` | Protect a memory from being forgotten |
| `forget_unprotect` | Remove protection from a memory |
| `forget_stats` | Forgetting curve — protected count, tier distribution |
| `merge_run` | Run memory merge cycle (dry-run supported) |
| `reflect` | Self-reflection — contradictions, connections, topic shifts |
| `detect_signals` | Detect user correction signals in text |
| `learner_status` | Learned behavior rules and correction statistics |
| `active_context` | Active context — current task, working memory state |
| `memory_doctor` | Full health check — integrity, redundancy, security, storage |

---

## 📋 Command Reference

### Defense & Security
`moyu setup` `moyu verify` `moyu unlock` `moyu check` `moyu audit` `moyu rules list` `moyu rules remove <pattern>` `moyu rules whitelist <pattern>` `moyu protect`
`moyu benchmark` `moyu demo-attack` `moyu doctor` `moyu mutate` `moyu frequency stats` `moyu frequency unlock <name>`

### Memory & Retrieval
`moyu search <query>` `moyu search --vote <id> good|bad` `moyu search --ns <ns>`
`moyu inject <query>` `moyu config show` `moyu config set retrieval.weights.<dim> <val>`
`moyu tune` / `--dry-run` / `--reset` `moyu stats` `moyu status`
`moyu extract <text>` `moyu extract stats` `moyu memory detail <id>` `moyu memory heat-recalc`

### Knowledge Layer
`moyu kg search <entity>` `moyu kg history <entity>` `moyu kb search <keyword>`

### Lifecycle & Context
`moyu compress` `moyu context` `moyu forget` `moyu lifecycle` `moyu ref <name>` `moyu snapshot`

### Learning & Maintenance
`moyu learn <text>` `moyu detect <text>` `moyu signals` `moyu quickstart` `moyu demo` `moyu reflect` `moyu setup agents` `moyu update`

### Session & Bridge
`moyu session state` `moyu session prompt`
`moyu session decision <text>` `moyu session pending <text>` `moyu session clear`
`moyu bridge`

---

## 📚 Documentation

- [FAQ & Anti-Patterns](docs/FAQ.md) — Common pitfalls and solutions
- [Python API Integration Guide](docs/python_api.md) — Code examples and integration patterns

---

## 📁 File Structure

```
moyu_toolkit/
├── _llm_client.py            # Unified LLM client
├── agent_memory.py           # Vector memory engine + TEMPR retrieval
├── agent_memory_sqlite.py    # SQLite FTS5 search index
├── active_context.py         # Working memory
├── context_manager.py        # Context compression + warning + task map
├── forgetting_curve.py       # Forgetting curve + LLM review
├── memory_merge.py           # Memory merge
├── knowledge_graph.py        # Entity-relation knowledge graph
├── knowledge_base.py         # Workflow knowledge base
├── learner.py                # Learn from corrections
├── security.py               # Password + lockout
├── feedback.py               # Search feedback collection
├── tune.py                   # Adaptive weight tuning
├── quickstart.py             # Bilingual launcher + 5-step interactive demo
├── moyu.py                   # CLI entry point
├── moyu_wake.py              # Startup pipeline
├── defense_toolkit/
│   ├── integrity_checker.py  # File integrity + LLM guard
│   ├── forensic_patterns.json # 516 injection detection patterns
│   └── pii_redactor.py       # PII redaction
├── tests/
│   └── test_all.py           # Automated tests
├── config.yaml               # Configuration
└── requirements.txt
```

## 📜 License

MIT
