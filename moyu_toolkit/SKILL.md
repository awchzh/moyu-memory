---
||name: moyu
||description: 墨羽 v2.4.0 — 25 项能力的 AI Agent 安全记忆工具包。四层防御链（内容安检/PII脱敏/密码/校验恢复）、知识图谱时间回溯+蒸馏、TEMPR多策略检索、遗忘曲线、任务画布、跨会话桥接、从纠正中学习、法医分析、自动更新等。
||tags: [ai-agent, memory, python, agent-memory, llm, rag, knowledge-graph, security, pii, 记忆, 安全, 工具包, AI Agent, 向量检索, 知识图谱, 检索增强, 自适应压缩, 记忆生命周期, 遗忘曲线, 场景保护]
|---

# 墨羽 v2.4.0 — 25 项能力的 AI Agent 安全记忆工具包

> 给你的 AI Agent 装上安全、智能、自我进化的记忆系统。零平台绑定，开箱即用。

GitHub 仓库：https://github.com/awchzh/moyu-memory

## 🛡️ 四层防御链（墨羽独有）

```
第 1 层（事前）：内容安检闸 + PII 脱敏 → 注入和敏感信息不入库
第 2 层（操作前）：密码验证 → 阻止危险操作
第 3 层（启动时）：完整性校验 + 法医分析 → 检测篡改
第 4 层（事后）：自动恢复 → 从每日备份还原
```

**额外防御：**
- **写入爆发防护** — 60 秒内超过 30 次写入触发回滚 + 锁定
- **工具调用环检测** — Agent 层拦截无限循环，SHA256 指纹 + 硬熔断

---

## 快速开始

```bash
pip install -r requirements.txt
```

把 `moyu_toolkit/` 文件夹复制到你的项目中：

```bash
cd moyu_toolkit
python3 moyu.py search "我们聊过什么"
```

**零配置模式：** 即装即用，无需 API Key。安装 FastEmbed 后可开启语义搜索（`pip install fastembed`）。

---

## 命令参考

```bash
cd moyu_toolkit && python3 moyu.py <命令> [参数]
```

### 🛡️ 安全

| 命令 | 说明 |
|------|------|
| `moyu setup` | 设置安全密码 |
| `moyu verify <类型> [描述]` | 验证危险操作 |
| `moyu unlock` | 解锁安全系统 |
| `moyu check` | 完整性校验（SHA256） |
| `moyu audit` | 四层防御链汇总 |
| `moyu init` | 初始化校验清单 |

### 🧠 记忆与检索

| 命令 | 说明 |
|------|------|
| `moyu search <关键词>` | TEMPR 多策略检索（语义 + BM25 + 时间加权） |
| `moyu stats` | 全统计 |
| `moyu status` | 系统状态 + 防御链可视化 |
| `moyu context` | 获取行为规则（注入到系统提示词中使用） |
| `moyu signals` | 查看学习触发词 |

### 📊 知识层

| 命令 | 说明 |
|------|------|
| `moyu kg search <实体>` | 搜索知识图谱实体关系 |
| `moyu kg search <实体> --snapshot YYYY-MM-DD` | 时间快照查询——查看过去某时刻的知识图谱 |
| `moyu kg search <实体> --snapshot all` | 包含全部历史关系（含已失效） |
| `moyu kg history <实体>` | 查看实体完整时间线（所有关系的生命周期） |
| `moyu kg invalidate --source X --target Y --relation Z [--reason ...]` | 标记关系失效（不删除，可回溯） |
| `moyu kg invalidate --entity E [--reason ...]` | 失效某实体及其所有关系 |
| `moyu kg stats` | 知识图谱统计（活跃/失效/总数） |
| `moyu kb list` | 知识文件列表 |
| `moyu kb search <关键词>` | 搜索知识文件 |
| `moyu kb read <文件>` | 读文件 |

### ⏳ 生命周期与压缩

| 命令 | 说明 |
|------|------|
| `moyu forget` | 遗忘曲线状态（三闸门 + 密度分析 + 蒸馏统计） |
| `moyu forget config` | 查看遗忘曲线参数 |
| `moyu forget set <键> <值>` | 设置参数：`demote_days`, `archive_days` 等 |
| `moyu compress` | 查看压缩状态 |
| `moyu compress --now` | 手动压缩 |
| `moyu compress config` | 查看压缩参数 |
| `moyu compress set <键> <值>` | 设置参数：`mild_threshold`, `auto_threshold` 等 |
| `moyu context` | 上下文占用率概览 |
| `moyu ref <名称>` | 读取压缩前原文（可溯源） |
| `moyu ref list` | 列出所有 refs |

### 🔄 学习与反思

| 命令 | 说明 |
|------|------|
| `moyu learn <文本>` | 从纠正中学习（3 次触发自动晋升永久规则） |
| `moyu detect <文本>` | 检测纠正信号 |
| `moyu reflect` | 自我反思 |

### 🔗 会话与更新

| 命令 | 说明 |
|------|------|
| `moyu bridge` | 会话桥状态（prefill + current_context 双同步） |
| `moyu update` | 检查更新 |
| `moyu update now` | 下载更新（TOFU 校验） |
| `moyu demo` | 全能力演示 |

---

## 对比

| 对比项 | 平台自带 | Mem0 | **墨羽** |
|--------|---------|------|----------|
| 存储方式 | 纯文本 | 向量数据库 | JSON + SQLite FTS5 |
| 检索方式 | 全文读取 | 语义（API） | TEMPR 三重策略 + RRF 融合 |
| 安全防御 | ❌ 无 | ❌ 无 | ✅ 四层防御链 |
| PII 脱敏 | ❌ 无 | ❌ 无 | ✅ 中英双语（正则） |
| 工具调用保护 | ❌ 无 | ❌ 无 | ✅ 环检测 + 硬熔断 |
| 知识图谱 | ❌ 无 | ❌ 无 | ✅ 时间回溯 + 蒸馏 |
| 工作记忆 | ❌ 无 | ❌ 无 | ✅ 抗压缩 |
| 自我反思 | ❌ 无 | ❌ 无 | ✅ 自动 |
| 用户画像 | ❌ 手动 | ❌ 无 | ✅ 自动 |
| 学习纠正 | ❌ 无 | ❌ 无 | ✅ 自动 |
| 完整性校验 | ❌ 无 | ❌ 无 | ✅ SHA256 |
| 自动恢复 | ❌ 无 | ❌ 无 | ✅ 每日备份，保留3天 |
| 法医分析 | ❌ 无 | ❌ 无 | ✅ 120+ 攻击关键词 |
| 遗忘曲线 | ❌ 无 | ❌ 无 | ✅ 三闸门 + 蒸馏 |
| 任务画布 | ❌ 无 | ❌ 无 | ✅ Mermaid 自动生成 |
| 上下文压缩 | ❌ 无 | ❌ 无 | ✅ 两级 + 可溯源 refs/ |
| 记忆合并 | ❌ 无 | ❌ 无 | ✅ 关键词重叠 |
| 自动更新 | ❌ 无 | ❌ 无 | ✅ 一键更新 |
| API 切换 | 固定 | OpenAI | ✅ 随意切换 |
| 平台绑定 | 绑定 | 绑定 SDK | ✅ 零绑定 |
| 部署 | 开箱即用 | 5 分钟 | pip install，30 秒 |

---

## 适用平台

Hermes、OpenClaw、LangChain、AutoGen，或任何基于 Python 的 AI Agent。

## 许可证

MIT
