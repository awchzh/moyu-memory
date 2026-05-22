# MOYU Roadmap

> **Current version:** v2.6.0
> **Last updated:** 2026-05-22

MOYU is built around a simple philosophy: **make every feature reliable before adding more.** These priorities reflect that.

## What's been delivered

MOYU's last two release cycles shipped:

- **v2.5.x** — 6 LLM-enhanced capabilities (smart summary, search rerank, memory merge, scene classification, KG extraction, forgetting review), security guard overhaul (+38% interception), 513 pattern library, circuit breaker with auto-recovery, CI integration, public benchmark validation (RTPB2026 + Safety-Prompts), pip packaging
- **v2.6.0** — Namespace memory layering (`--ns` search, SQLite sync, auto-tagging), self-evolving security rules (`moyu learn` / `moyu rules`), reproducible security benchmark (`moyu benchmark`), `moyu doctor` / `moyu snapshot` / `moyu demo-attack`, lazy init (install-and-run, no setup), injection mutator (`moyu mutate`)

## Short-term (v2.7.x)

| Priority | Item | Why |
|----------|------|-----|
| 🔴 | **Adaptive retrieval weighting** — Tune BM25/semantic/time weights via weak user feedback signals (click, skip, re-query) | Gets smarter with use instead of staying static. Pure logic, no LLM cost. |
| 🟠 | **Public security benchmarks** — Publish reproducible scores on Gandalf, HackAPrompt, and community injection datasets | Third-party validation builds trust. Current 74.8% needs a public leaderboard. |
| 🟠 | **API reference docs + architecture diagram** — Standalone documentation beyond README | Current README is dense. New users need a structured entry point. |
| 🟡 | **3 ready-to-run integration examples** — LangChain Tool, HTTP server, OpenAI Assistant | Lower the barrier for trying MOYU in different stacks. |

## Medium-term (v2.8.x)

| Priority | Item | Why |
|----------|------|-----|
| 🟠 | **Hot-reloadable pattern library** — Load injection patterns from external files without code changes | Reduces maintenance burden for the 500+ forensic rule set. |
| 🟠 | **Multi-instance memory reconciliation** — Native merge/compare between two MOYU instances | Unique differentiator — no other memory toolkit does peer-to-peer sync. |
| 🟡 | **Prompt-as-memory entry** — `moyu listen <fact>` extracts structured memory from natural language | "Say it and it's saved" — paradigm shift from API-call to conversation. |
| 🟡 | **Performance benchmarks** — Provide benchmark data for different memory scales | Help users understand MOYU's performance profile before deploying. |

## Long-term (v3.0+)

| Priority | Item | Why |
|----------|------|-----|
| 🟠 | **Plugin architecture** — Pluggable storage backends (SQLite, Redis), retrieval strategies | Keep the core lightweight while allowing customization. |
| 🟡 | **Versioned memory** — Optional Git-like version history for critical memories | Enable precise rollback on memory poisoning. |
| 🟡 | **LLM ecosystem native adapters** — LangChain Tool, MCP Server | Let mainstream AI frameworks discover MOYU natively. |

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
- [DeepLearning.AI](https://www.deeplearning.ai/) — Long-Term Agentic Memory with LangGraph course

MOYU differentiates by being the only purely local, zero-config, self-defending memory toolkit with built-in injection detection, PII redaction, and a full four-layer defense chain.
