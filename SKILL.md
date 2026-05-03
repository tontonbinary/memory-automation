# Memory Automation (Mauto) - Skill 操作指南（简化版）

> 本 Skill 实现 L0→L1→L2 的记忆流转
> L3 auto-dream 已移除，L1 由 Agent 主动总结生成

---

## 1. Agent 启动时加载记忆

### 1.1 加载 L1 标签（最近 3 天）
```python
from memory.l1_reader import L1Reader

l1_reader = L1Reader(agent_id, config)
recent_l1 = l1_reader.load_recent(days=3)
```

---

## 2. Heartbeat 触发（自动执行）

Mauto Heartbeat 现在只做一件事：**保存 clean_session**

```
Step 1: Session Switch (无条件)
  └─ 检测 session_key 变化 → 保存旧 session 的 clean_session

Step 2: 积压处理 (无条件)
  └─ 检查积压的历史 session → 每心跳处理 1 个积压

Step 3: 凌晨总结提醒 (03:00-04:00)
  └─ 检查前一日 clean_session 是否已写入 L1 → 未写则提醒

Step 4: Active Session (条件: 不在静默时段)
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
- **每天凌晨 03:00-04:00 收到 heartbeat 提醒时**

### 3.2 读取 clean_session

```python
import json
from pathlib import Path

# 读取当日 clean_session
clean_path = Path(f"~/.openclaw/agents/{agent_id}/clean_session/2026-04-27.json")
if clean_path.exists():
    with open(clean_path, 'r') as f:
        messages = json.load(f)
```

### 3.3 L1 新格式

```markdown
# Memory Log - 2026-04-27

## RuleDecision
做任何代码或配置修改，先给方案，提示风险，确认后执行

## SelfEvolve
用户偏好简洁日志格式

## SocialEcology
沟通渠道是飞书

## To-do
每天凌晨 03:00-04:00 提醒总结前一日 clean_session

## Output
实现了新的 L1 格式：6 分类

## Event
用户要求整理 prompt 内容
```

### 3.4 格式规则

| 项目 | 说明 |
|------|------|
| **6 分类** | RuleDecision / SelfEvolve / SocialEcology / To-do / Output / Event |
| **正文** | 每个分类一行，无内容写 `（空）` |
| **内容** | 事实本身，不是摘要 |

### 3.5 写入 L1

```python
from memory.l1_writer import L1Writer

writer = L1Writer(agent_id, config)

# 格式：List[Dict]，每项包含 event_type、content
entries = [
    {'event_type': 'Event', 'content': '用户要求整理 prompt 内容'},
    {'event_type': 'SocialEcology', 'content': '用户偏好简洁日志格式'},
    {'event_type': 'To-do', 'content': '每天凌晨 03:00-04:00 提醒总结前一日 clean_session'},
    {'event_type': 'Output', 'content': '实现了新的 L1 格式'},
]

writer.write(entries, "2026-04-27")
```

### 3.6 同一天多个 Session 的 L1 处理

如果同一天有多个 session（如中午 reset 后产生新 session）：
1. **Reset 前**：先保存当前 session 的 clean_session
2. **Reset 后马上**：生成带后缀的 L1，如 `2026-04-28_1.md`
3. **后续 L1 生成**：不带后缀的 `2026-04-28.md` 会自动合并所有同日期的 L1 文件

```python
# Reset 后马上写入（带后缀）
writer.write(entries, "2026-04-28", suffix="_1")

# 后续合并（不带后缀，自动合并所有 2026-04-28*.md）
writer.write(new_entries, "2026-04-28")
```

**读取时 glob**：
```python
from pathlib import Path
l1_files = Path("memory/").glob("2026-04-28*.md")
# 会找到 2026-04-28.md, 2026-04-28_1.md, 2026-04-28_2.md 等
```

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
    └── {YYYY-MM-DD}.json            # 每天一个文件，追加模式
```

---

## 5. clean_session 规范

### 文件位置
- **目录**: `~/.openclaw/agents/{agent_id}/clean_session/`
- **文件名**: `{YYYY-MM-DD}.json`（每天一个文件，追加模式）

### 文件格式
```json
[
  {"r": "u", "s": "ou_xxx", "t": "2026-04-27T14:30:00+08:00", "c": "消息内容"},
  {"r": "a", "s": "", "t": "2026-04-27T14:31:00+08:00", "c": "助手回复内容"}
]
```

- `r`: 角色 (`u`=user, `a`=assistant)
- `s`: 发送者 ID
- `t`: 时间戳
- `c`: 清洗后的内容（已截断至 500 字符）

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
  },
  "l2": {
    "enabled": true
  }
}
```

**已移除的配置**：
- ❌ `llm` - 不再需要 LLM API
- ❌ `distillation` - 不再需要蒸馏
- ❌ `agent_self_distill` - 不再需要
