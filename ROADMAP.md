# MOYU Roadmap

> **Current version:** v2.4.6
> **Last updated:** 2026-05-19

MOYU is built around a simple philosophy: **make every feature reliable before adding more.** These priorities reflect that.

## Short-term (v2.5.x)

| Priority | Item | Why |
|----------|------|-----|
| 🔴 | **Standard pip package** — Add `pyproject.toml`, publish to PyPI | Current "copy folder" method is manual and error-prone. `pip install moyu` should be the default. |
| 🔴 | **Operation audit log** — ✅ Done in v2.4.6 | Comprehensive audit trail for forget/distill/merge operations. |
| 🟠 | **Memory source tagging** — ✅ Done in v2.4.6 | Distinguish user/agent/system memory sources for smarter lifecycle management. |
| 🟠 | **Contributing guide + Roadmap** — ✅ Done in v2.4.6 | Make it easy for the community to contribute. |
| 🟡 | **LLM ecosystem integration** — LangChain Tool, MCP Server adapters | Let mainstream AI frameworks discover MOYU natively. |

## Medium-term (v2.6.x)

| Priority | Item | Why |
|----------|------|-----|
| 🟠 | **Hot-reloadable pattern library** — Load injection patterns from external files without code changes | Reduces maintenance burden for the 422-pattern forensic rule set. |
| 🟡 | **Performance benchmarks** — Provide benchmark data for different memory scales | Help users understand MOYU's performance profile before deploying. |
| 🟡 | **Enhanced diagnostics** — More status checks (disk space, index health, FTS5 rebuild suggestions) | Improve `moyu status` and `moyu audit` output. |

## Long-term (v3.0+)

| Priority | Item | Why |
|----------|------|-----|
| 🟠 | **Plugin architecture** — Pluggable storage backends (SQLite, Redis), retrieval strategies | Keep the core lightweight while allowing customization. |
| 🟡 | **Versioned memory** — Optional Git-like version history for critical memories | Enable precise rollback on memory poisoning. |

## What we explicitly won't do

These features are out of scope for MOYU's design:

- **Multi-tenant / multi-user** — MOYU is a single-agent tool. Multi-user is a different product.
- **Distributed / clustered deployment** — Requires infrastructure, contradicts zero-infrastructure design.
- **Event sourcing** — Letta-level versioning would make MOYU too heavy.
- **Full semantic injection defense** — Would require LLM-level content moderation, breaking zero-config.

## Prior art & thanks

MOYU's design draws inspiration from:

- [Mem0](https://github.com/mem0ai/mem0) — Enterprise memory layer
- [Letta](https://github.com/letta-ai/letta) — Agent operating system with memory
- [Kioku Lite](https://github.com/kioku-labs/kioku-lite) — Local-first tri-hybrid retrieval
- [Tencent Agent Memory](https://github.com/tencent-ailab/agent-memory) — Task map visualization

MOYU differentiates by being the only purely local, zero-config, self-defending memory toolkit with built-in injection detection, PII redaction, and a full four-layer defense chain.
