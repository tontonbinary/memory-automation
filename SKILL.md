# Memory Automation (Mauto) - Skill 操作指南

> 本 Skill 实现 L0→L1→L2→L3 的完整记忆流转架构

---

## 1. Agent 启动时加载记忆

Agent 启动后，**应当**执行以下记忆加载操作：

### 1.1 加载 L1 标签（最近 3 天）
```python
# 使用 L1Reader 的懒加载功能
from memory.l1_reader import L1Reader

l1_reader = L1Reader(agent_id, config)

recent_tags = set()
for i in range(3):  # 最近3天
    date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
    l1_data = l1_reader.load_index_only(date_str)
    if l1_data and l1_data.index:
        for entry in l1_data.index:
            tags_str = entry.get("tags", "")
            if tags_str and tags_str != "-":
                recent_tags.update([t.strip() for t in tags_str.split() if t.strip()])

# recent_tags 可用于上下文注入
```

### 1.2 加载 L3 长期记忆
```python
l3_path = Path(f"~/.openclaw/workspaces/{agent_id}/workspace/MEMORY.md").expanduser()

if l3_path.exists():
    l3_content = l3_path.read_text(encoding='utf-8')
    # 提取关键决策、经验教训、用户偏好等章节
    # 用于系统 prompt 注入
```

---

## 2. L2 自动触发（纠正检测）

在**每次用户消息处理时**，Agent **应当**检测用户是否表达纠正意图：

### 2.1 纠正关键字列表
```python
CORRECTION_KEYWORDS = [
    # 直接纠正
    "改", "改正", "修改", "调整", "更正",
    "不对", "错了", "错误", "有误",
    # 未来纠正
    "下次", "以后", "往后", "将来",
    "记得", "别忘了", "注意", "要",
    # 否定纠正
    "不要", "别", "不需要", "不用",
    # 强调纠正
    "必须", "一定", "务必", "千万",
]
```

### 2.2 检测逻辑
```python
from memory.l2_extraction import add_correction

# 检测用户消息
message_lower = user_message.lower()
matched_keywords = [kw for kw in CORRECTION_KEYWORDS if kw.lower() in message_lower]

if matched_keywords:
    # 提取纠正内容
    correction_content = user_message
    for kw in CORRECTION_KEYWORDS:
        correction_content = correction_content.replace(kw, "")
    correction_content = correction_content.strip()
    
    # 添加到 L2 corrections
    add_correction(
        agent_id=agent_id,
        content=correction_content,
        source="binary",
        context=f"关键字: {', '.join(matched_keywords)}"
    )
```

### 2.3 触发示例
| 用户消息 | 检测类型 | 记录内容 |
|---------|---------|---------|
| "下次记得用 Python" | future | "记得用 Python" |
| "改一下这个逻辑" | immediate | "一下这个逻辑" |
| "不要这么写了" | negative | "这么写了" |
| "这个不对，应该那样" | immediate | "这个，应该那样" |

---

## 3. Heartbeat 触发（自动执行）

Mauto 会自动处理以下流程，Agent 无需干预：

```
Step 1: Session Switch (无条件)
  └─ 检测 session_key 变化 → 处理旧 session 遗留消息

Step 2: Backlog Processing (无条件)
  └─ 检查积压的历史 session → 每心跳处理 1 个积压

Step 3: L3 Auto-Dream (时间窗口: 04:00-05:00)
  └─ 扫描未整合的 L1 → 整合到 L3 MEMORY.md

Step 4: Active Session (条件: 不在静默时段)
  └─ 处理当前 session 的新消息 → L0→L1 蒸馏
```

---

## 4. 文件路径

```
~/.openclaw/workspaces/{agent_id}/
├── workspace/
│   ├── MEMORY.md                    # L3 长期记忆
│   └── memory/
│       ├── {YYYY-MM-DD}.md         # L1 每日日志
│       ├── l3-consolidation/        # L3 整合日志
│       └── L2/                      # L2 自我改进层
│           ├── corrections.md
│           ├── patterns.md
│           └── insights.md
└── memory/
    └── heartbeat-state.json         # 状态文件
```

---

## 5. 记忆类型系统 (5+5)

### 5 类记忆 (Item Types)
- `Memory` - 重要事件/决策 → L3 Key Decisions
- `Preference` - 用户偏好 → L3 User Preferences
- `To-do` - 待办事项 → L3 Open Threads
- `Output` - 输出记录 → L3 Project Episodes
- `Emotion` - 情绪状态 → 附加到其他条目

### 5 维事件 (Event Types)
- `CoreWork` - 核心工作任务
- `EventsOutside` - 外部事件
- `SelfEvolve` - 自我改进/学习
- `SocialEcology` - 社交/生态互动
- `RuleDecision` - 规则/决策制定

---

## 6. CLI 命令（手动触发）

```bash
# L1→L2 自动提升
python -m memory.l1_to_l2 --agent {agent_id} --days 7 --min 3

# L2 管理
python -m memory.automation l2 correct --agent {agent_id} --content "..."
python -m memory.automation l2 process --agent {agent_id}
python -m memory.automation l2 status --agent {agent_id}

# L3 整合（手动触发）
python -m memory.automation l3 consolidate --agent {agent_id}

# Heartbeat（单次）
python -m memory.automation heartbeat --agent {agent_id}
```

---

## 7. 高级：重新处理已处理过的 Session

当需要**重新蒸馏**某个已处理过的 session 文件时（例如修正错误或补充遗漏）：

### 7.1 CLI 方式
```bash
# 指定 session 文件路径直接处理（绕过 processed-sessions 检查）
python -m memory.automation manual \
    --agent {agent_id} \
    --session /path/to/session_file.jsonl
```

### 7.2 Python API 方式
```python
from memory.automation import MemoryAutomation

automation = MemoryAutomation(agent_id="your_agent_id")

# 直接处理指定文件（不检查是否已处理）
result = automation._process_session_file("/path/to/session_file.jsonl")

print(f"蒸馏项: {result['items_distilled']}")
print(f"写入行: {result['lines_written']}")
```

### 7.3 注意事项
- **会重复写入 L1**：重新处理会再次追加到 L1 文件（如需清理旧条目，需手动编辑 L1）
- **不会自动更新 tracker**：如需标记为已处理，需手动调用 `ProcessedSessionsTracker.mark_processed()`
- **适用场景**：修复错误、补充遗漏、调整蒸馏策略后的重新处理

---

## 8. 配置项 (config.json)

```json
{
  "agent_id": "your_agent_id",
  "heartbeat_interval_minutes": 360,
  "l3_consolidation": {
    "enabled": true,
    "time_window": {"start_hour": 4, "start_minute": 0, "end_hour": 5, "end_minute": 0},
    "silent_hours": {"enabled": true, "start_hour": 3, "start_minute": 55, "end_hour": 4, "end_minute": 10}
  },
  "pattern_keywords": ["我喜欢", "我决定", "我偏好"],
  "pattern_threshold": 3
}
```
