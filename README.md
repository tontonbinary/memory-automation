# Memory Automation Skill

OpenClaw 记忆自动化 Skill，实现会话内容的智能蒸馏与持久化存储。

## 功能特性

- **手动触发**: 用户说"记住"、"记忆"时自动蒸馏当前会话
- **Heartbeat 触发**: 每30分钟自动检测并记录会话变化
- **智能提取**: 自动识别事件、决策、偏好、情绪、行动五类信息
- **结构化存储**: 统一的 Markdown 格式，便于检索和回顾
- **无外部依赖**: 仅使用 Python 标准库

## 安装

```bash
# 确保目录结构正确
mkdir -p ~/.openclaw/skills/memory-automation/memory

# 复制所有文件到上述目录
```

## 目录结构

```
~/.openclaw/skills/memory-automation/
├── SKILL.md                 # Skill 定义
├── config.json              # 配置
├── README.md                # 本文件
├── memory-rules.md          # 记忆规则
└── memory/
    ├── __init__.py
    ├── state_manager.py     # 状态管理
    ├── session_distiller.py # 会话蒸馏
    └── automation.py        # 主逻辑
```

## 配置

编辑 `config.json`:

```json
{
  "agent_id": "code",
  "trigger_keywords": ["记住", "记忆", "distill", "distillation"],
  "heartbeat_interval_minutes": 30,
  "l1_template": "~/.openclaw/workspaces/{agent}/workspace/memory/{date}.md",
  "state_file": "memory/heartbeat-state.json",
  "min_message_length": 10
}
```

## 使用方法

### 手动触发

```bash
# 直接运行
python ~/.openclaw/skills/memory-automation/memory/automation.py manual

# 带用户消息（用于关键词检查）
USER_MESSAGE="请记住这个" python ~/.openclaw/skills/memory-automation/memory/automation.py manual
```

### Heartbeat 触发

```bash
python ~/.openclaw/skills/memory-automation/memory/automation.py heartbeat
```

### 作为模块调用

```python
from memory.automation import MemoryAutomation

# 创建实例
auto = MemoryAutomation(agent_id="code")

# 手动触发
result = auto.run_manual(user_message="请记住这个")
print(result)

# Heartbeat 触发
result = auto.run_heartbeat()
print(result)
```

## L1 存储格式

存储位置: `~/.openclaw/workspaces/{agent}/workspace/memory/YYYY-MM-DD.md`

```markdown
# Memory Log - 2026-03-26

## 14:32
### Event
- **内容**: 完成了用户认证模块的开发
- **情绪**: positive
- **后续行动**: 准备写单元测试
- **标签**: `#event #coding #completed`
- **来源**: memory/2026-03-26.md#L5

## 15:45
### Decision
- **内容**: 决定使用 PostgreSQL 作为主数据库
- **标签**: `#decision #planning`
- **来源**: memory/2026-03-26.md#L12
```

## 提取规则

### 事件 (Event)
- 关键词: 创建了、完成了、修复了、解决了、删除了、更新了、添加了、修改了、实现了
- 示例: "完成了登录功能的开发"

### 决策 (Decision)
- 关键词: 决定、确认、采用、选择、使用、设置为、应该、需要、最好
- 示例: "决定使用 React 作为前端框架"

### 偏好 (Preference)
- 关键词: 我喜欢、我偏好、我想要、我倾向于、不要、不想、不喜欢
- 示例: "我喜欢深色主题"

### 情绪 (Emotion)
- 关键词: 太棒了、很好、不错、完美、感谢、着急、焦虑、担心
- 示例: "太棒了！问题解决了"

### 行动 (Action)
- 关键词: 去做、开始、启动、准备、着手、下一步、接下来、记得、别忘了
- 示例: "下一步需要部署到测试环境"

## 状态文件

位置: `~/.openclaw/skills/memory-automation/memory/heartbeat-state.json`

```json
{
  "last_session_key": "agent:code:session:xxx",
  "last_processed_time": "2026-03-26T14:32:00",
  "last_distilled_messages": 5,
  "version": "1.0.0",
  "updated_at": "2026-03-26T14:32:00"
}
```

## Heartbeat 触发逻辑

1. 每30分钟执行一次检查
2. 对比当前 session_key 与上次记录的 session_key
3. 如果 session_key 变化 → 触发蒸馏
4. 如果超过30分钟未处理 → 触发蒸馏
5. 更新状态文件

## 依赖

- Python 3.7+
- openclaw CLI (`openclaw sessions`, `openclaw sessions history`)
- 无第三方 Python 包

## 调试

设置环境变量查看详细日志:

```bash
export DEBUG=1
python memory/automation.py heartbeat
```

## License

MIT License
test
