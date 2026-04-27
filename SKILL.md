# Memory Automation (Mauto) - Skill 操作指南（简化版）

> 本 Skill 实现 L0→L1 的记忆保存架构
> L3 auto-dream 已移除，L1 由 Agent 主动总结生成
> L2 保持不变（corrections/patterns/insights）

---

## 1. Agent 启动时加载记忆

### 1.1 加载 L1 标签（最近 3 天）
```python
from memory.l1_reader import L1Reader

l1_reader = L1Reader(agent_id, config)

recent_tags = set()
for i in range(3):
    date_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
    l1_data = l1_reader.load_index_only(date_str)
    if l1_data and l1_data.index:
        for entry in l1_data.index:
            tag = entry.get("tag", "")
            if tag:
                recent_tags.add(tag)
```

---

## 2. Heartbeat 触发（自动执行）

Mauto Heartbeat 现在只做一件事：**保存 clean_session**

```
Step 1: Session Switch (无条件)
  └─ 检测 session_key 变化 → 保存旧 session 的 clean_session

Step 2: Backlog Processing (无条件)
  └─ 检查积压的历史 session → 每心跳处理 1 个积压

Step 3: Active Session (条件: 不在静默时段)
  └─ 处理当前 session 的新消息 → 清洗 → 保存 clean_session
```

**不再做的事情**：
- ❌ 不再调用 LLM API 蒸馏
- ❌ 不再自动写入 L1
- ❌ 不再触发 L3 Auto-Dream

---

## 3. Agent 自主总结 L1（新增）

### 3.1 何时总结

Agent **应当**在以下时机主动总结并写入 L1：
- 每次 session 结束前
- 用户说"总结一下今天"
- 用户说"记一下"
- Agent 认为有重要内容需要记录时

### 3.2 读取 clean_session

```python
# 读取当日 clean_session
clean_dir = Path(f"~/.openclaw/agents/{agent_id}/clean_session").expanduser()
clean_files = sorted(clean_dir.glob("*.json"))

for f in clean_files:
    data = json.loads(f.read_text())
    # data 格式: [{"r": "u/a", "s": sender, "t": timestamp, "c": content}, ...]
```

### 3.3 写入 L1（新格式）

```python
from memory.l1_writer import L1Writer

writer = L1Writer(agent_id, config)

entries = [
    {
        "tag": "To-do",           # Event|Preference|To-do|Output|Emotion
        "event_type": "CoreWork",  # CoreWork|EventsOutside|SelfEvolve|SocialEcology|RuleDecision
        "content": "用户要求简化 Mauto，去除 L3 auto-dream"
    },
    {
        "tag": "Preference",
        "event_type": "SocialEcology",
        "content": "用户偏好简洁日志格式"
    }
]

writer.write(entries, "2026-04-27")
```

### 3.4 L1 新格式示例

```markdown
# Memory Log - 2026-04-27

| 记忆标签 | 事件类型 |
|----------|----------|
| To-do | CoreWork |
| Preference | SocialEcology |

---

## CoreWork
- [To-do] 用户要求简化 Mauto：去除 L3 auto-dream，L1 改为 agent 主动提炼
- [Event] 发现 L3Consolidator 有 8 步流程，太重

## SocialEcology
- [Preference] 用户偏好简洁日志格式，索引只保留记忆标签和事件类型
```

### 3.5 格式规则

**索引表**：
- 只保留「记忆标签」和「事件类型」两列
- 去重：同一标签+事件类型组合只出现一次

**正文**：
- 按 `## 事件类型` 分组
- 每条格式：`- [记忆标签] 内容摘要`
- 内容简洁，不要复述对话，要提炼要点

---

## 4. 文件路径

```
~/.openclaw/workspaces/{agent_id}/
├── workspace/
│   └── memory/
│       ├── {YYYY-MM-DD}.md         # L1 每日日志（Agent 主动写入）
│       └── L2/                      # L2 自我改进层（保持不变）
│           ├── corrections.jsonl
│           ├── patterns.md
│           └── insights.md
└── clean_session/                   # Heartbeat 自动保存的清洗后消息
    └── {MMDD}#L{N}.json
```

---

## 5. 记忆类型系统 (5+5)

### 5 类记忆标签
- `Event` - 客观事实、问题、需求（包括踩坑）
- `Preference` - 用户偏好、习惯、忌讳
- `To-do` - 待办、承诺、需遵守事项
- `Output` - 产出物
- `Emotion` - 只记积极/负面（附加在其他标签上，不单独成条）

### 5 维事件类型
- `CoreWork` - 本职核心业务
- `EventsOutside` - 临时辅助、无重要成果
- `SelfEvolve` - 知识/纠错/习惯养成
- `SocialEcology` - 用户关系/组织/环境规律
- `RuleDecision` - 硬性规则、流程、约束

---

## 6. CLI 命令

```bash
# Heartbeat（只保存 clean_session）
python -m memory.automation heartbeat --agent {agent_id}

# 手动触发（只保存 clean_session）
python -m memory.automation manual --agent {agent_id}

# 处理积压 session
python -m memory.automation process-backlog --agent {agent_id}

# L2 管理（保持不变）
python -m memory.automation l2 correct --agent {agent_id} --topic "..." --wrong "..." --correct "..."
python -m memory.automation l2 process --agent {agent_id}
python -m memory.automation l2 status --agent {agent_id}
```

---

## 7. L2 自我改进层（保持不变）

> L2 机制不变，corrections/patterns/insights 继续由 Agent 手动维护。
> 详见原 SKILL.md 第 7 节。

---

## 8. 配置项 (config.json)

```json
{
  "agent_id": "your_agent_id",
  "heartbeat_interval_minutes": 360,
  "output": {
    "clean_session_dir": "~/.openclaw/agents/{agent}/clean_session",
    "l1_template": "~/.openclaw/workspaces/{agent}/workspace/memory/{date}.md"
  },
  "session_processing": {
    "process_inactive": true,
    "max_age_days": 3,
    "min_message_count": 50
  }
}
```

**已移除的配置**：
- ❌ `llm` - 不再需要 LLM API
- ❌ `l3_consolidation` - L3 Auto-Dream 已删除
