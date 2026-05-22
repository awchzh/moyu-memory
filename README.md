
**Your AI remembers every conversation. But:**

- **Is someone writing garbage into your memory?**
- **Did that private info you discussed yesterday leak into a file?**
- **Context window full — will you lose what matters?**

MOYU is a **security-first memory layer** for AI Agents. Pure Python, zero external dependencies at the storage layer — one folder, plug and play. LLM-enhanced features are **on by default**; no API key? Silent degrade, core memory keeps working.

### Why MOYU

- **🛡️ Security built in** — Injection detection, PII redaction, file integrity verification, write burst protection — security gaps other memory tools leave open, MOYU handles by default
- **🧠 Install and use** — `pip install moyu-memory` → `moyu search "what did we talk about"`. No Docker, no database, no API key required for core memory
- **🔄 Teach it on the fly** — Spot an attack that slipped through? Tell it once. Takes effect immediately. No release cycle

### Who is it for

| You | Why MOYU |
|-----|----------|
| **Local Agent user (Claude Code, Codex, OpenAI Assistant)** | Your agent needs persistent memory with real security |
| **AI app developer** | Add memory to your product without leaking user privacy |
| **Enterprise deployment** | Zero-trust, zero external deps (storage layer), third-party audited |
| **Anyone who doesn't want API lock-in** | Fully local, your data stays on your machine |

**v2.6.0** — Memory layering + self-evolving security rules + reproducible benchmark. Now available via `pip install moyu-memory`.

[![Tests](https://github.com/awchzh/moyu-memory/actions/workflows/test.yml/badge.svg)](https://github.com/awchzh/moyu-memory/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/moyu-memory)](https://pypi.org/project/moyu-memory/)
[![Python](https://img.shields.io/badge/python-%3E%3D3.8-blue)](https://pypi.org/project/moyu-memory/)
[![License](https://img.shields.io/github/license/awchzh/moyu-memory)](LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/moyu-memory)](https://pypi.org/project/moyu-memory/)

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
| 🟢 | Script-kiddie injection (known patterns) | **~70%** | Content gate (513 patterns, 17 categories, regex combos) + loop detection |
| 🟡 | Simple prompt injection (standard variants) | **~65%** | Regex covers (forget|ignore|skip)×(previous|all|your)×(instructions|rules) + extended CN/EN variants |
| 🟠 | Professional adversarial injection (targeted bypass) | **~25%** | Keyword-based gates + pattern library expanded 20% since v2.5.1, but novel variants remain challenging |
| 🟠 | Semantic-level injection (metaphor, abstraction, no keywords) | **~60%** | LLM Security Guard detects semantic bypasses — regex-untouched patterns like "pretend to be DAN" are caught. Uses your configured LLM. Falls back to safe on API failure: **never blocks legitimate writes.** |
| 🟢 | **Combined defense (all layers)** | **reproducible** | Validated on 1,769 test cases across 15 attack categories. Run `moyu benchmark --full` to reproduce. 0% false positive rate. |

**How it works:** LLM Guard is a second layer after regex — regex untouched → LLM verdict. No API key? Silent degrade to regex-only. This means semantic injection coverage goes from ~0% to ~60% without breaking zero-config.

**MOYU's strength is in the combination:** content gate + LLM guard + PII redaction + write burst guard + forensic analysis + password gate + integrity check + auto-restore + loop detection — unique layers no other memory toolkit offers.

**Additional opt-in:** user isolation (per-directory storage) & AES-256-GCM file encryption (requires `cryptography`). Not in default config — add to `config.yaml` to enable:

```yaml
security:
  isolation:
    enabled: true
    user_id: "your-username"   # separate storage per user
  encryption:
    enabled: true               # AES-256-GCM file encryption
```

Encryption also requires `MOYU_ENCRYPTION_PASSWORD` environment variable.

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
| `moyu forget` | View forgetting curve status (4-gate + LLM review + distillation stats) |
| `moyu forget config` | View forgetting curve parameters |
| `moyu forget set <key> <value>` | Adjust forgetting parameters (demote_days, archive_days, etc.) |
| `moyu ref <name>` | Read original content of a compressed memory |
| `moyu ref list` | List all compressed memory references |

Forgetting curve + knowledge distillation:
- **Four gates** (OR logic): Safety window (14 days) → Access density analysis → Scene association protection → **LLM semantic importance review**
- **Distillation**: Entity relations auto-extracted to knowledge graph before demotion — structural knowledge survives when raw memory is cleared
- **Task map**: Auto-generated Mermaid task graph on wake — agent sees the big picture at a glance

> **🧠 Context warning:** MOYU auto-detects your running agent (Hermes, Claude Code, OpenClaw, Cursor, Continue), reads its real-time context usage, and injects a warning into behavior rules before compression kicks in.
>
> ```bash
> # Quick check
> python3 moyu.py context
> # → Hermes窗口: 85% (累计120,456/128,000, 45次调用) ⚠️ 已深度压缩
>
> # Configure
> moyu compress set warn_threshold 0.6    # warn at 60% (default: 0.7)
> moyu compress set warn_language zh       # Chinese warning
> moyu compress config                     # view all parameters
> ```
>
> **Can't detect your agent?** Run `moyu compress diagnose` for a per-agent path scan, or set `MOYU_FORCE_PROVIDER` / `MOYU_PROVIDER_PATH` to bypass auto-detection.

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

## 🔬 Capabilities by Layer

### 🛡️ Defense Layer (9)

| # | Capability | Description |
|---|-----------|------|
| 1 | **Content Security Gate** | Blocks injection attacks before writing (injection patterns + regex combos, 8 categories) |
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
| 1 | **TEMPR Multi-Strategy Retrieval** | Semantic embedding + BM25 keywords + time-weighted hybrid ranking + **optional LLM rerank** |
| 2 | **Smart Summary** *(LLM)* | `add_memory` auto-refined by LLM — conversational filler removed, key facts preserved. Falls back to raw text. |
| 3 | **FastEmbed Local Embedding** | Local ONNX vectorization, no API dependency, auto-degrade to n-gram |
| 4 | **SQLite FTS5 + MD5 Dedup** | Full-text index + in-library/batch double dedup |

### 📊 Knowledge Layer (3) *1 LLM-Enhanced*

| # | Capability | Description |
|---|-----------|------|
| 1 | **Knowledge Graph** | Entity-relation extraction (**LLM-enhanced**, falls back to regex) + time-travel snapshots + relation invalidation + full timeline + knowledge distillation |
| 2 | **Workflow Knowledge Base** | Markdown knowledge file indexing + keyword search |
| 3 | **User Profile** | Auto-extract preferences, habits, facts from conversation |

### ⏳ Lifecycle Layer (4) *3 LLM-Enhanced*

| # | Capability | Description |
|---|-----------|------|
| 1 | **Context-Aware Compression + Warning** | Two-tier (70% mild / 85% aggressive), originals preserved in refs/. Auto-detects agent context usage and warns before compression (configurable threshold, bilingual) |
| 2 | **Task Map** | Auto-generated Mermaid task graph on wake — see full progress at a glance |
| 3 | **Forgetting Curve** | Four gates (safety window / access density / scene protection / **LLM semantic review**) + **LLM scene classification** + knowledge distillation |
| 4 | **Memory Merge** | Detect keyword-overlapping related memories + **LLM merged summary**. Originals preserved. |

### 🔄 Learning & Reflection (2)

| # | Capability | Description |
|---|-----------|------|
| 1 | **Learn from Corrections** | Auto-detect correction signals, 3 identical corrections → permanent behavioral rule |
| 2 | **Self-Reflection** | Analyze memory base on startup, discover cross-time associations, contradictions, topic shifts |

### 🔗 Integration Layer (4)

| # | Capability | Description |
|---|-----------|------|
| 1 | **Working Memory** | Independent file, survives context compression |
| 2 | **Cross-Session Bridge** | Conversation summaries auto-synced to prefill + current_context, continuity across sessions |
| 3 | **Auto-Update** | Check GitHub for new versions, in-place update (TOFU checksum), preserves user data and config |
| 4 | **Wake Orchestration** | `moyu_wake`: full module pipeline — check→backup→forget→merge→reflect→context→bridge |

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
│   ├── forensic_patterns.json # Injection detection rule base (patterns + regex)
│   ├── pii_redactor.py      # PII redaction (bilingual, API key support)
│   ├── isolation.py         # User isolation (opt-in)
│   └── encrypt.py           # AES-256-GCM file encryption (opt-in, requires cryptography)
├── tests/
│   └── test_all.py          # Automated tests (26 items)
├── config.yaml              # API keys & settings
└── requirements.txt
```

---

## 🏆 Comparison (Honest)

| Dimension | MOYU | Mem0 | Letta | Zep | Cognee |
|------|------|------|-------|-----|--------|
| Setup | **Minimal: pip, zero config** | Low: pip + API Key | Medium: needs runtime setup | Medium: cloud simple, self-host complex | Low: uv pip install |
| External deps | **Zero: no DB/API/Docker** | LLM API + vector DB | LLM API + storage | Cloud dep strong; self-host needs graph DB | LLM API |
| Security | **Best: injection defense/PII redaction/integrity check/zero-trust** | Medium: API Key + compliance | Basic: framework isolation | Medium: cloud SOC2/HIPAA | Basic: tenant isolation |
| Retrieval | Semantic+BM25+time+**LLM rerank** | Semantic+BM25+entity (3-way fusion) | Agent tool-call pagination | **Temporal graph retrieval** + validity window | Graph+vector hybrid |
| Lifecycle | **Most complete: compression/forgetting review/merge/scene class, fully auto** | ADD-only, no active forgetting | 3-tier memory, auto pagination | Temporal graph auto version tracking | Feedback learning, needs config |
| Knowledge Graph | Entity extraction+time-travel+distillation | Pro only ($249/mo) | Indirect (external tools) | **Temporal graph, all tiers** | **Core feature, full OSS** |
| Cross-session | Auto prefill sync | **3-tier isolation (user/session/agent)** | Native (stateful runtime) | Temporal graph natural continuity | Cross-agent sharing |
| Offline | **Fully offline, zero network** | Partial (self-host + local embed) | Self-hostable | Self-host only | Fully local |
| Platform lock-in | **Minimal: pure Python, any framework** | Low: OSS, multi-language SDK | Medium: requires Letta framework | Medium: cloud has lock-in | Low: Python only |

**Bottom line:** MOYU excels at security, offline capability, and lifecycle management — areas where alternatives offer little to none. Mem0 brings the richest ecosystem, Zep leads in temporal graph reasoning, and Cognee offers the most complete open-source knowledge graph. Choose by your scenario, not by feature count.

---

## 🎮 Use Cases

- Want your AI Agent to **remember cross-session conversations** with real security
- Frequently hit **context limits**, need auto-compression without losing important memories
- Concerned about **PII leaks** — don't want phone numbers, IDs, API keys lingering in memory files
- Switching between **Hermes, OpenClaw, LangChain, or custom projects**, need a unified memory solution
- Want **zero infrastructure** — no Docker, no databases, no signups

---

## 🔒 Third-Party Security Audit

MOYU has passed security reviews from two Tencent Cloud security labs:

| Auditor | Result | Report |
|---------|--------|--------|
| **Keen Lab** (Tencent) | ✅ Benign — no malicious code detected | [View Report](https://tix.qq.com/search/skill?keyword=0f86b9542efec19edf776812f7e82855) |
| **Cloud Security Lab** (Tencent) | ✅ Benign — no malicious code detected | [View Report](https://static.cloudsec.tencent.com/html-report-v2/2026/05/21/383126_6444e76133d8be0b8eb3493110694b1f.html) |

These audits are conducted by third-party security vendors on behalf of [SkillHub](https://skillhub.cn/skills/moyu), covering static analysis, behavioral analysis, and code review.

---

## 📜 License

MIT
