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
