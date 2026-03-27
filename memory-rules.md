# 记忆规则 (Memory Rules)

## L1 存储规范

### 文件位置
- **全局路径模板**: `~/.openclaw/workspaces/{agent}/workspace/memory/YYYY-MM-DD.md`
- **按日期分文件**: 每天一个文件，便于管理和检索
- **自动创建**: 目录和文件由自动化模块自动创建

### 记录格式
```markdown
## {HH:MM}
### {事件类型}
- **内容**: {提炼的核心信息}
- **情绪**: {positive/negative/无}
- **后续行动**: {待办或下一步}
- **标签**: `#event #coding #user`
- **来源**: memory/YYYY-MM-DD.md#L{行号}
```

### 事件类型
1. **Event** - 客观发生的事件（创建、完成、修复、部署）
2. **Decision** - 做出的决策（决定、确认、选择）
3. **Preference** - 用户偏好（喜欢、偏好、想要）
4. **Emotion** - 情绪表达（感谢、焦虑、兴奋）
5. **Action** - 后续行动（下一步、去做、记得）
6. **Improve** - 用户纠正/改进（认知纠正、规则修正、错误修正）

## 蒸馏规则

### 提取优先级
1. 用户明确说"记住" - 最高优先级，全文提取
2. 事件类词汇 - 次高优先级
3. 决策和偏好 - 中等优先级
4. 情绪和行动 - 记录但不重复

### 过滤规则
- 忽略少于 10 个字符的消息
- 忽略纯问候语（你好、在吗、谢谢等）
- 忽略重复内容（去重检查）

### 标签体系
- **角色**: #user #assistant
- **类型**: #event #decision #preference #emotion #action #improve
- **主题**: #coding #meeting #question #completed #planning

## Heartbeat 规则

### 触发条件（满足任一即触发）
1. Session Key 发生变化（新会话）
2. 距离上次处理超过 30 分钟

### 状态文件
- **位置**: `~/.openclaw/skills/memory-automation/memory/heartbeat-state.json`
- **内容**: 上次处理的 session_key、时间戳、消息数

## 手动触发

### 关键词
"记住"、"记忆"、"distill"、"distillation"（不区分大小写）

### 用法
用户说"请记住这个" → 触发当前会话的全量蒸馏

## 存储原则

1. **宁可多记，不可漏记** - 存储成本低，遗漏成本高
2. **结构化优先** - 使用统一的 Markdown 格式
3. **可追溯** - 保留来源信息（行号、时间戳）
4. **定期整理** - 建议每周回顾，合并到 MEMORY.md
