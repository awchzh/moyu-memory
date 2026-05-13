---
|name: moyu
description: MOYU — AI Agent 记忆工具包。TEMPR 多策略检索、工作记忆、知识图谱、自我反思、学习信号、自动恢复、记忆自我保护等 11 大能力。
tags: [ai-agent, memory, python, agent-memory, llm, rag, knowledge-graph, security, 记忆, 工具包, AI Agent, 向量检索, 知识图谱, 检索增强]
---

# MOYU — AI Agent 记忆工具包

> 给你的 AI Agent 装上 11 大记忆能力，跨会话真正记得你是谁。

GitHub 仓库：https://github.com/awchzh/moyu-memory

## 11 大能力

1. **TEMPR 多策略检索** — 语义 + BM25 关键词 + 时间加权，三重保障
2. **工作记忆** — 独立文件存储，上下文压缩也不丢
3. **轻量知识图谱** — 自动提取实体关系（JSON，零数据库）
4. **自我反思** — 醒来时自动分析旧记忆，发现关联与矛盾
5. **用户画像** — 自动从对话中提取用户偏好和事实
6. **从纠正中学习** — 识别纠错信号，3 次晋升为永久规则
7. **防重复** — SHA256 哈希去重
8. **完整性校验** — 检测记忆文件篡改
9. **自动恢复** — 检测到篡改后自动从备份恢复
10. **法医分析** — 分析篡改来源（指令覆盖、提示词注入等）
11. **记忆自我保护** — 第一道防火墙。操作到达记忆文件之前阻止误删和篡改。密码验证 + 自动锁定 + 审计留痕

## 快速开始

```bash
pip install numpy requests pyyaml
```

把 `moyu_toolkit/` 文件夹复制到你的项目中：

```bash
cd moyu_toolkit
python3 agent_memory.py search "我们聊过什么"
```

**（可选）设置安全密码：**

```bash
python3 security.py setup
```

这是记忆的第一道防火墙——在误删和篡改真正发生之前阻止它们。**一条命令统领全局：**

```bash
cd moyu_toolkit && python3 moyu.py --help
```

所有 MOYU 功能统一入口——检索、统计、设置、演示，一个命令搞定。

设置后，删除文件、修改配置等危险操作需要密码确认。

## 对比

| 对比项 | 平台自带 | MOYU |
|--------|---------|------|
| 存储方式 | 纯文本 | 向量索引（1536维语义） |
| 检索方式 | 全文读取 | **TEMPR 三重策略** |
| 工作记忆 | ❌ 无 | ✅ 抗压缩 |
| 知识图谱 | ❌ 无 | ✅ JSON 文件 |
| 自我反思 | ❌ 无 | ✅ 自动 |
| 用户画像 | ❌ 手动 | ✅ 自动 |
| 学习纠正 | ❌ 无 | ✅ 自动 |
| 完整性校验 | ❌ 无 | ✅ manifest + SHA256 |
| 自动恢复 | ❌ 无 | ✅ 从备份恢复 |
| 法医分析 | ❌ 无 | ✅ 攻击来源分析 |
| 记忆自我保护 | ❌ 无 | ✅ 事前验证，拦截危险操作 |
| API 切换 | 固定 | ✅ 随意切换 |
| 平台绑定 | 绑定平台 | ✅ 零绑定 |

## 适用平台

Hermes、OpenClaw、LangChain、AutoGen，或任何基于 Python 的 AI Agent。

## 许可证

MIT
