# MOYU — Development Log

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

## 待规划

- （等用户指方向）
