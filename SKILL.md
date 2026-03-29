---
name: memory-automation
type: public  # 公用 skill（所有 agent 可用）
description: |
  记忆自动化 Skill，实现会话内容的智能蒸馏与持久化存储。
  支持手动触发（关键词"记住""记忆"）和 Heartbeat 自动触发（每30分钟）。
triggers:
  manual:
    - keywords: ["记住", "记忆", "distill", "distillation"]
      condition: "用户消息包含上述关键词"
  heartbeat:
    - interval: "30m"
      condition: "session_key 变化 或 距离上次处理超过30分钟"
config:
  agent_id: "code"
  trigger_keywords: ["记住", "记忆", "distill", "distillation"]
  heartbeat_interval_minutes: 30
  l1_path_template: "~/.openclaw/workspaces/{agent}/workspace/memory/YYYY-MM-DD.md"
  state_file: "memory/heartbeat-state.json"
  memory_rules: "~/.openclaw/memory-rules.md"
entry_points:
  manual: "memory/automation.py"
  heartbeat: "memory/automation.py"
---

# Memory Automation Skill

## 功能

1. **手动记忆**：用户说"记住"或"记忆"时，自动蒸馏当前会话内容并写入 L1 存储
2. **自动记忆**：每30分钟检测会话变化，自动处理并记录

## 目录结构

```
~/.openclaw/skills/memory-automation/
├── SKILL.md                 # 本文件
├── config.json              # 配置
├── memory/
│   ├── __init__.py
│   ├── state_manager.py     # 状态管理
│   ├── session_distiller.py # 会话蒸馏
│   └── automation.py        # 主逻辑
└── README.md                # 使用说明
```

## L1 存储格式

```markdown
## {时间戳}
### {事件类型}
- **内容**：{提炼内容}
- **情绪**：{情绪}
- **后续行动**：{行动}
- **标签**：`#{标签1} #{标签2}`
- **来源**：memory/YYYY-MM-DD.md#L行号
```

## 提取类型

- **event**：事件（"创建了"、"完成了"、"修复了"）
- **decision**：决策（"决定"、"确认"、"采用"）
- **preference**：偏好（"我喜欢"、"我偏好"、"我想要"）
- **emotion**：情绪（"好的"、"感谢"、"太棒了"）
- **action**：行动（"去做"、"开始"、"下一步"）

## 首次激活流程

当用户说"请使用 memory-automation"时：
1. Agent 执行 run_manual()
2. 如果脚本输出 `[MEMORY-AUTOMATION] API_KEY: not_configured`，
   Agent 询问用户是否提供 API key 和供应商
3. 用户提供了 → Agent 将 key 写入 config.json
4. 用户没有 → 使用 regex 蒸馏

## 蒸馏模式

| 模式 | 触发条件 | 需要 API key |
|------|----------|-------------|
| LLM 蒸馏 | config.json 有 api_key | ✅ |
| Regex 蒸馏 | 无 api_key 或 LLM 失败 | ❌ |

- 每次 heartbeat 检查 api_key，有则用 LLM
- API 失败时 fallback 到 regex，并通知用户
- Regex 蒸馏超过 30 次时，Agent 主动询问用户是否满意

## Regex 升级机制

当 regex 蒸馏次数达到 30 次时：
- 脚本输出 `[MEMORY-AUTOMATION] REGEX_LIMIT_REACHED`
- Agent 主动询问用户：
  "你已经使用 regex 蒸馏 30 次了，效果如何？
   是否要：1）提供 API key 升级到 LLM 蒸馏
          2）提供更好的蒸馏关键词/标签"

## 配置管理

### API Key 管理
- key 存储在 `config.json` 的 `llm.api_key`
- 用户可通过提供新 key 来更新
- Agent 发现 key 失效时：
  - 脚本输出 `[MEMORY-AUTOMATION] API_ERROR: API_KEY_INVALID`
  - Agent 通知用户并询问是否更新

### Agent 询问用户时的标准话术

**首次询问 API key：**
```
memory-automation 需要配置以下信息：
1. API key（从哪里获取？）
2. 供应商（默认 minimax）
3. 模型（默认 MiniMax-M2.7）

如暂不提供，将使用 regex 蒸馏（效果较差）。
```

**Regex 30 次询问：**
```
你已经使用 regex 蒸馏 30 次了，效果如何？
是否要：
1）提供 API key 升级到 LLM 蒸馏
2）提供更好的蒸馏关键词/标签
```

**API 错误询问：**
```
memory-automation 的 API key 已失效或配置有误。
请检查或提供新的 API key。
```

### 用户可以随时：
- 提供/更新 API key → Agent 写入 config.json
- 更换供应商/模型 → Agent 更新 config.json

### 当用户询问时：
- Agent 检查 config.json 当前配置
- 告知用户当前状态
- 根据用户需求更新
