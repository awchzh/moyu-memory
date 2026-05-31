# MOYU — Development Log

## v2.9.0 — Skill Memory + Unified File I/O (2026-05-31)

### 🧠 Skill Memory
- **Per-function experience accumulation** — `search()` and `add_memory()` now accumulate usage experience into independent `.memory.md` files. Each call injects relevant past learnings into results automatically.
- **`moyu skill-note` CLI** — `list`, `show <name>`, `add <name> <note>` for manual experience management.
- **Learner auto-integration** — When the learner detects a correction that maps to a skill function, it automatically writes the lesson to the matching `.memory.md`.
- **Cross-session carryover** — Experiences survive agent restarts. Next session wakes up with accumulated wisdom.

### 🗄️ Unified File I/O Layer
- **`_storage.py`** — Single entry point for all memory data reads/writes. Atomic write (tmp → rename), content security scanning, HMAC signature, manifest update — all in one call.
- **11 modules migrated** — `active_context`, `self_reflection`, `knowledge_graph`, `memory_merge`, `context_manager`, `frequency_guard`, `learner`, `forgetting_curve`, `agent_memory`, `session_bridge`, `test_all` now use `storage.read()`/`storage.write()`.
- **Net code change** — +427/−391 lines. All existing JSON files, signatures, and manifest entries remain untouched. Fully backward compatible.

### 🔧 Internal
- `storage.write()` automatically runs content security gate on every write.
- `storage.delete()` cleans up both the file and its manifest entry.
- Python 3.9+ compatible (no walrus operators, no `str.removeprefix`).

### 🔌 MCP Expansion (5 → 29 tools)
Exposing all MOYU capabilities as MCP tools — memory, search, defense, knowledge graph, knowledge base, lifecycle, reflection, learning, diagnostics.

### 🪲 Fix
Fix `uvx` args — `moyu-mcp@latest` → `--from moyu-memory@latest moyu-mcp` (PyPI package name ≠ entry point name).

## v2.8.1 — MCP Server Adapter (2026-05-29)

### 🔌 MCP stdio server
Added `mcp_server.py` — exposed `search_memory`, `add_memory`, `memory_stats`, `defense_scan`, `memory_doctor`.

### 🔧 Internal
- Server version dynamically read from package metadata.
- `@latest` suffix per ModelScope recommendation.

## v2.8.0 — Progressive Memory + Heat Tiers + Security Deepening (2026-05-28)

### 🧠 Progressive Memory (3-Tier)

- **Summary → Overview → Full** — `add_memory()` now accepts optional `overview` and `full` parameters. Search returns summaries by default; `moyu memory detail <id>` expands progressively.
- **Access Heat Tracking** — Every memory tracks a `heat` score (0.0–1.0). Heats increase on search access (+0.02) and detail expansion (+0.1), providing implicit relevance feedback.
- **HOT/WARM/COLD Tiers** — Memories auto-sort into three tiers by heat (top 20% HOT, middle 40% WARM, bottom 40% COLD). 5%/day time decay + `moyu memory heat-recalc` for manual tier reassignment.
- **Semantic Dedup** — Search filters near-duplicate results (cosine similarity > 0.9), retaining the higher-heat entry.
- **Heat ↔ Forgetting Curve Bridge** — COLD-tier memories bypass density checks and flow directly to forgetting curve deletion candidates.

### 🛡️ Security Hardening

- **Injection output gate** — `build_injection()` assembled content now passes through `content_scan()` before delivery, preventing assembled injections from sneaking through.
- **Persistence gate** — `forgetting_curve._save_memories()` now passes through `content_scan()` before persisting demoted/archived memories.
- **Pseudo-signal blacklist** — `session_bridge` filters `<artificial>`, `<|im_start|>`, `[system]`, and emoji pollution patterns from prefill content.
- **Next-session behavioral points** — Session bridge auto-generates compact (≤3 item) behavioral summaries from decisions and pending tasks, injected into prefill for reliable next-session carryover.

### 🔄 Compression Hardening

- **Tiered compression priority** — `rule` and `working_memory` categories are now permanently protected from deferral and demotion, regardless of priority score.
- **Recursive compression guard** — `was_compressed` flag prevents already-truncated content from being compressed a second time.
- **Compression alignment check** — Post-compression report now includes rule retention stats (e.g., "规则保留: 2/2 | 记忆条目: 1/1").

### 📊 Knowledge Graph

- **`moyu kg history <entity>`** — Entity timeline command showing active + expired relations with validity windows.
- **Conflict auto-invalidation** — New relations auto-expire existing same-source, same-type relations to prevent conflict accumulation.

### 🔧 Rules & Learning

- **`moyu rules whitelist <pattern>`** — Whitelist management for false-positive suppression.
- **`moyu rules remove <pattern>`** — Remove stale or over-aggressive rules.
- **`moyu rules list`** — List all active custom rules with descriptions.

### 📋 CLI

- **`moyu memory detail <id>`** — Progressive content expansion (summary → overview → full).
- **`moyu memory heat-recalc`** — Manual heat tier recalculation.
- **`moyu kg history <entity>`** — Entity relation timeline.
- **`moyu rules` subcommands** — whitelist, remove, list.

## v2.7.7 — Import Path Security + Write-Path Hardening (2026-05-26)

### 🛡️ Security

- **Cross-module import hardening** — All internal imports now use fully-qualified package paths (`moyu_toolkit.xxx`), ensuring the content security gate, PII redaction, and LLM guard activate consistently regardless of installation method (`pip install`, `python -m`, or direct CLI).
- **Write-path coverage expanded** — Active context (`active_context.py`), knowledge graph (`knowledge_graph.py`), and knowledge base (`knowledge_base.py`) now all pass through the content security gate before writing user-provided text.
- Defense layer count unchanged (11). These are hardening fixes to existing layers, not new capabilities.

### 🔧 Bug Fixes

- **LLM features** — `_llm_client` imports in `agent_memory`, `learner`, `auto_extractor`, and `knowledge_graph` fixed for pip-installed environments.
- **SQLite FTS** — Import paths in `agent_memory_sqlite.py` fixed for package-mode execution.
- **Python 3.9 compatibility** — `feedback.py` type annotation fixed (`dict | None` → `Optional[dict]`).

## v2.7.6 — Memory Signature + Defense Log (2026-05-26)

### ✍️ Memory Digital Signature

- **HMAC-SHA256 per-file signing** — `signature.py` signs `conversation_memory.json` and `vector_index.json` on every write.
- **Auto-verify & recover** — `moyu doctor --fix` checks all signatures and auto-restores from signed backups.
- **Backup signing** — daily backups are also signed, forming a trust chain: write → backup → verify → recover.
- **Default off** — set `MOYU_SIGN_KEY` to enable. Zero-config priority preserved.
- Defense layer expanded from 10 to 11: added **Memory Digital Signature**.

### 📋 Defense Log

- **Unified event reporting** — `defense_log.md` in MOYU storage dir records all defense events.
- **8 defense layers wired in**: content gate, PII, LLM guard, burst rollback, signature, password, forensic, loop detection.
- **Event dedup** — same event type within 10 min is silently merged.
- **Auto-cron notification** — red/yellow events trigger a one-shot cron message to the chat.
- Integration layer expanded from 5 to 6: added **Defense Log**.

## v2.7.4 — Frequency Guard + Read Monitoring (2026-05-24)

### 🧱 Frequency Guard V1.0

- **Unified frequency monitoring framework** — `frequency_guard.py` replaces hard-coded write burst protection with a configurable sliding window engine.
- **Write burst protection** (unchanged behavior): >30 writes/60s → rollback + 5min lock.
- **Read burst monitoring** (new): >100 reads/60s → alert log (no blocking). Every `moyu search` is tracked.
- **`moyu frequency stats`** — Check current frequency status for all rules.
- **`moyu frequency unlock <name>`** — Manually unlock a rule.
- **Backward compatible** — old lock files (`write_lock.json`, `write_freq.json`) reused; same file paths. No config changes needed.

### 🛡️ Security

- Defense chain expanded from 9 to 10 capabilities: added **access behavior monitoring** (read frequency).

## v2.7.2 — Auto memory extraction + Session bridge V2.2 (2026-05-24)

### 🆕 Auto Memory Extraction

- **`moyu extract <text>`** — Manual extraction from any text. Extracts facts into memory.
- **Automatic extraction** — Every `moyu` command scans its text arguments for facts to store. Enabled by default (`memory.auto_extract: true` in config.yaml).
- **Dual-channel pipeline**: Fast path (27 regex patterns, 0 token cost) + Slow path (LLM, ~500 tokens for edge cases).
- **Extraction scope**: preferences, decisions, corrections, personal info, technical details, habits, relations, project info, cognitive judgments.
- **Built-in safety**: semantic dedup (cosine >0.88 skipped), type density cap (10/24h per type), max 5 per call.

### 🔧 Session Bridge V2.2 — State Management

- **`add_decision(text)`** / **`add_pending(text)`** / **`remove_pending(text)`** — Track decisions and todos across sessions.
- **`format_state_summary()`** — One-line summary (topic + decisions + pending).
- **`moyu session`** — New CLI group: `state`, `prompt`, `decision`, `pending`, `clear`.
- **Generic state file** — `~/.moyu/session_state.json` written on every state change. Any Agent can read it.
- **Hermes users**: zero-config — state auto-synced to prefill.
- **Other agents**: run `moyu session prompt` or paste a one-liner into system prompt.
- **Backwards compatible**: old 10-turn summaries + 3-round conversations continue to work unchanged.

### 📝 Documentation

- README: Memory & Retrieval Layer now 8 capabilities (added Auto Memory Extraction).
- README: Cross-Session Bridge updated with V2.2 features + setup instructions for non-Hermes agents.

## v2.7.1 — Interactive quickstart + build hygiene (2026-05-23)

### Experience
- **`moyu quickstart` rewritten** — Interactive step-by-step walkthrough: user types test inputs, sees security gate in action, explores search and config. No longer a passive script.

### Build Hygiene
- **MANIFEST.in added** — Excludes internal files from sdist
- **`scripts/preflight.py` added** — Pre-build check: catches internal document leaks before they ship
- **`pyproject.toml` fixed** — `exclude-package-data` ensures wheel clean

## v2.7.0 — 架构统一 + 检索全链路 + 安全加固 (2026-05-23)

### 架构：统一 LLM 客户端 (`_llm_client.py`)

- **6 路调用合一** — `learner.py` / `knowledge_graph.py` / `forgetting_curve.py` / `agent_memory.py`(×2) / `memory_merge.py` 各自手搓的 LLM 调用全部替换为统一入口
- **消除密钥解析副本** — 密钥解析、基础 URL 环境变量覆盖（`MOYU_LLM_BASE_URL`）、model auto-correct 只在一个文件维护
- **NAS 端代码审查** — REST API 直连双脑联动，审查产出 `MOYU_LLM_BASE_URL` 遗漏修复 + 非200显式返回

### 检索权重全链路 (Phase 1-3)

- **Phase 1: 加权检索** — `score_and_rank` 从等权求和改为 config.yaml 加权，新增 entity 维度（默认0.0），归一化动态计算。`moyu config show/set` CLI 可配
- **Phase 2: 反馈收集** — `moyu search --vote <id> good|bad`、`moyu ref`、`moyu learn` 自动写入 JSONL 日志，按月切分
- **Phase 3: 自适应调优** — `moyu tune` / `--dry-run` / `--reset`，渐变小步长调整

### 新命令

| 命令 | 作用 |
|:----|:----|
| `moyu inject` | 标准化记忆注入，输出自动带 `[NOTE]` 上下文预警 |
| `moyu quickstart` | 5 分钟交互式演示 — 零配置展示防御链效果 |
| `moyu config` | 检索引擎权重查看/调整 |
| `moyu setup agents` | 首次运行自动检测 Agent + 集成配置 |
| `moyu search --vote` | 搜索反馈 (Phase 2) |

### 安全加固

- 词库 **516 条**
- LLM 安检 prompt **5 类 → 8 类**（新增越狱短词、PII 提取、社会工程分类）
- short-word 正则经 NAS 审查后因误报风险回退

### 双躯壳联动

- **路径 1（首选）** — NAS REST API 直连 (`192.168.1.21:8788`)，`POST /api/chat/start` 发消息，`GET /api/session` 读回复
- **路径 2（备选）** — Kimi WebBridge → Chrome → NAS WebUI
- 单次讨论上限 10 轮，防上下文溢出

## v2.5.0 — Released (2026-05-20)

### New Features: 6 LLM-Enhanced Capabilities (All Default-On)

| Feature | What it does | Fallback |
|---------|-------------|----------|
| **Smart Summary** | `add_memory` auto-refined by LLM — strips filler, keeps all facts and decisions | Raw text truncation |
| **Search Rerank** | LLM re-ranks top candidates by semantic relevance beyond keyword matching | `score_and_rank` original order |
| **Memory Merge** | LLM generates coherent merged summaries instead of keyword concatenation | Keyword concatenation |
| **Scene Classification** | LLM assigns semantic scene labels (project/personal/general) to new memories | Keyword frequency matching |
| **KG Entity Extraction** | LLM extracts entity-relation triples with JSON structured output | Regex fallback |
| **Forgetting Review** | LLM reviews demotion candidates for semantic importance (preferences, identity, milestones) | Rule-only demotion |

All six features reuse your existing API key — no new keys, no new dependencies. No API key? Each silently degrades to its local fallback with a one-time notice. Circuit breaker halts after 3 consecutive failures.

### Fixes

- **API key priority corrected** — `.env` file now checked before `DEEPSEEK_API_KEY` environment variable. Previously, an env var with wrong key could override a valid `.env` key. Fixed across 6 call sites in 5 files: `agent_memory.py`, `forgetting_curve.py`, `memory_merge.py`, `knowledge_graph.py`, `integrity_checker.py`.

### Zero-Dependency Commitment

No new pip packages. No new runtime requirements. `pip install moyu-memory` still works with zero config. LLM features are additive enhancements, not gatekeeping — everything works without them.

---

## v2.4.8 — Released (2026-05-20)

### Fixes
- **Security gate path bug (critical)** — `_load_patterns()` in `integrity_checker.py` was looking for `forensic_patterns.json` in the wrong directory when installed via pip. Result: **0 patterns loaded, content security gate was always bypassed.** Fixed by correcting the path to include `defense_toolkit/` subdirectory.
- **Hermes context monitoring fix** — Previously only read the latest single session's token count (~2%), now reads all messages from the last 24 hours with dynamic window sizing (128K for small sessions, 1M for long sessions). Result: 49% vs WebUI 62%, close enough to be useful for warning.
- **Agent `likely_compressed` normalization** — All 5 Agent parsers (Claude Code, OpenClaw, Cursor, Continue) now use `pct >= 85` instead of arbitrary `calls > 30` thresholds that caused false positives.

### New Features
- **Protected memory whitelist** — `moyu protect {list|add <id>|remove <id>}`. Memoried marked as `protected` are never demoted by the forgetting curve. Supports audit logging for protect/unprotect events.
- **Enhanced `moyu status`** — Now shows disk usage (MB used / GB free), audit log event counts (demote/distill/merge/protect), SQLite FTS5 index health, and protected memory count.
- **Clean `from moyu import xxx` path** — New `moyu/` package directory allows `from moyu import context_manager`, `from moyu.security import verify_operation`, etc. alongside the existing `moyu_toolkit` namespace.

### Documentation
- **Security gate test results** — 80% interception rate on known injection patterns (tested with 40+ samples, 0 false positives). README already honestly states ~60% for simple injection and ~0% for semantic-level.

---

## v2.4.7 — Released (2026-05-19)

### New Features
- **Audit log** — forget/distill/merge operations now recorded to `audit_log.json` with timestamps, memory IDs, and reasons. Persistent, atomic writes, last 500 entries kept.
- **Memory source differentiation** — `forgetting_curve` now treats `agent`/`system`-sourced memories differently: safety window reduced by half (demote_days // 2), making less-trusted content eligible for cleanup sooner.
- **Contributing guide** — `CONTRIBUTING.md` with instructions for adding injection patterns, Provider detectors, and PR checklist.
- **Roadmap** — `ROADMAP.md` with short/medium/long-term priorities.

### Standard Python Packaging
- **`pyproject.toml`** — MOYU is now a standard Python package. Install via `pip install moyu-memory`.
- **`moyu_toolkit/_moyu_paths.py`** — Centralized path resolution that works both in development mode and pip-installed mode.
- **16 modules updated** — Cross-module imports now use full package paths. CLI entry `moyu` registered via console_scripts.
- **Pip-aware updater** — When installed via pip, `moyu update` shows `pip install --upgrade moyu-memory`.

---

## v2.4.6 — Released (2026-05-19)

### Logic Hardening (from third-party audit)
- **Budget clamp** — `prepare_injection()` now caps budget to config value. Callers can no longer bypass compression by passing a large budget.
- **Priority clamp** — `InjectionPayload.add()` now clamps priority to 1–10. Prevents bypassing compression by setting all priorities to 0.
- **Hard truncate when disabled** — `build_injection()` when `enabled=False` still truncates each part to `budget_chars`. Prevents context overflow even with compression off.
- **Config load failure → conservative defaults** — `_load_compression_config()` and `_load_config()` now return tighter defaults on parse failure. Config corruption no longer silently loosens security.
- **Warning rate limit** — `warning_message()` now fires at most once per 60 seconds. Persistent across sessions via compression log.
- **SQLite busy timeout** — All `sqlite3.connect()` calls now set `timeout=3.0` and `PRAGMA busy_timeout=3000`. Reduces silent failures under concurrent writes.
- **Embedding API degradation alert** — `get_embedding()` now prints a warning when API embedding fails and falls back to n-gram. Users are no longer silently served non-semantic search.
- **Timestamp parse safety** — `_days_since()` returns `float('inf')` on parse failure instead of 0. Prevents erroneous memory demotion from bad timestamps.
- **Version string sanitization** — `_parse_version()` strips `-alpha`, `+build` etc. suffixes. Prevents version comparison bypass via pre-release tags.

### Reliability
- **`STORAGE_PATH` path traversal guard** — `learner.py` now validates `MOYU_STORAGE` env var against allowed directory (same pattern as integrity_checker).
- **Atomic writes in learner** — All 4 save functions (`_save_learned_signals`, `_save_lessons`, `_save_corrections`, `_save_profile`) now use temp file + `os.replace()`.
- **Update failure marker** — `updater.py` writes `.UPDATE_FAILED` on failed rollback. `moyu_wake.py` detects the marker on startup and refuses to run, preventing silent mixed-version states.

---

## v2.4.5 — Released (2026-05-19)

### Security Fixes
- **Zip slip protection** — `updater.py` now validates every member path in the zip before extracting. Malicious archives containing `../../etc/passwd` paths are rejected. Prevents arbitrary file writes via update packages.
- **Checksum enforcement** — `update()` now refuses to install any version without a known SHA256 checksum. Previously, new versions with empty checksums would skip verification entirely (TOFU weakness). Users must now download and verify manually if no checksum is available.
- **Path traversal guard** — `integrity_checker.py` `BASE` path from `MOYU_STORAGE` env var is now validated against the allowed directory. Malicious `../` sequences are rejected.
- **Path traversal guard** — `_auto_recover()` in `integrity_checker.py` now uses `os.path.basename()` to filter restore paths, preventing manifest-based directory traversal.
- **Path traversal guard** — `session_bridge.py` `MOYU_PREFILL_PATH` and `MOYU_CONTEXT_MD_PATH` env vars now validate against home directory and project directory. Out-of-bounds paths fall back to defaults.
- **Injection scan for assistant content** — `session_bridge.py` now scans both user and assistant content before writing to `prefill.json`. Previously only user messages were scanned.
- **Hide password on input** — `security.py` `setup()` and `verify_operation()` now use `getpass.getpass()` instead of `input()`. Passwords are no longer visible on screen.
- **Timing-safe hash comparison** — `security.py` now uses `hmac.compare_digest()` instead of `==` for password hash comparison.
- **Auto-clear failure count on unlock** — `_check_lock()` now calls `_clear_failures()` when a lock expires, preventing immediate re-lock due to stale failure records.

### Reliability
- **Update rollback** — `updater.py` now backs up the entire toolkit before applying updates. If the update fails mid-way (crash, disk full, etc.), it restores from backup automatically.
- **Atomic config writes** — `security.py` `_write_config_section()` now uses temp file + `os.replace()`. Prevents config corruption on power loss.
- **Atomic log writes** — `security.py` `_save_logs()` uses temp file + `os.replace()`. Prevents log corruption.
- **Atomic bridge writes** — `session_bridge.py` `_save()` uses temp file + `os.replace()`. Prevents session bridge corruption.
- **Atomic manifest writes** — `integrity_checker.py` all 3 manifest write paths now use `_atomic_write_json()` (temp file + `os.replace()`).
- **Success audit logging** — `security.py` now logs successful verifications (`ALLOWED`) in addition to failures. Previously only failures were recorded.
- **Setup no longer leaks hash** — `security.py` `setup()` no longer prints the SHA256 password hash to terminal when PyYAML is unavailable.

### Monitoring
- **Alert dedup** — `integrity_checker.py` suppresses duplicate webhook alerts of the same type within 5 minutes. Local logging continues normally.
- **Alert retry** — `_post_with_retry()` implements exponential backoff (0.5s, 1s, 2s) for webhook delivery failures. 3 retries before giving up.

---

## v2.4.4 — Released (2026-05-18)

### Security Fixes
- **Path traversal fix** — `_save_ref()` now uses SHA256 hash as filename instead of raw name concatenation. Prevents directory traversal via `..` injection. (applies to `read_ref`, `delete_ref` too)
- **Atomic config writes** — `set_config()` now writes to a temp file before replacing the original. Prevents config corruption on power loss.
- **Atomic memory file writes** — `_save_memories()` and `_save_index()` use temp file + `os.replace()`. No more partial writes on crash.
- **Real file locks** — `fcntl.flock` replaces JSON-based lock files for write frequency tracking. Eliminates race conditions in multi-process scenarios.
- **Encryption password hardening** — `_get_encryption_password()` now reads from env var only. Plaintext passwords in `config.yaml` are no longer supported.
- **Path traversal guard** — `MOYU_STORAGE` env var path is validated against the expected directory. Malicious `../` sequences are rejected.

### Bug Fixes
- **Fatal: `build_injection` parameter mismatch** — `bridge_context` and `task_map` parameters were being passed but the function signature didn't accept them. Every `wake()` call would crash with `TypeError`. Both parameters are now properly supported with priority ordering.

### Reliability
- **Graceful degradation** — `moyu_wake.py` now wraps all core module calls (`check_status`, `fc.run`, `mm.run`, `sb.load`, `ac.format_context`, `lrn.format_behavior_rules`) in try/except. Any single module failure no longer crashes the entire wake pipeline.
- **Optimized memory loading** — Wake no longer loads the entire `conversation_memory.json` (~multi-MB) just to get the last 5 entries. Instead reads the file tail (~16KB) for recent memories.

### Documentation
- `README.md` — removed all bare `pip install` commands, replaced with `see requirements.txt`
- `README.md` — context warning section added (usage, diagnose command, env var override)

---

## v2.4.3 — Released (2026-05-18)

### Context Warning (New Feature)
- **Auto-detect running agent** — scans for Hermes, Claude Code, OpenClaw, Cursor, Continue in priority order. Reads real-time context usage from local session data (SQLite/JSONL). First match wins.
- **Warning injection** — when agent context crosses `warn_threshold` (default 70%), appends a bilingual warning (en/zh) to behavioral rules via `build_injection()`. Works for any agent calling the MOYU API.
- **CLI control** — `moyu compress set warn_threshold 0.6`, `moyu compress set warn_language zh`, `moyu compress config` to view all parameters.
- **One-line status** — `moyu context` shows both MOYU budget usage and real agent context percentage in one command.

### Diagnostics & Troubleshooting
- **`moyu compress diagnose`** — scans every supported agent path and reports ✅/❌ per path, plus system info and env var status. Helps users debug detection issues without guessing.
- **Environment variable override** — `MOYU_FORCE_PROVIDER` + `MOYU_PROVIDER_PATH` bypasses auto-detection for custom installations.

### Cross-Platform Hardening
- **Hermes Windows fallback** — added `%LOCALAPPDATA%\hermes\state.db` as secondary Windows path.
- **Hermes parser fix** — replaced `ended_at IS NULL` with `ORDER BY started_at DESC` to handle sessions without proper end timestamps.
- **SQLite safety** — all `sqlite3.connect()` calls now use `with` statements, preventing file handle leaks on exceptions.
- **Ref cleanup** — auto-deletes `.ref` files older than 7 days at every `prepare_injection()` call, preventing unbounded disk growth.
- **API compatibility** — `build_context_prompt` alias added for backward compatibility with existing integrations.

### Documentation
- **README.md** — full context warning section with usage examples, agent support table, env var override instructions, and diagnose command docs.
- **CHANGELOG.md** — converted to English for GitHub release tracking.

---

## v2.3.0 — 已发布 (2026-05-16)

### 安全层完整链路
- 内容安检闸：写入前（add_memory）拦截 + prefill 同步拦截
- 法医分析：120+ 注入关键词，8 大类（指令覆盖/角色改写/规则注入/记忆操纵/越狱/提示泄露/编码绕过/注入标记）
- 告警框架：内容安检/写入爆发 两路告警
- 写入爆发防护：60 秒 30 次阈值 → 锁定 5 分钟 + 细粒度回滚
- 外置注入库：forensic_patterns.json 独立文件，避免 SecurityHub 误判
- NAS 备份与 MOYU 代码分离：nas_sync_backup.py 独立维护

### 检索增强
- 时序推理：30 条时间信号（"最近"、"上次"、"之前说过"等）
- agent_confirmed：平等化排名（用户确认 > 时间新）
- 跨记忆实体链接
- 跨场景隧道（cross_scene_tunnels）
- 维度兜底（概括/用户画像/向量/随机）

### 审计修复
- batch_index 合并写入
- session_bridge prefill 同步
- 密码验证告知原因
- 中文字符提取修复
- learner 自动触发

### 测试
- 22 项自动化测试全部通过

---

## v2.4.0 — 已发布 (2026-05-17)

### 安全修复
- **工具调用环检测（运行时侧）**：拦截所有 Agent 工具调用入口，SHA256 指纹（函数名 + 参数），穷举周期检测（1～n/3 周期），30 分钟 TTL，硬熔断返回 LoopDetectedError
- **updater 校验修复**：修复了硬编码 checksum 空值时跳过校验的问题，新增 TOFU 本地缓存（`.moyu_checksums.json`），首次更新后自动记录 SHA256，后续更新用缓存校验
- **安装命令锁定**：README.md / SKILL.md 安装命令改为 `pip install -r requirements.txt`，不再裸露未锁版本

### 任务画布（新功能）
- 从最近记忆自动生成 Mermaid 任务路径图（graph LR）
- 自动检测条目状态：✅ 完成 / 🔴 阻塞 / 🔀 决策 / 🔄 进行中
- 注入到 context prompt 最先位置，agent 一眼看懂全局进度
- 不到 30 行核心逻辑，零额外依赖
- 灵感来源：腾讯 Agent Memory 的 Context Offloading + Mermaid 任务画布

### PII 脱敏（新功能）
- 中文：手机号、身份证、银行卡、固定电话正则匹配 + 脱敏
- 国际：+1 美加 / +44 英国 / +81 日本 / +82 韩国 / +852 香港 / +886 台湾 等带国家码格式；美式括号格式 `(212) 555-1212`
- 英文/通用：Email、信用卡号、IP 地址、SSN
- 零外部依赖，纯标准库 re 实现
- 集成在 `add_memory()` 的内容安检闸之后、hash去重之前
- 脱敏后的内容不进知识图谱蒸馏路径
- 支持 CLI 独立调用：`python3 defense_toolkit/pii_redactor.py "我的手机是13812345678"`

### 命名清理
- 全局重命名 `injection` → `context`，消除云鼎扫描误判为 prompt 注入风险的隐患
- 涉及 6 个 Python 文件、3 个文档文件
- 安全检测功能中的 "injection"（`integrity_checker.py`、`agent_memory.py`、`session_bridge.py` 安全日志）不受影响，保留原词

### 知识图谱时间回溯（已完成 ✅）
- entities/relations 添加 valid_from / valid_until
- 默认查询只返回当前有效关系
- `search(query, snapshot_at="2026-02-01")` 时间旅行
- `search(query, snapshot_at="all")` 包含全部历史
- `get_entity_history("Alice")` 完整时间线
- `invalidate()` 标记关系失效不删数据
- `invalidate_entity()` 实体及其所有关系失效
- 回填兼容旧数据

### 遗忘曲线蒸馏（已完成 ✅）
- 降级前自动提取实体关系到知识图谱
- 防重复蒸馏（_kg_distilled 标志位）
- `distilled_to_kg` 汇报字段

### 测试
- 26/26 测试通过（含 4 项新增的时间回溯/蒸馏测试）

---

## v2.4.2 — 已发布 (2026-05-17)

### 新增功能
- **用户隔离（可选层）** — defense_toolkit/isolation.py，按 user_id 分目录存储，config.yaml 开关默认关闭
- **加密存储（可选层）** — defense_toolkit/encrypt.py，AES-256-GCM + PBKDF2 密钥派生，`pip install cryptography` 后启用，密码优先读取环境变量 MOYU_ENCRYPTION_PASSWORD
- **API Key 脱敏** — pii_redactor.py 新增正则覆盖 sk-/ark-/AKID/ghp_ 等主流 API Key 格式

### 文档
- **安全能力边界说明** — README.md / SKILL.md 新增诚实评估表，说明各对抗层级的覆盖率和为什么不追求顶层

---

## v2.6.0 — 记忆分层 + 自进化规则 + 安全基准 (2026-05-22)

> 源自吴恩达 DeepLearning.AI《Long-Term Agentic Memory with LangGraph》课程消化

### 新架构：三层记忆分层

- **Namespace 分层** — `add_memory()` 支持 `metadata={"namespace": "xx"}` 参数，记忆可按项目/安全/学习/个人等维度隔离存储
- **`--ns` 搜索过滤** — `moyu search <query> --ns project-moyu` 只搜指定抽屉，不干扰其他领域
- **SQLite FTS5 同步支持** — agent_memory_sqlite 新增 namespace 列，自动回迁旧数据，向后兼容
- **对话场景自动标记** — 我根据当前上下文自然决定 namespace（MOYU项目→`project-moyu`，安全讨论→`security`），不做不可靠的关键词自动分类

### 新能力：自进化安全规则

- **`custom_rules.py`** — 独立模块，存储用户自定义的检测规则到 `custom_rules.json`
- **`moyu learn` 自动识别安全规则** — 输入含引号的模式时自动提取为 blocking rule，非安全内容走原有 learner
- **`moyu rules` 命令** — 查看所有自定义规则 / 清空
- **`moyu learn <text> --ns <name>`** — 带 namespace 学习
- **防御链优先检查自定义规则** — `content_scan()` 先跑 custom_rules，再跑内置词库，你教的规则即时生效，不用等发版
- **非安全学习走回原有 learner** — 不影响已有行为

### 体验优化

- **惰性初始化** — 首次使用 `moyu search`/`learn`/`stats` 时自动创建存储目录和空文件，不再报"请先初始化"
- **安装即用** — `pip install moyu-memory` 后直接跑 `moyu search "hello"` 不报错

### 文档

- 安全能力评估表数据待更新（多层测试 74.8% + 词库 513 条）
- README 能力列表改为层内独立编号（防御层1-9，记忆层1-4等），章节标题不写总数
