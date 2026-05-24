# MOYU Python API 集成指南

MOYU 不需要复杂的集成——核心就是一个 Python 包，import 后直接调用函数。以下是最常见的几种集成方式。

---

## 安装

```bash
pip install moyu-memory
```

---

## 基础集成

### 添加记忆

```python
from moyu_toolkit.agent_memory import add_memory

# 添加一条记忆
add_memory("用户偏好简洁的设计风格", source="agent")
# → 返回 {"id": "mem_20260524...", "summary": "用户偏好简洁的设计风格", ...}

# 带命名空间
add_memory("项目决定走MVP路线", source="user", metadata={"namespace": "project-moyu"})
```

### 搜索记忆

```python
from moyu_toolkit.agent_memory import search

# 搜索
results = search("用户喜欢什么风格", top_k=3)
# → [{"summary": "用户偏好简洁的设计风格", "score": 0.85, ...}, ...]
```

### 自动提取事实

```python
from moyu_toolkit.auto_extractor import extract_and_store

# 从对话文本中自动提取事实并存入记忆
count = extract_and_store("用户: 我是前端开发，习惯用Vue3和TypeScript。")
print(f"提取了 {count} 条事实")
```

---

## 在 Agent 中集成

### 每次对话结束时自动提取记忆

```python
from moyu_toolkit.auto_extractor import extract_and_store

def on_conversation_end(user_text: str, assistant_reply: str):
    """对话结束时调用，自动提取事实"""
    text = f"用户: {user_text}\n助手: {assistant_reply}"
    count = extract_and_store(text)
    if count > 0:
        print(f"自动提取了 {count} 条新记忆")
```

### 跨会话状态续接

```python
from moyu_toolkit.session_bridge import (
    format_state_summary,
    add_decision,
    add_pending,
    remove_pending,
)

# 记录决策
add_decision("采用双通道架构")

# 添加待办
add_pending("优化检索速度")

# 生成状态摘要
summary = format_state_summary()
# → "🧠 已有决定：采用双通道架构 | 待办：优化检索速度"

# 新会话开始时，用 summary 恢复上下文
```

### 完整对话轮次记录

```python
from moyu_toolkit.session_bridge import log_round

# 每轮对话结束时调用
log_round(
    user_text="天王盖地虎",                    # 用户原文，一字不差
    assistant_summary="哈哈哈哈哈哈哈",          # 回复压缩概要
)
# 自动同步到 prefill.json，新窗口醒来自动看到前置对话
```

---

## 安全集成

### 写入前安全检查

```python
from moyu_toolkit.agent_memory import add_memory
from moyu_toolkit.defense_toolkit.integrity_checker import content_scan

# 安全检查（add_memory 内部自带，也可以单独用）
hits = content_scan("some suspicious text")
if hits:
    print(f"检测到异常内容: {hits}")
else:
    add_memory("安全的内容", source="agent")
```

### PII 脱敏

```python
from moyu_toolkit.defense_toolkit.pii_redactor import redact

text, pii_types = redact("我的手机号是13800138000")
print(text)       # "我的手机号是138****8000"
print(pii_types)  # ["phone"]
```

---

## 完整示例：一个简单的记忆 Agent

```python
from moyu_toolkit.agent_memory import add_memory, search
from moyu_toolkit.auto_extractor import extract_and_store

class MyAgent:
    def process_message(self, user_text: str) -> str:
        # 1. 自动提取事实
        extract_and_store(user_text)

        # 2. 搜索相关记忆
        memories = search(user_text, top_k=3)

        # 3. 构建上下文回复
        context = ""
        if memories:
            context = "相关记忆：\n" + "\n".join(
                f"- {m['summary']}" for m in memories
            )

        reply = self._generate_reply(user_text, context)
        return reply

    def _generate_reply(self, user_text: str, context: str) -> str:
        # 你的 LLM 调用逻辑
        return f"收到: {user_text}\n{context}"
```

---

## 注意事项

- `add_memory()` 内部自带安全检查（内容安检闸 + PII 脱敏 + LLM 安检），不需要额外调
- 所有函数在无 API Key 情况下都能工作，LLM 增强功能会静默降级
- 记忆文件默认存储在 `~/.moyu/memory_data/`，可通过 `MOYU_STORAGE` 环境变量修改
- 日志文件会自动裁剪，不会无限膨胀
