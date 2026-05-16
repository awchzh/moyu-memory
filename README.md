# MOYU — AI Agent Secure Memory Toolkit

**Your AI remembers everything. But is it safe? Can it survive context compression? Will old memories pile up forever?**

MOYU is a lightweight, zero-trust memory layer for AI Agents. Drop it into any Python project — your Agent gains **secure, self-managing, cross-session memory** in minutes.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Dependencies](https://img.shields.io/badge/dependencies-numpy%20%7C%20requests-green)]()

**No Docker. No database. No registration. No API vendor lock-in. Pure Python, copy & use.**

---

## 🎯 What MOYU is really about

Three things that every other memory solution ignores:

| Your problem | MOYU's answer |
|-------------|---------------|
| **"Is my Agent's memory file being tampered?"** | 🔒 **Defense chain** — password gate + integrity check (SHA256) + forensic analysis + auto-recovery from backup |
| **"My AI's context window is filling up — what do I delete?"** | 🌿 **Lifecycle management** — adaptive compression + forgetting curve (parallel gates) + scene-protected retention |
| **"Can I take this to another project?"** | 📦 **Zero infrastructure** — one folder, `pip install numpy requests`, works with Hermes / OpenClaw / LangChain / custom Python |

MOYU has 15 capabilities (all of them real, all verified working). But these three are what no one else does.

---

## 30-Second Quick Start

```bash
pip install numpy requests pyyaml
```

Copy the `moyu_toolkit/` folder into your project. First search:

```bash
cd moyu_toolkit
python3 moyu.py search "what did we talk about"
```

> **Zero-config mode:** Works immediately with local fallback. When you need better retrieval, install FastEmbed (`pip install fastembed`). No API key required.

```bash
python3 moyu.py help          # Full command reference
python3 moyu.py demo          # See all capabilities in action
python3 moyu.py init          # Initialize integrity protection
```

---

## 📋 Complete Command Reference

All commands through a unified CLI:

```bash
python3 moyu.py <command> [args]
```

### 1️⃣ Defense & Security (MOYU's core differentiator)

| Command | What it does | Why you need it |
|---------|-------------|-----------------|
| `moyu setup` | Set a security password | Dangerous ops need password confirmation |
| `moyu verify <type> [desc]` | Verify a dangerous operation | Blocks memory data corruption before it happens |
| `moyu unlock` | Unlock after 3 failed attempts | Auto-lockout prevents brute force |
| `moyu check` | Check all file integrity (SHA256) | Detects tampering — even data files that change daily are tracked |
| `moyu audit` | Full security audit — all 3 layers | One report: password status + integrity status + recovery readiness |
| `moyu init` | Initialize integrity manifest | First step to enable the defense chain |

**How the defense chain works:**

```
Layer 1 (Pre-operation): password verification → blocks dangerous edits
Layer 2 (On-wake):       integrity check + forensic analysis → detects tampering
Layer 3 (Post-tamper):   auto-recovery from daily backup → restores clean state
```

### 2️⃣ Memory & Semantic Retrieval

| Command | What it does |
|---------|-------------|
| `moyu search <query>` | Search memories using TEMPR multi-strategy (semantic + keyword + time) |
| `moyu stats` | All statistics: memory count, embedding type, source distribution, entities |
| `moyu status` | System status with defense chain visualization |
| `moyu inject` | Get behavioral rules for injection into system prompt |
| `moyu signals` | View active trigger words (learner) |

**Search quality:** Local FastEmbed (BAAI/bge-small-zh-v1.5, 512-dim semantic vector). Falls back gracefully to n-gram + BM25 when FastEmbed is not installed. Never breaks.

### 3️⃣ Lifecycle & Compression (auto-context management)

| Command | What it does |
|---------|-------------|
| `moyu compress` | Show compression status and context usage |
| `moyu compress --now` | Force manual compression (requires password) |
| `moyu compress config` | Show compression parameters |
| `moyu compress set <k> <v>` | Adjust thresholds (mild_threshold, auto_threshold, etc.) |
| `moyu context` | One-line context usage percentage |
| `moyu forget` | Show forgetting curve status (two-stage gating, density analysis) |
| `moyu forget config` | Show forgetting curve parameters |
| `moyu forget set <k> <v>` | Adjust: `demote_days`, `archive_days`, `density_window`, `enabled` |
| `moyu forget --summary` | One-line memory lifecycle summary |
| `moyu forget history` | What was demoted, what was kept, and why |
| `moyu ref <name>` | Read original content of a compressed memory |
| `moyu ref list` | List all available refs |

**How the forgetting curve works (parallel gating — OR logic):**

- **Safety window** (default 14 days): nothing demoted before this
- **Access density**: frequently-used topics survive longer
- **Scene protection**: related memories protect each other, even past the window
- All parameters adjustable. Runs automatically every 2 hours via cron.

### 4️⃣ Learning & Reflection (get better from interaction)

| Command | What it does |
|---------|-------------|
| `moyu learn <text>` | Learn from a user correction (extracts pattern after 3 repeats) |
| `moyu detect <text>` | Detect correction signals in text ("no/don't/remember") |
| `moyu reflect` | Run self-reflection (cross-time connections, contradictions) |

### 5️⃣ Knowledge Base & Graph

| Command | What it does |
|---------|-------------|
| `moyu kb list` | List all knowledge files |
| `moyu kb search <query>` | Search knowledge files |
| `moyu kb index` | Rebuild keyword index |
| `moyu kb read <file>` | Read a knowledge file |
| `moyu kg search <entity>` | Search knowledge graph for entities and relations |

### 6️⃣ Session & Maintenance

| Command | What it does |
|---------|-------------|
| `moyu bridge` | Show session bridge status |
| `moyu update` | Check for GitHub updates |
| `moyu update now` | Download and apply update (requires password) |
| `moyu demo` | Interactive demo of all capabilities |

---

## 🔬 15 Capabilities — Full Details

### 🛡️ Defense Layer (3 capabilities)

| # | Capability | What it does |
|---|-----------|-------------|
| 1 | **Memory Self-Defense** | Prevents dangerous operations before they reach memory files. Password verification + auto-lockout + audit trail |
| 2 | **Integrity Check & Recovery** | SHA256 manifest on wake + daily backups (3 days). Detects tampering — including data file changes |
| 3 | **Forensic Analysis** | Analyzes what changed and why. Detects instruction override patterns, prompt injection, JSON corruption |

### 🧠 Memory Layer (8 capabilities)

| # | Capability | What it does |
|---|-----------|-------------|
| 4 | **TEMPR Semantic Retrieval** | Multi-strategy: FastEmbed semantic + BM25 keyword + time-weighted recency. Hybrid score_and_rank fusion |
| 5 | **Working Memory** | Survives context compression — remembers the current task. Separate file, auto-injected |
| 6 | **Knowledge Graph** | Auto-extracts entities & relations from memory. Local regex (no API key) or semantic (with API key) |
| 7 | **User Profile** | Auto-extracts preferences, habits, facts from interaction |
| 8 | **Deduplication** | SHA256 hash prevents duplicates |
| 9 | **Context-Aware Compression** | Two-tier graduated compression (mild at 70%+, aggressive at 85%+). Original content preserved in refs/ |
| 10 | **Forgetting Curve** | Parallel gating: safety window OR access density OR scene protection. Prevents context saturation without losing important memories |
| 11 | **Memory Merge** | Detects related memories by keyword overlap and merges them. Originals preserved in expandable field |

### 🔄 Learning Layer (2 capabilities)

| # | Capability | What it does |
|---|-----------|-------------|
| 12 | **Learn from Corrections** | Auto-detects correction signals. Learns lessons after 3 repeats. Produces injectable behavioral rules |
| 13 | **Self-Reflection** | Analyzes old memories on wake. Finds cross-time connections, contradictions, topic shifts |

### 🔗 Integration Layer (2 capabilities)

| # | Capability | What it does |
|---|-----------|-------------|
| 14 | **Cross-Session Bridge** | Carries context across sessions. `prefill.json` auto-syncs to system prompt. Every round logged |
| 15 | **Auto-Update** | Checks GitHub for new releases. Applies in-place without touching memory_data or config |

---

## 🏆 What makes MOYU different

| | Hermes/OpenClaw (built-in) | Mem0 | **MOYU** |
|--|---------------------------|------|----------|
| Storage | Plain text files | Vector DB (SQLite/Faiss) | **JSON + SQLite FTS5** |
| Search | Full text dump | Semantic (API/LLM) | **TEMPR triple strategy** |
| Security | ❌ None | ❌ None | **✅ 3-layer defense chain** |
| Lifecycle | ❌ None | ❌ None | **✅ Forgetting curve + compression** |
| Working memory | ❌ None | ❌ None | **✅ Separate file, survives compression** |
| Cross-session carry | Manual only | ❌ None | **✅ Auto-sync prefill.json** |
| Platform lock-in | Tied to platform | Tied to SDK | **✅ Zero binding** |
| API lock-in | Fixed provider | OpenAI only | **✅ Hot-swappable** |
| Setup time | Out of box | 5 min + API key | **pip install, 30 seconds** |
| Offline mode | Partial | Requires API key | **✅ Full local fallback** |

---

## 🎮 When to use MOYU

- **You want your AI Agent to remember things across conversations** — and you want it to be secure
- **You keep hitting context limits** — and you need automatic compression that doesn't lose important memories
- **You're switching between Hermes, OpenClaw, LangChain, or custom code** — and you want one memory solution for all
- **You want zero infrastructure** — no Docker, no database, no registration

---

## 📁 File Structure

```
moyu_toolkit/
├── agent_memory.py          # Vector memory engine + TEMPR retrieval
├── agent_memory_sqlite.py   # SQLite FTS5 search index
├── active_context.py        # Working memory (survives compression)
├── context_manager.py       # Context-aware compression
├── forgetting_curve.py      # Memory lifecycle — two-stage gating
├── memory_merge.py          # Topic-aware memory merge
├── knowledge_graph.py       # Entity-relation knowledge graph
├── knowledge_base.py        # Workflow knowledge base
├── learner.py               # Learn from user corrections
├── self_reflection.py       # Cross-time analysis
├── security.py              # Memory self-defense — password + lockout
├── session_bridge.py        # Cross-session carryover
├── moyu.py                  # Unified CLI entry point
├── moyu_wake.py             # Wake-up integration flow
├── moyu_demo.py             # Interactive demo
├── updater.py               # Auto-update
├── defense_toolkit/
│   └── integrity_checker.py # File integrity + auto recovery
├── config.yaml              # API keys & settings
└── requirements.txt
```

---

## 🚀 Getting Started

```bash
# Install dependencies
pip install numpy requests pyyaml

# Optional — enables true semantic search
pip install fastembed

# Run your first search
cd moyu_toolkit
python3 moyu.py search "your first query"

# Secure your memory
python3 moyu.py init
python3 moyu.py setup
```

---

## 📜 License

MIT
