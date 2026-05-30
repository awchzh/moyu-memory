# _storage.py 抽象层重构计划

## 目标
所有文件IO操作统一到 `_storage.py`，消灭各模块散落的 open/makedirs/path-join，
同时自动挂载安全钩子（content scan、签名、写入锁、原子写入）。

## _storage.py API 设计

```python
# 读操作
storage.read(filename) -> dict       # 读JSON文件
storage.read_raw(filename) -> str    # 读原始文本
storage.exists(filename)             # 文件是否存在
storage.path(filename) -> str        # 返回完整路径（替代 _path()）

# 写操作
storage.write(filename, data)        # 原子写入JSON（tmp→rename + 安全钩子）
storage.write_raw(filename, text)    # 原子写入原始文本

# 目录操作
storage.ensure()                     # 确保存储目录存在
storage.list_files() -> [str]        # 列出所有文件

# Manifest（SHA256索引）
storage.update_manifest(filename)    # 更新单个文件的哈希
storage.verify_manifest() -> dict    # 完整性校验
```

## 迁移顺序

### 第一批（低风险、价值高）
1. `_storage.py` 新建
2. `active_context.py` — 最关键，没有安全钩子
3. `self_reflection.py` — 改动最小
4. `knowledge_graph.py` — 简单读写

### 第二批（中等复杂度）
5. `memory_merge.py`
6. `context_manager.py`

### 第三批（核心模块，需要保留现有复杂逻辑的完整性）
7. `agent_memory.py` — 已有较规范的原子写
8. `learner.py` — 有自己的原子写
9. `forgetting_curve.py`
10. `frequency_guard.py`
11. `session_bridge.py` — 多处路径散落，特殊处理
12. `security.py` — 防御日志，签名文件

### 第四批
13. 测试更新
14. 全量测试验证
