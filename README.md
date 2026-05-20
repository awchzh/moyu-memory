# MOYU — Secure Memory Toolkit for AI Agents

**Your AI remembers every conversation, but is your memory safe? Will old memories bloat your context window?**

MOYU is a lightweight memory toolkit that gives your Agent a **secure, self-managing, cross-session persistent** memory system. Pure Python, zero infrastructure, plug-and-play with one folder. Works with Hermes, OpenClaw, LangChain, AutoGen, or any custom Python project.

**v2.5.0** — 6 LLM-enhanced features: semantic rerank, smart summary, AI merge, scene classification, entity extraction, and intelligent forgetting review. All default-on, keyless fallback to local rules. Now available via `pip install moyu-memory`.

---

## 🚀 Quick Start

**One-line install (recommended):**
```bash
pip install moyu-memory
```

Then use it anywhere:
```bash
moyu search "what did we talk about last time"
```

**Or copy the toolkit (no pip needed):**
```bash
pip install -r requirements.txt
```

Copy the `moyu_toolkit/` folder into your project and run:

```bash
cd moyu_toolkit
python3 moyu.py search "what did we talk about last time"
```

> **Zero-config mode:** Works out of the box without an API key. Install FastEmbed to unlock semantic search (see `requirements.txt`).

```bash
python3 moyu.py help          # List all commands
python3 moyu.py demo          # Show capabilities
python3 moyu.py init          # Initialize file integrity protection
```

---

## 🛡️ Security Capability — What MOYU Does and Doesn't Cover

MOYU's defense chain is a **layered deterrent**, not a silver bullet. Honest assessment by threat level:

| Level | Threat | Coverage | How |
|-------|--------|----------|-----|
| 🟢 | Accidental misuse (fat-finger, mis-script) | **~90%** | Password gate + burst guard + integrity check + daily backup |
| 🟢 | Script-kiddie injection (known patterns) | **~70%** | Content gate (433 patterns + regex combos) + loop detection |
| 🟡 | Simple prompt injection (standard variants) | **~60%** | Regex covers (forget|ignore|skip)×(previous|all|your)×(instructions|rules) |
| 🟠 | Professional adversarial injection (targeted bypass) | **~20%** | Keyword-based gates can't catch every novel variant |
| 🟠 | Semantic-level injection (metaphor, abstraction, no keywords) | **~60%** | LLM Security Guard detects semantic bypasses — regex-untouched patterns like "pretend to be DAN" are caught. Uses your configured LLM. Falls back to safe on API failure: **never blocks legitimate writes.** |

**How it works:** LLM Guard is a second layer after regex — regex untouched → LLM verdict. No API key? Silent degrade to regex-only. This means semantic injection coverage goes from ~0% to ~60% without breaking zero-config.

**MOYU's strength is in the combination:** content gate + LLM guard + PII redaction + write burst guard + forensic analysis + password gate + integrity check + auto-restore + loop detection — unique layers no other memory toolkit offers.

**Additional opt-in security** (config.yaml, disabled by default): user isolation (per-directory storage) & AES-256-GCM file encryption (requires `cryptography`, see `requirements.txt`).

---

## 📋 Command Reference

All commands through a single entry point:

```bash
python3 moyu.py <command> [arguments]
```

### 🛡️ Defense & Security

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
- **PII redaction** — Chinese & international phone/ID/bank cards + email/SSN/credit cards/IPs/API keys, regex-based auto-replacement

### 🧠 Memory & Retrieval

| Command | Description |
|------|------|
| `moyu search <query>` | TEMPR multi-strategy search (semantic + BM25 keywords + time-weighted) + **optional LLM rerank** |
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
| `moyu compress diagnose` | Show detailed scan results for all supported agents |
| `moyu context` | One-line context usage percentage |
| `moyu context raw` | Get behavioral rules (inject into system prompt) |
| `moyu forget` | View forgetting curve status (3-gate + density analysis + distillation stats) |
| `moyu forget config` | View forgetting curve parameters |
| `moyu forget set <key> <value>` | Adjust forgetting parameters (demote_days, archive_days, etc.) |
| `moyu ref <name>` | Read original content of a compressed memory |
| `moyu ref list` | List all compressed memory references |

Forgetting curve + knowledge distillation:
- **Four gates** (OR logic): Safety window (14 days) → Access density analysis → Scene association protection → **LLM semantic importance review**
- **Distillation**: Entity relations auto-extracted to knowledge graph before demotion — structural knowledge survives when raw memory is cleared
- **Task map**: Auto-generated Mermaid task graph on wake — agent sees the big picture at a glance

> **🧠 Context warning (v2.4.3):** Your agent compresses silently — now it tells you first. MOYU auto-detects your running agent (Hermes, Claude Code, OpenClaw, Cursor, or Continue), reads its real-time context usage, and injects a warning into the agent's behavior rules before compression kicks in.
>
> ```bash
> # Quick check — how full is your context window?
> python3 moyu.py context
> # → Hermes窗口: 85% (累计120,456/128,000, 45次调用) ⚠️ 已深度压缩
> # → 预警线: 70%
>
> # Set your preferred warning threshold and language
> moyu compress set warn_threshold 0.6    # warn at 60% (default: 0.7)
> moyu compress set warn_language zh       # Chinese warning (default: en)
> moyu compress config                     # view all parameters
> ```
>
> When the threshold is crossed, the warning auto-appends to your agent's behavioral rules:
> - *"Hermes context at 85%, conversation deeply compressed — /new recommended"*
> - *"Hermes context at 72%, approaching 70% warning — set MOYU warn below it"*
>
> **Supported agents:** Hermes ✅ (macOS, verified), Claude Code, OpenClaw, Cursor, Continue — all with cross-platform paths (macOS / Windows / Linux). Works out of the box for default installations.
>
> **Custom paths?** Bypass auto-detection with environment variables:
> ```bash
> export MOYU_FORCE_PROVIDER=Hermes
> export MOYU_PROVIDER_PATH="/custom/path/to/state.db"
> ```
>
> **Can't detect your agent?** Run the diagnostic command — it shows exactly where each agent's data is (or isn't):
> ```bash
> moyu compress diagnose
> # → [Hermes]    ✅ /Users/you/.hermes/state.db
> # → [Claude]    ❌ ~/.claude/projects (not found)
> # → [OpenClaw]  ✅ ~/.openclaw/agents
> ```

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

## 🔬 26 Capabilities Detailed (7 LLM-Enhanced)

| # | Capability | Description |
|---|-----------|------|
| **🛡️ Defense Layer (9)** |||
| 1 | **Content Security Gate** | Blocks injection attacks before writing (433 patterns + regex combos, 8 categories) |
| 2 | **Forensic Analysis** | Detects injection patterns, JSON corruption, file tampering |
| 3 | **Write Burst Protection** | >30 writes/60s triggers fine-grained rollback + 5-min lock |
| 4 | **Tool Call Loop Detection** | Runtime-level infinite loop interception, SHA256 fingerprint + exhaustive cycle scan + hard abort |
| 5 | **PII Redaction** | Bilingual: Chinese & international phones, ID cards, bank cards, emails, SSNs, IPs, API keys — regex-based, no deps |
| 6 | **Password Verification** | Pre-op confirmation + auto-lock after 3 failures (30 min) |
| 7 | **Integrity Check & Recovery** | SHA256 manifest + daily backups (3-day retention) |
| 8 | **User Isolation & Encryption** (opt-in) | Per-user storage directories + AES-256-GCM file encryption (requires `cryptography`, see `requirements.txt`) |
| 9 | **LLM Security Guard** *(LLM)* | Second layer after regex: regex-untouched inputs get LLM verdict for semantic injection. Uses your configured LLM. No API key? Degrades to regex-only — **never blocks legitimate writes.** |

### 🧠 Memory Layer (4) *2 LLM-Enhanced*

| # | Capability | Description |
|---|-----------|------|
| 10 | **TEMPR Multi-Strategy Retrieval** | Semantic embedding + BM25 keywords + time-weighted hybrid ranking + **optional LLM rerank** |
| 11 | **Smart Summary** *(LLM)* | `add_memory` auto-refined by LLM — conversational filler removed, key facts preserved. Falls back to raw text. |
| 12 | **FastEmbed Local Embedding** | Local ONNX vectorization, no API dependency, auto-degrade to n-gram |
| 13 | **SQLite FTS5 + MD5 Dedup** | Full-text index + in-library/batch double dedup |

### 📊 Knowledge Layer (3) *1 LLM-Enhanced*

| # | Capability | Description |
|---|-----------|------|
| 14 | **Knowledge Graph** | Entity-relation extraction (**LLM-enhanced**, falls back to regex) + time-travel snapshots + relation invalidation + full timeline + knowledge distillation |
| 15 | **Workflow Knowledge Base** | Markdown knowledge file indexing + keyword search |
| 16 | **User Profile** | Auto-extract preferences, habits, facts from conversation |

### ⏳ Lifecycle Layer (4) *3 LLM-Enhanced*

| # | Capability | Description |
|---|-----------|------|
| 17 | **Context-Aware Compression + Warning** | Two-tier (70% mild / 85% aggressive), originals preserved in refs/. Auto-detects agent context usage and warns before compression (configurable threshold, bilingual) |
| 18 | **Task Map** | Auto-generated Mermaid task graph on wake — see full progress at a glance |
| 19 | **Forgetting Curve** | Four gates (safety window / access density / scene protection / **LLM semantic review**) + **LLM scene classification** + knowledge distillation |
| 20 | **Memory Merge** | Detect keyword-overlapping related memories + **LLM merged summary**. Originals preserved. |

### 🔄 Learning & Reflection (2)

| # | Capability | Description |
|---|-----------|------|
| 21 | **Learn from Corrections** | Auto-detect correction signals, 3 identical corrections → permanent behavioral rule |
| 22 | **Self-Reflection** | Analyze memory base on startup, discover cross-time associations, contradictions, topic shifts |

### 🔗 Integration Layer (4)

| # | Capability | Description |
|---|-----------|------|
| 23 | **Working Memory** | Independent file, survives context compression |
| 24 | **Cross-Session Bridge** | Conversation summaries auto-synced to prefill + current_context, continuity across sessions |
| 25 | **Auto-Update** | Check GitHub for new versions, in-place update (TOFU checksum), preserves user data and config |
| 26 | **Wake Orchestration** | `moyu_wake`: full module pipeline — check→backup→forget→merge→reflect→context→bridge |

---

## 📁 File Structure

```
moyu_toolkit/
├── agent_memory.py          # Vector memory engine + TEMPR retrieval
├── agent_memory_sqlite.py   # SQLite FTS5 search index
├── active_context.py        # Working memory (compression-surviving)
├── context_manager.py       # Context-aware compression + warning + task map
├── forgetting_curve.py      # Memory lifecycle — four gates + LLM review + knowledge distillation
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
│   ├── forensic_patterns.json # Injection detection rule base (433 patterns + regex)
│   ├── pii_redactor.py      # PII redaction (bilingual, API key support)
│   ├── isolation.py         # User isolation (opt-in)
│   └── encrypt.py           # AES-256-GCM file encryption (opt-in, requires cryptography)
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
- Concerned about **PII leaks** — don't want phone numbers, IDs, API keys lingering in memory files
- Switching between **Hermes, OpenClaw, LangChain, or custom projects**, need a unified memory solution
- Want **zero infrastructure** — no Docker, no databases, no signups

---

## 📜 License

MIT
