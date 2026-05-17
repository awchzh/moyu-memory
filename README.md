# MOYU — Secure Memory Toolkit for AI Agents

**Your AI remembers every conversation, but is your memory safe? Will old memories bloat your context window?**

MOYU is a lightweight memory toolkit that gives your Agent a **secure, self-managing, cross-session persistent** memory system. Pure Python, zero infrastructure, plug-and-play with one folder. Works with Hermes, OpenClaw, LangChain, AutoGen, or any custom Python project.

**v2.4.0** — 25 capabilities, 6 categories.

---

## 🚀 Quick Start

```bash
pip install -r requirements.txt
```

Copy the `moyu_toolkit/` folder into your project and run:

```bash
cd moyu_toolkit
python3 moyu.py search "what did we talk about last time"
```

> **Zero-config mode:** Works out of the box without an API key. Install FastEmbed to unlock semantic search (`pip install fastembed`).

```bash
python3 moyu.py help          # List all commands
python3 moyu.py demo          # Show capabilities
python3 moyu.py init          # Initialize file integrity protection
```

---

## 📋 Command Reference

All commands through a single entry point:

```bash
python3 moyu.py <command> [arguments]
```

### 🛡️ Defense & Security (MOYU's competitive edge)

| Command | Description |
|------|------|
| `moyu setup` | Set security password (required for dangerous operations) |
| `moyu verify <type> [desc]` | Verify dangerous operations (delete, modify config, etc.) |
| `moyu unlock` | Unlock security system (auto-locks for 30 min after 3 failed attempts) |
| `moyu check` | Check file integrity (SHA256 comparison + auto-recovery) |
| `moyu audit` | Full security audit — all four defense layers |
| `moyu init` | Initialize integrity manifest |

Four-layer defense chain:
```
Layer 1 (pre-write): Content security gate + PII redaction → injections & sensitive data blocked
Layer 2 (pre-op): Password verification → dangerous operations blocked
Layer 3 (startup): Integrity check + forensic analysis → tampering detected
Layer 4 (post-op): Auto-restore → restore from daily backup
```

**Additional defenses:**
- **Write burst protection** — >30 writes in 60s triggers fine-grained rollback + 5-minute lock + alert
- **Tool call loop detection** — Intercepts infinite loops at agent layer, SHA256 fingerprint + cycle detection + hard abort
- **PII redaction** — Chinese & international phone/ID/bank cards + email/SSN/credit cards/IPs, regex-based auto-replacement

### 🧠 Memory & Retrieval

| Command | Description |
|------|------|
| `moyu search <query>` | TEMPR multi-strategy search (semantic + BM25 keywords + time-weighted) |
| `moyu stats` | Show all statistics (memory count, embedding type, source distribution) |
| `moyu status` | System status + defense chain visualization |
| `moyu context` | Get behavioral rules (inject into system prompt) |
| `moyu signals` | View active trigger words (from learner module) |

Search quality: Local FastEmbed 512-dim semantic vectors, no crash on missing — auto-degrades to n-gram + BM25. Backed by SQLite FTS5 full-text index.

### 📊 Knowledge Layer

| Command | Description |
|------|------|
| `moyu kg search <entity>` | Search entity relationships in knowledge graph |
| `moyu kg search <entity> --snapshot YYYY-MM-DD` | Time-travel query — view graph state at a past point in time |
| `moyu kg search <entity> --snapshot all` | Include all historical relations (including expired) |
| `moyu kg history <entity>` | View entity's complete timeline (lifecycle of all relations) |
| `moyu kg invalidate --source X --target Y --relation Z` | Mark a relation as expired (preserved for backtracking) |
| `moyu kg invalidate --entity E` | Expire an entity and all its relations |
| `moyu kg stats` | Knowledge graph stats (active/expired/total) |
| `moyu kb list` | List all workflow knowledge files |
| `moyu kb search <keyword>` | Search knowledge files |
| `moyu kb index` | Rebuild keyword index |
| `moyu kb read <file>` | Read a knowledge file |

### ⏳ Lifecycle & Context Management

| Command | Description |
|------|------|
| `moyu compress` | View compression status |
| `moyu compress --now` | Force manual compression (password required) |
| `moyu compress config` | View compression parameters |
| `moyu compress set <key> <value>` | Adjust compression thresholds |
| `moyu context` | One-line context usage percentage |
| `moyu forget` | View forgetting curve status (3-gate + density analysis + distillation stats) |
| `moyu forget config` | View forgetting curve parameters |
| `moyu forget set <key> <value>` | Adjust forgetting parameters (demote_days, archive_days, etc.) |
| `moyu ref <name>` | Read original content of a compressed memory |
| `moyu ref list` | List all compressed memory references |

Forgetting curve + knowledge distillation:
- **Three gates** (OR logic): Safety window (14 days) → Access density analysis → Scene association protection
- **Distillation**: Entity relations auto-extracted to knowledge graph before demotion — structural knowledge survives when raw memory is cleared
- **Task map**: Auto-generated Mermaid task graph on wake — agent sees the big picture at a glance

### 🔄 Learning & Self-Reflection

| Command | Description |
|------|------|
| `moyu learn <text>` | Learn from user corrections (3 identical corrections → permanent rule) |
| `moyu detect <text>` | Detect correction signals in text |
| `moyu reflect` | Self-reflect (cross-time association analysis, contradiction detection) |

### 🔗 Session & Maintenance

| Command | Description |
|------|------|
| `moyu bridge` | View cross-session bridge status (prefill + current_context dual sync) |
| `moyu update` | Check GitHub for updates (TOFU checksum verification) |
| `moyu update now` | Download and apply latest update (password required) |
| `moyu demo` | Interactive capability showcase |

---

## 🔬 25 Capabilities Detailed

### 🛡️ Defense Layer (8)

| # | Capability | Description |
|---|-----------|------|
| 1 | **Content Security Gate** | Blocks injection attacks before writing (120+ patterns, 8 categories) |
| 2 | **Forensic Analysis** | Detects injection patterns, JSON corruption, file tampering |
| 3 | **Write Burst Protection** | >30 writes/60s triggers fine-grained rollback + 5-min lock |
| 4 | **Tool Call Loop Detection** | Agent-level infinite loop interception, SHA256 fingerprint + exhaustive cycle scan + hard abort |
| 5 | **PII Redaction** | Bilingual: Chinese & international phones, ID cards, bank cards, emails, SSNs, IPs — regex-based |
| 6 | **Password Verification** | Pre-op confirmation + auto-lock after 3 failures (30 min) |
| 7 | **Integrity Check & Recovery** | SHA256 manifest + daily backups (3-day retention) |
| 8 | **Alert Framework** | Content gate / write burst dual alert channels |

### 🧠 Memory Layer (4)

| # | Capability | Description |
|---|-----------|------|
| 9 | **TEMPR Multi-Strategy Retrieval** | Semantic embedding + BM25 keywords + time-weighted hybrid ranking |
| 10 | **FastEmbed Local Embedding** | Local ONNX vectorization, no API dependency, auto-degrade to n-gram |
| 11 | **SQLite FTS5** | Full-text index for accelerated keyword search |
| 12 | **MD5 Dedup** | In-library + batch double dedup |

### 📊 Knowledge Layer (3)

| # | Capability | Description |
|---|-----------|------|
| 13 | **Knowledge Graph** | Entity-relation extraction + time-travel snapshots + relation invalidation + full timeline + knowledge distillation |
| 14 | **Workflow Knowledge Base** | Markdown knowledge file indexing + keyword search |
| 15 | **User Profile** | Auto-extract preferences, habits, facts from conversation |

### ⏳ Lifecycle Layer (4)

| # | Capability | Description |
|---|-----------|------|
| 16 | **Two-Tier Progressive Compression** | 70% mild / 85% aggressive, originals preserved with traceable refs/ |
| 17 | **Task Map** | Auto-generated Mermaid task graph on wake — see full progress at a glance |
| 18 | **Forgetting Curve** | Three gates (safety window / access density / scene protection) + knowledge distillation |
| 19 | **Memory Merge** | Detect keyword-overlapping related memories and merge, originals preserved |

### 🔄 Learning & Reflection (2)

| # | Capability | Description |
|---|-----------|------|
| 20 | **Learn from Corrections** | Auto-detect correction signals, 3 identical corrections → permanent behavioral rule |
| 21 | **Self-Reflection** | Analyze memory base on startup, discover cross-time associations, contradictions, topic shifts |

### 🔗 Integration Layer (4)

| # | Capability | Description |
|---|-----------|------|
| 22 | **Working Memory** | Independent file, survives context compression |
| 23 | **Cross-Session Bridge** | Conversation summaries auto-synced to prefill + current_context, continuity across sessions |
| 24 | **Auto-Update** | Check GitHub for new versions, in-place update (TOFU checksum), preserves user data and config |
| 25 | **Wake Orchestration** | `moyu_wake`: full module pipeline — check→backup→forget→merge→reflect→context→bridge |

---

## 📁 File Structure

```
moyu_toolkit/
├── agent_memory.py          # Vector memory engine + TEMPR retrieval
├── agent_memory_sqlite.py   # SQLite FTS5 search index
├── active_context.py        # Working memory (compression-surviving)
├── context_manager.py       # Context-aware compression + task map
├── forgetting_curve.py      # Memory lifecycle — three gates + knowledge distillation
├── memory_merge.py          # Topic-aware memory merging
├── knowledge_graph.py       # Entity-relation knowledge graph (with time-travel)
├── knowledge_base.py        # Workflow knowledge base
├── learner.py               # Learn from corrections + user profile
├── security.py              # Memory self-protection — password + lockout
├── session_bridge.py        # Cross-session continuity
├── moyu.py                  # Unified CLI entry point
├── moyu_wake.py             # Startup integration pipeline
├── moyu_demo.py             # Interactive demo
├── updater.py               # Auto-update (TOFU checksum verification)
├── self_reflection.py       # Self-reflection
├── defense_toolkit/
│   ├── integrity_checker.py # File integrity + auto-recovery + forensic analysis + alerts
│   ├── forensic_patterns.json # Injection detection rule base (120+ patterns)
│   └── pii_redactor.py      # PII redaction (bilingual)
├── tests/
│   └── test_all.py          # Automated tests (26 items)
├── config.yaml              # API keys & settings
└── requirements.txt
```

---

## 🏆 Comparison

| Dimension | Built-in (Hermes/OpenClaw) | Mem0 | **MOYU** |
|------|------------------------|------|----------|
| Storage | Plain text files | Vector DB | **JSON + SQLite FTS5** |
| Search | Full dump | Semantic (API/LLM) | **TEMPR triple strategy** |
| Security | ❌ None | ❌ None | **✅ 4-layer defense chain** |
| PII Redaction | ❌ None | ❌ None | **✅ Bilingual (regex, zero deps)** |
| Tool Call Protection | ❌ None | ❌ None | **✅ Loop detection + hard abort** |
| Lifecycle | ❌ None | ❌ None | **✅ Forgetting curve + compression + task map** |
| Knowledge Graph | ❌ None | ❌ None | **✅ Time-travel + snapshots + distillation** |
| Working Memory | ❌ None | ❌ None | **✅ Independent file, compression-surviving** |
| Cross-Session | Manual | ❌ None | **✅ Auto-sync prefill + current_context** |
| Platform Lock-in | Locked | SDK locked | **✅ Zero lock-in** |
| API Lock-in | Fixed | OpenAI | **✅ Hot-swappable** |
| Deployment | Out of box | 5 min + API Key | **pip install, 30 sec** |
| Offline | Partial | Requires API Key | **✅ Full local degradation** |

---

## 🎮 Use Cases

- Want your AI Agent to **remember cross-session conversations** with real security
- Frequently hit **context limits**, need auto-compression without losing important memories
- Concerned about **PII leaks** — don't want phone numbers, IDs lingering in memory files
- Switching between **Hermes, OpenClaw, LangChain, or custom projects**, need a unified memory solution
- Want **zero infrastructure** — no Docker, no databases, no signups

---

## 📜 License

MIT
