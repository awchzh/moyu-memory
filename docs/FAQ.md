# MOYU FAQ & 反模式

---

## 常见翻车场景

### 1. 装了之后 `moyu` 命令找不到

```bash
pip install moyu-memory
moyu search "test"
# → zsh: command not found: moyu
```

**原因：** pip 安装的脚本目录没在 PATH 里。

**解决：**
```bash
python3 -m pip install --user moyu-memory
export PATH="$HOME/Library/Python/3.9/bin:$PATH"    # macOS
# 或
export PATH="$HOME/.local/bin:$PATH"                 # Linux
```

加到 `~/.zshrc` 或 `~/.bashrc` 里就不用每次敲了。

### 2. 装了之后 `moyu` 命令是旧版本

```bash
moyu --version
# 还是 2.6.0，但我刚装了 2.7.2
```

**原因：** 系统中同时存在 pip 安装和手动 copy 两个版本，PATH 优先找到了旧的。

**解决：** 找到旧的删除，或者直接用绝对路径：
```bash
which moyu                    # 看当前用的是哪个
python3 -m pip show moyu-memory  # 看 pip 装的是哪个版本
```

### 3. LLM 功能（智能摘要、语义重排）不工作

```bash
moyu search "关键词"
# 搜到了但没有重排效果
```

**原因：** 没有配置 API Key，或 API Key 指向的 provider 不可达。

**解决：** 配环境变量（不需要改 config.yaml）：
```bash
export MOYU_LLM_BASE_URL="https://api.openai.com/v1"
export OPENAI_API_KEY="sk-..."
```

配好后不需要重启，下次执行命令自动生效。没有 key 也不影响核心记忆功能，只是 LLM 增强部分会静默降级。

### 4. `moyu extract` 提取不到任何记忆

```bash
moyu extract "今天天气不错"
# → Extracted 0 memories
```

**原因：** 提取器只针对有信息量的事实——偏好、决定、个人信息、技术细节等。纯闲聊寒暄不会触发提取。

**试试这些：**
```bash
moyu extract "我是前端开发，习惯用Vue3"
moyu extract "我决定用Python做后端"
moyu extract "我讨厌用微信沟通工作"
```

### 5. 安全密码忘了

```bash
moyu verify delete
# → 需要密码，但我忘了设过什么
```

**解决：** 密码只阻止危险操作，不影响正常读写。忘了的话重置：
```bash
moyu setup    # 重新设置新密码
```

如果连续输错 3 次被锁定，等 30 分钟自动解锁，或用 `moyu unlock`。

### 6. 文件完整性校验报错

```bash
moyu check
# → 显示 manifest 不匹配
```

**可能原因：**
- 手动编辑了记忆文件（`conversation_memory.json` 等）
- 从备份恢复后 manifest 没更新

**解决：**
```bash
moyu init     # 重新生成校验清单
```
如果是因为手动改文件导致的，改完文件后记得跑 `moyu init` 更新校验。

### 7. 上下文一直显示 100%

```bash
moyu context
# → Hermes窗口: 100%
```

**说明：** Hermes 的上下文窗口已满，不是 MOYU 的问题。MOYU 的压缩机制在下次 wake 时自动处理。你也可以手动触发：
```bash
moyu compress --now
```

### 8. pip 安装后找不到 auto_extractor

```bash
moyu extract "test"
# → auto_extractor not available
```

**原因：** 版本低于 2.7.2。升级：
```bash
pip install --upgrade moyu-memory
```

---

## 反模式（不要这样做）

### ❌ 手动编辑 JSON 记忆文件

`conversation_memory.json` 是 MOYU 的内部数据格式。手动改它会导致：
- 向量索引不同步（搜不到新内容）
- JSON 格式错误导致整个文件无法读取
- 完整性校验报错

**✅ 正确做法：** 用 `moyu search` 查询，用 `moyu extract` 添加。

### ❌ 把多个 MOYU 实例指向同一个 storage 目录

MOYU 没有内置的并发写入锁（除写入爆发防护外）。两个进程同时写一个文件会互相覆盖。

**✅ 正确做法：** 每个 Agent 用独立的 storage 路径，或通过 `MOYU_STORAGE` 环境变量隔离。

### ❌ 在 config.yaml 里写死 API Key

```yaml
api:
  api_key: sk-xxxxx    # 不要这样做
```

config.yaml 可能会被提交到 git、包含在 pip 包中、或被他人看到。

**✅ 正确做法：** 通过环境变量配置：
```bash
export MOYU_API_KEY="sk-xxxxx"
# 或
export DEEPSEEK_API_KEY="sk-xxxxx"
```

### ❌ 依赖 `moyu wake` 做实时同步

`moyu wake` 是 cron 任务（每 2 小时），不是实时守护进程。想实时获取最新记忆应该用 `moyu search` 而不是等 wake。

### ❌ 删掉 `memory_data/` 目录来「清空记忆」

这样做会导致：
- 完整性校验报错
- 向量索引丢失（重建需要时间）
- 知识图谱数据丢失

**✅ 正确做法：** MOYU 的遗忘曲线会帮你清理不常用的记忆。想手动清空：`moyu init` 重新初始化。

---

## 怎样调试

```bash
moyu doctor          # 记忆健康检查
moyu audit           # 防御链状态
moyu status          # 系统状态
moyu stats           # 全统计
moyu context         # 上下文占用率
```

大部分问题 `moyu doctor` 能扫出来。
