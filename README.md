# MOYU — AI Agent Secure Memory Toolkit

**Zero-trust memory infrastructure for your AI Agent. Auditable, recoverable, self-defending memory. No Docker, no database, no registration — pure Python, copy & use.**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Dependencies](https://img.shields.io/badge/dependencies-numpy%20%7C%20requests-green)]()

MOYU is a lightweight, platform-agnostic memory layer for AI Agents. Drop it into Hermes, OpenClaw, LangChain, AutoGen, or your own Python project — your Agent gains **persistent cross-session memory** instantly.

---

## Quick Start

```bash
pip install numpy requests pyyaml
```

Copy the `moyu_toolkit/` folder into your project. Run your first memory search:

```bash
cd moyu_toolkit
python3 agent_memory.py search "what did we talk about"
```

> **Zero-config mode:** Works immediately with local fallback. Add your API key in `config.yaml` when you want semantic search.

**One command to rule them all:**

```
moyu_toolkit/moyu.py help
```

## Command Reference

All commands are available through the unified CLI:

```bash
cd moyu_toolkit && python3 moyu.py <command> [args]
```

### 🛡️ Security

| Command | Description |
|---------|-------------|
| `moyu setup` | Set a security password (dangerous operations need password confirmation) |
| `moyu verify <type> [desc]` | Verify a dangerous operation (delete, modify config, etc.) |
| `moyu unlock` | Unlock the security system (locked after 3 failed attempts) |
| `moyu check` | Check memory file integrity (SHA256 comparison) |
| `moyu audit` | Full security audit — all three defense layers at a glance |
| `moyu init` | Initialize integrity verification manifest |

### 🧠 Memory & Retrieval

| Command | Description |
|---------|-------------|
| `moyu search <query>` | Search memories using TEMPR multi-strategy retrieval |
| `moyu stats` | Show all statistics (memory, context, learner, security) |
| `moyu status` | System status with defense chain visualization |
| `moyu inject` | Get behavioral rules for injection into system prompt |
| `moyu signals` | View active trigger words (learner) |

### ⏳ Lifecycle & Compression

| Command | Description |
|---------|-------------|
| `moyu forget` | Show forgetting curve status (two-stage gating, density analysis) |
| `moyu forget config` | Show current forgetting curve parameters |
| `moyu forget set <key> <val>` | Set: `demote_days`, `archive_days`, `density_window`, `enabled` |
| `moyu forget --summary` | One-line summary of memory lifecycle |
| `moyu forget history` | Show demotion/retention history with reasons |
| `moyu compress` | Show compression status and context usage |
| `moyu compress --now` | Force manual compression |
| `moyu context` | Show context usage percentage in one line |

### 🔄 Learning & Reflection

| Command | Description |
|---------|-------------|
| `moyu learn <text>` | Learn from a user correction |
| `moyu detect <text>` | Detect correction signals in text |
| `moyu reflect` | Run self-reflection (analyze connections & contradictions) |

### 📚 Knowledge Base

| Command | Description |
|---------|-------------|
| `moyu kb list` | List all knowledge files |
| `moyu kb search <query>` | Search knowledge files |
| `moyu kb index` | Rebuild keyword index |
| `moyu kb read <file>` | Read a knowledge file |
| `moyu kg search <entity>` | Search knowledge graph for entities and relations |

### 🔗 Session & Updates

| Command | Description |
|---------|-------------|
| `moyu bridge` | Show session bridge status |
| `moyu update` | Check for updates on GitHub |
| `moyu update now` | Download and apply the latest update |

### 🎭 Demo

| Command | Description |
|---------|-------------|
| `moyu demo` | Show all 15 capabilities with examples |


## File Structure

## 15 Capabilities — Grouped by Domain

### 📦 Memory Layer — Store & Find

| # | Capability | What it does |
|---|-----------|-------------|
| 1️⃣ | **TEMPR Multi-Strategy Retrieval** | Semantic + BM25 + time-weighted — always finds what you need |
| 2️⃣ | **Working Memory** | Survives context compression — remembers current task. Built-in workflow knowledge base — tell your AI "remember this" and completed workflows auto-save as markdown. Retrieve with `moyu kb search`, or let your AI's system prompt trigger auto-lookup |
| 3️⃣ | **Knowledge Graph** | Auto-extracts entities & relations. Local regex mode (no API key needed), upgrades to semantic deep extraction with API key |
| 4️⃣ | **User Profile** | Auto-extracts preferences, habits, facts. Local regex mode (no API key needed), upgrades to semantic deep extraction with API key |
| 5️⃣ | **Deduplication** | SHA256 hash — same content never stored twice |

### 🧠 Learning Layer — Improve From Interaction

| # | Capability | What it does |
|---|-----------|-------------|
| 6️⃣ | **Learn from Corrections** | Auto-detects correction signals ("no/don't/remember") on any MOYU command — learns lessons after pattern repeats 3 times. `moyu learn` for manual trigger. |
| 7️⃣ | **Self-Reflection** | Analyzes old memories on wake — finds connections & contradictions |

### 🛡️ Defense Layer — Protect & Verify

| # | Capability | What it does |
|---|-----------|-------------|
| 8️⃣ | **Integrity Verification** | Detects memory file tampering on wake |
| 9️⃣ | **Integrity Check & Recovery** | Run `moyu check` to verify file integrity. On pass, auto-saves daily backup (keeps 3 days). Recover from any clean backup if tampered. |
| 🔟 | **Forensic Analysis** | Analyzes what changed and how — instruction override, prompt injection detection |
| 1️⃣1️⃣ | **Memory Self-Defense** | First line of defense — prevents dangerous operations before they reach your memory files. Password verification, auto-lockout, audit trail. |

### 🌿 Lifecycle Layer — Let Memory Breathe (V2.0)

| # | Capability | What it does |
|---|-----------|-------------|
| 1️⃣2️⃣ | **Context-Aware Compression** | Two-tier graduated compression: mild (70%+) truncates long memories, auto (85%+) aggressively demotes non-critical items. Compression preserves traceability — original content saved to `refs/` before truncation, retrievable via `moyu ref <name>`. Manual trigger (`moyu compress --now`), status (`moyu compress`), and parameter adjustment (`moyu compress config` / `moyu compress set`) all available. |
| 1️⃣3️⃣ | **Forgetting Curve** | Parallel gating (OR): 14-day safety window OR access density trend OR scene association protection. Frequently used topics protect related memories from being forgotten, even past the window. All parameters adjustable via `moyu forget config` and `moyu forget set`. Forgetting visibility via `moyu forget history`. |
| 1️⃣4️⃣ | **Memory Merge** | Detects related memories by keyword overlap and merges them into a single composite entry. Original details are preserved in an expandable field — nothing is lost. |
| 1️⃣5️⃣ | **Self-Update** | Checks GitHub for new releases and updates the toolkit in place — preserving memory_data and user config. `moyu update` to check, `moyu update now` to apply. |

---

## Comparison

| | Built-in (Hermes/OpenClaw) | **MOYU** |
|--|---------------------------|----------|
| Storage | Plain text files | Vector index (1536-dim semantic) |
| Retrieval | Full text dump | **TEMPR triple strategy** |
| Working memory | ❌ None | **✅ Separate file, survives compression** |
| Knowledge graph | ❌ None | **✅ JSON-based, zero ops** |
| Self-reflection | ❌ None | **✅ Automatic** |
| User profile | ❌ Manual only | **✅ Auto-extraction** |
| Learn from corrections | ❌ None | **✅ Auto-detect & accumulate** |
| Integrity check | ❌ None | **✅ manifest + SHA256** |
| Auto recovery | ❌ None | **✅ `moyu check` manual verify / auto backup last 3 days** |
| Forensic analysis | ❌ None | **✅ Tamper source analysis** |
| Memory self-defense | ❌ None | **✅ Pre-verification, blocks before damage** |
| Context-aware compression | ❌ None | **✅ Auto at 90%, manual trigger** |
| Forgetting curve | ❌ None | **✅ Pressure-driven lifecycle** |
| Memory merge | ❌ None | **✅ Keyword overlap merge** |
| Self-update | ❌ None | **✅ GitHub one-click update** |
| API switching | Fixed | **✅ Hot-swappable** |
| Platform dependency | Tied to platform | **✅ Zero binding** |
| Setup time | Out of box | **pip install, 5min** |

---

## Why MOYU

- **No platform lock-in** — Hermes, OpenClaw, LangChain, or custom Python
- **No API vendor lock-in** — DeepSeek, OpenAI, MiniMax, Doubao — switch freely
- **Zero risk sidecar** — doesn't touch your existing memory files
- **Zero barrier** — no Docker, no database, no registration required
- **Pure Python, 4 core files, fully hackable**

---

## File Structure

```
moyu_toolkit/
├── agent_memory.py          # Vector memory + TEMPR retrieval
├── active_context.py         # Working memory (survives compression)
├── knowledge_graph.py        # Entity-relation graph
├── learner.py                # Learn from user corrections
├── security.py               # Memory self-defense — first line of defense
├── self_reflection.py        # Self-Reflection — analyzes connections & contradictions on wake (V2.0.3)
├── knowledge_base.py         # Workflow knowledge base — searchable recipe book (V2.0.3)
├── moyu.py                    # Unified CLI entry point
├── context_manager.py         # Context-aware compression (V2.0)
├── forgetting_curve.py        # Memory lifecycle — two-stage gating (V2.0.5)
├── memory_merge.py            # Topic-aware memory merge (V2.0)
├── session_bridge.py          # Cross-session carryover (V2.0)
├── updater.py                 # Self-update (V2.0)
├── moyu_wake.py               # Wake-up integration flow (V2.0)
├── defense_toolkit/
│   └── integrity_checker.py  # File integrity + auto recovery
├── config.yaml               # API keys & settings (fill in yours)
└── requirements.txt
```

---

## License

MIT
