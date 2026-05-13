# MOYU — AI Agent Memory Toolkit

**15 memory capabilities for your AI Agent. Remember who you are across conversations. No code rewrite required.**

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

```bash
python3 moyu_toolkit/moyu.py --help
```

All MOYU capabilities available from a single entry point — search, stats, setup, demo, and more.

**(Optional) Memory Self-Defense — prevent accidental deletion & tampering before they happen:

```bash
cd moyu_toolkit && python3 security.py setup
```

This is your memory's first line of defense. Unlike Integrity Check + Auto Recovery (which detect tampering after the fact), Memory Self-Defense stops dangerous operations **before** they reach your memory files. Set a password — operations that could delete or corrupt your memory (file deletion, config changes, external scripts) will require verification. Accidental `rm` by users or misbehaving agents? Blocked. [Learn more →](moyu_toolkit/security.py)

---

## 15 Capabilities — Grouped by Domain

### 📦 Memory Layer — Store & Find

| # | Capability | What it does |
|---|-----------|-------------|
| 1️⃣ | **TEMPR Multi-Strategy Retrieval** | Semantic + BM25 + time-weighted — always finds what you need |
| 2️⃣ | **Working Memory** | Survives context compression — remembers current task |
| 3️⃣ | **Knowledge Graph** | Auto-extracts entities & relations from conversation (JSON, no database) |
| 4️⃣ | **User Profile** | Auto-extracts user preferences, habits, facts from conversation |
| 5️⃣ | **Deduplication** | SHA256 hash — same content never stored twice |

### 🧠 Learning Layer — Improve From Interaction

| # | Capability | What it does |
|---|-----------|-------------|
| 6️⃣ | **Learn from Corrections** | Detects "no/don't/remember" signals — learns lessons after 3 same mistakes |
| 7️⃣ | **Self-Reflection** | Analyzes old memories on wake — finds connections & contradictions |

### 🛡️ Defense Layer — Protect & Verify

| # | Capability | What it does |
|---|-----------|-------------|
| 8️⃣ | **Integrity Verification** | Detects memory file tampering on wake |
| 9️⃣ | **Auto Recovery** | Automatically restores from backup when tampering detected |
| 🔟 | **Forensic Analysis** | Analyzes what changed and how — instruction override, prompt injection detection |
| 1️⃣1️⃣ | **Memory Self-Defense** | First line of defense — prevents dangerous operations before they reach your memory files. Password verification, auto-lockout, audit trail. |

### 🌿 Lifecycle Layer — Let Memory Breathe (V2.0)

| # | Capability | What it does |
|---|-----------|-------------|
| 1️⃣2️⃣ | **Context-Aware Compression** | Auto-detects context occupancy. At 80% warns the user. At 90% silently compresses — defers low-priority items, truncates long memories, saves tokens. Manual trigger also available (`moyu compress --now`). |
| 1️⃣3️⃣ | **Forgetting Curve** | Automatically demotes memories not accessed for 14 days — but ONLY when context is under pressure (low-frequency users keep everything). Demoted memories skip automatic injection but remain searchable. Re-accessing restores them. |
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
| Auto recovery | ❌ None | **✅ From backup** |
| Forensic analysis | ❌ None | **✅ Tamper source analysis** |
| Memory self-defense | ❌ None | **✅ Pre-verification, blocks before damage** |
| Context-aware compression | ❌ None | **✅ Auto at 90%, warns at 80%, manual trigger** |
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
├── moyu.py                    # Unified CLI entry point
├── context_manager.py         # Context-aware compression (V2.0)
├── forgetting_curve.py        # Memory lifecycle demotion (V2.0)
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
