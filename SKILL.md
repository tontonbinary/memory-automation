# Memory Automation (Mauto) - Skill 操作指南（简化版）

> 本 Skill 实现 L0→L1→L2 的记忆流转
> L3 auto-dream 已移除，改为 **Agent 主动总结 + 凌晨 cron 触发 distill-l1**

---

## 1. Agent 启动时加载记忆

### 1.1 加载 L1 标签（最近 2 天）
```python
from memory.l1_reader import L1Reader

l1_reader = L1Reader(agent_id, config)
recent_l1 = l1_reader.load(days=2)
```

---

## 2. Heartbeat 触发（自动执行）

Mauto Heartbeat 只做一件事：**保存 clean_session**

```
Step 1: Session Switch (无条件)
  └─ 检测 session_key 变化 → 保存旧 session 的 clean_session

Step 2: 积压处理 (无条件)
  └─ 检查积压的历史 session → 每心跳处理 1 个积压

Step 3: 配置自检 (每天一次)
  └─ 检查凌晨 L1 蒸馏 cron 是否存在 → 缺则提醒 agent 创建

**自检机制**：
1. 读取 `~/.openclaw/agents/{agent_id}/heartbeat-state.json`
2. 检查上次自检时间，确保每天只执行一次
3. 扫描 cron job 列表，查找匹配 `distill-l1 --agent {agent_id}` 的定时任务
4. 如果缺失 → 输出提醒：
   ```
   ⚠️ 凌晨 L1 蒸馏 cron 未配置
   建议执行：openclaw cron add --command "distill-l1 --agent {agent_id}" --schedule "0 15 3 * * *"
   ```
5. 如果存在但时间不在 3:00-4:00 窗口 → 提示调整

Step 4: Active Session (条件: 不在静默时段)
  └─ 处理当前 session 的新消息 → 清洗 → 保存 clean_session
```

## 3. 凌晨 L1 蒸馏（cron 触发）

凌晨 3:00-4:00 由 cron 触发 `distill-l1` 命令：

```
Cron 3:15 → 发消息到 agent
  └─ agent 执行 distill-l1 命令
      ├─ 读前一日 clean_session → 无对话则静默跳过
      ├─ 读前一日 L1 → 已写则跳过
      └─ 输出对话摘要 + L1 分类模板 → agent 写 L1
```

**distill-l1 输出内容**：
1. **对话摘要**：按时间线列出昨日关键对话主题（每主题一句话）
2. **分类模板**：预填的 6 分类框架，agent 只需填入内容
   ```markdown
   ## RuleDecision
   （空）
   
   ## SelfEvolve
   （空）
   
   ## SocialEcology
   （空）
   
   ## To-do
   （空）
   
   ## Output
   （空）
   
   ## Event
   （空）
   ```
3. **引用建议**：检测近 3 天 L1 重复主题，提示用引用方式记录

**次日后安全网**：心跳自检发现缺 L1 时有 clean_session → 提醒 agent 补写。

**执行细则**：
1. 心跳检查当天是否为 "次日后"（即当前日期 > clean_session 日期 + 1 天）
2. 检查对应日期的 L1 文件是否存在（`memory/YYYY-MM-DD.md`）
3. 如果 L1 缺失但 clean_session 存在 → 输出提醒：
   ```
   📅 补写提醒：YYYY-MM-DD 的 clean_session 已保存，但 L1 尚未写入。
   建议执行 distill-l1 --date YYYY-MM-DD 补写。
   ```
4. 每天只提醒一次，避免重复打扰

---

## 4. Agent 自主总结 L1

### 4.1 何时总结

Agent **应当**在以下时机主动总结并写入 L1：
- **每天凌晨 3:15 cron 触发 distill-l1 时**（主要时机）
- 用户说"总结一下今天"
- 用户说"记一下"
- Agent 认为有重要内容需要记录时

### 4.2 读取 clean_session

```python
import json
from pathlib import Path

# 读取当日 clean_session
clean_path = Path(f"~/.openclaw/agents/{agent_id}/clean_session/2026-04-27.json")
if clean_path.exists():
    with open(clean_path, 'r') as f:
        messages = json.load(f)
```

### 4.3 L1 新格式

```markdown
# Memory Log - 2026-04-27

## RuleDecision
做任何代码或配置修改，先给方案，提示风险，确认后执行

## SelfEvolve
用户偏好简洁日志格式

## SocialEcology
沟通渠道是飞书

## To-do
Fix 4: 群聊 session 不被蒸馏到 L1（记入多维表，搁置状态）

## Output
实现了新的 L1 格式：6 分类

## Event
用户要求整理 prompt 内容
```

### 4.4 格式规则

| 项目 | 说明 |
|------|------|
| **6 分类** | RuleDecision / SelfEvolve / SocialEcology / To-do / Output / Event |
| **正文** | 每个分类一行，无内容写 `（空）` |
| **内容** | 事实本身，不是摘要 |

**蒸馏规则**：
- **SelfEvolve 入口**：所有纠正和知识先进入 SelfEvolve，再分流到 RuleDecision 或 SocialEcology
- **7 天计数制**：近 7 天内同一主题纠正次数 ≥2 次 → 升级到 RuleDecision
- **纠正升级**：SelfEvolve 只留摘要+次数标记，完整内容移至 RuleDecision
- **知识分流**：属于系统/工具/组织的知识 → SocialEcology；个人技能/通用知识 → SelfEvolve
- **只记一次**：同一件事的完整内容只在一个分类中出现
- **多日重复**：近 3 天已出现的主题用引用方式记录，不重复全文

### 4.5 写入 L1

```python
from memory.l1_writer import L1Writer

writer = L1Writer(agent_id)

# 格式：List[Dict]，每项包含 event_type、content
entries = [
    {'event_type': 'Event', 'content': '用户要求整理 prompt 内容'},
    {'event_type': 'SocialEcology', 'content': '用户偏好简洁日志格式'},
    {'event_type': 'To-do', 'content': 'Fix 4: 群聊 session 不被蒸馏到 L1'},
    {'event_type': 'Output', 'content': '实现了新的 L1 格式'},
]

writer.write(entries, "2026-04-27")
```

### 4.6 同一天多个 Session 的 L1 处理

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

## 6. 文件路径

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

## 7. clean_session 规范

### 7.1 文件位置
- **目录**: `~/.openclaw/agents/{agent_id}/clean_session/`
- **文件名**: `{YYYY-MM-DD}.json`（每天一个文件，追加模式）

### 7.2 文件格式
```json
[
  {"r": "u", "s": "ou_xxx", "t": "2026-04-27T14:30:00+08:00", "c": "消息内容"},
  {"r": "a", "s": "", "t": "2026-04-27T14:31:00+08:00", "c": "助手回复内容"}
]
```

- `r`: 角色 (`u`=user, `a`=assistant)
- `s`: 发送者 ID
- `t`: 时间戳
- `c`: 清洗后的内容（已过滤 subagent context / failed turn / 用户ID前缀 / 长格式时间戳）

---

## 8. CLI 命令

```bash
# Heartbeat（只保存 clean_session）
python -m memory.automation heartbeat --agent {agent_id}

# 手动触发 session 清洗
python -m memory.automation manual --agent {agent_id}

# 输出昨日对话摘要供 agent 写 L1（凌晨 cron 调用）
python -m memory.automation distill-l1 --agent {agent_id}
python -m memory.automation distill-l1 --agent {agent_id} --date 2026-05-06

# per-agent 运行环境检查
python -m memory.automation setup --agent {agent_id}

# 处理积压 session
python -m memory.automation process-backlog --agent {agent_id}

# L2 管理
python -m memory.automation l2 correct --agent {agent_id} --topic "..." --wrong "..." --correct "..."
python -m memory.automation l2 process --agent {agent_id}
python -m memory.automation l2 status --agent {agent_id}
```

### 8.1 setup - per-agent 运行环境检查

```bash
python -m memory.automation setup --agent {agent_id}
```

检查 Mauto 自身文件：
- heartbeat-state.json 是否存在
- HEARTBEAT.md 内容是否完整
- 凌晨 L1 蒸馏 cron job 是否存在（可选）
- 运行日志是否可写

每项输出 ✅/❌/ℹ️，缺失项附详细修复指引。只检查、不自动修复。

### 8.2 运行日志

每次 heartbeat、manual、setup 和 process-backlog 的执行记录会自动保存到：
`~/.openclaw/agents/{agent_id}/memory-automation.log`

**日志路径格式**：
- **文件**: `~/.openclaw/agents/{agent_id}/memory-automation.log`
- **格式**: JSONL（每行一条 JSON 记录）
- **保留**: 最近 1000 行，自动轮转
- **字段**: `timestamp`, `command`, `status`, `details`, `agent_id`

**示例记录**：
```json
{"timestamp": "2026-05-07T03:15:00+08:00", "command": "heartbeat", "status": "success", "details": "saved 12 messages", "agent_id": "mautoer"}
```

---

## 9. L2 自我改进层

L2 机制继续保留，由 Agent 手动维护：

- `corrections.jsonl` - 纠正记录（时间戳、主题、错误做法、正确做法）
- `patterns.md` - 行为模式（场景、根因、教训、修复、预防检查清单）
- `insights.md` - 洞察原则（踩坑记录、经验总结）

详见 `docs/memory-distill-rules-draft.md` 完整规则。

---

## 10. 配置项 (config.json)

```json
{
  "agent_id": "your_agent_id",
  "heartbeat_interval_minutes": 10,
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
