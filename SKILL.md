---
name: memory-automation
type: public  # 公用 skill（所有 agent 可用）
description: |
  分层记忆管理 Skill，实现 L0→L1→L2→L3 的完整记忆流转。
  
  四层架构：
  - L0: Session 原始记录
  - L1: 每日日志（Event/Decision/Preference/Improve/To-do/Output/Emotion）
  - L2: 自我改进层（corrections → patterns → insights）
  - L3: 长期记忆（verified insights）
  
  支持手动触发、Heartbeat 自动触发、L2 实时纠正。
  注意：每次调用必须指定 --agent 参数。
  静默时段（03:55-04:10）手动和自动触发均跳过。
triggers:
  manual:
    - keywords: ["记住", "记忆", "distill", "distillation"]
      condition: "用户消息包含上述关键词"
  heartbeat:
    - interval: "6h"
      condition: "session_key 变化 或 距离上次处理超过6小时"
config:
  agent_id: "code"
  trigger_keywords: ["记住", "记忆", "distill", "distillation"]
  heartbeat_interval_minutes: 360
  l1_path_template: "~/.openclaw/workspaces/{agent}/workspace/memory/YYYY-MM-DD.md"
  l2_dir: "~/.openclaw/workspaces/{agent}/workspace/memory/L2"
  state_file: "memory/heartbeat-state.json"
  memory_rules: "~/.openclaw/memory-rules.md"
entry_points:
  manual: "memory/automation.py"
  heartbeat: "memory/automation.py"
  old-session: "memory/automation.py"
  l2: "memory/automation.py"
---

# Memory Automation Skill

## 分层架构

```
┌─────────────────────────────────────────────────────────────┐
│ L3: 长期记忆 (Long-term)                                     │
│    ~/self-improving/memory.md                               │
│    - Verified Insights (已验证的原则)                        │
│    - Consolidated Patterns (稳定的行为模式)                   │
│    - 跨 session 的持久知识                                   │
├─────────────────────────────────────────────────────────────┤
│ L2: 自我改进层 (Self-improving)                              │
│    ~/.openclaw/workspaces/{agent}/workspace/memory/L2/      │
│    - corrections.md: 被纠正的记录 (L0→L2 实时)                │
│    - patterns.md: 聚合的行为模式 (L1→L2 定期)                 │
│    - insights.md: 提炼的洞察/原则 (L2→L3 候选)                │
├─────────────────────────────────────────────────────────────┤
│ L1: 每日日志 (Daily Log)                                     │
│    ~/.openclaw/workspaces/{agent}/workspace/memory/YYYY-MM-DD.md
│    - Event/Decision/Preference/Improve/To-do/Output/Emotion │
│    - 通过 L1→L2 提升进入改进层                                │
├─────────────────────────────────────────────────────────────┤
│ L0: Session 记录 (Raw)                                       │
│    ~/.openclaw/agents/{agent}/sessions/*.jsonl              │
│    - 原始对话记录                                            │
└─────────────────────────────────────────────────────────────┘

流转路径：
  L0 → L1: 手动/Heartbeat 蒸馏
  L0 → L2: 实时纠正
  L1 → L2: 标签提升 / patterns 聚合
  L2 → L3: 定期提升 (verified insights / 稳定 patterns)
```

## 功能模块

### L1 记忆管理（原有）

**触发方式：**
1. **手动触发**：用户说"记住"、"记忆"等关键词
2. **Heartbeat 触发**：每6小时自动检测

**存储格式：**
```markdown
| 时间 | 记忆标签 | 事件类型 | 内容标签 |
|------|----------|----------|----------|
| 14:30 | Decision | CoreWork | #feature #coding |
```

### L2 自我改进层（新增整合）

**数据来源：**
- **实时（L0→L2）**：被纠正时立即写入 corrections.md
- **定期（L1→L2）**：从 L1 扫描生成 patterns 和 insights

**统一三文件结构（写入规则）：**

| 文件 | 层级 | 何时写入 | 写入者 | 内容示例 |
|------|------|---------|--------|---------|
| `corrections.md` | 底层 | **实时**：Agent 被用户纠正时 | Agent 自己或脚本 | 用户说"不对，应该用..." |
| `patterns.md` | 中层 | **定期**：① corrections 聚合<br>② L1 标签提升 | 定期脚本 | "用户偏好先讨论架构再写代码" |
| `insights.md` | 顶层 | **验证后**：patterns 提炼为原则 | Agent（人工确认） | "优先澄清需求再出方案" |

**Agent 写入决策流程：**

```
被用户纠正？
  └─ 是 → 立即写入 corrections.md
  
发现了重复行为模式？
  └─ 是 → 写入/更新 patterns.md
  
模式已验证为长期原则？
  └─ 是 → 写入 insights.md（status=verified）
```

**写入方式：**

```python
# Python API - 根据内容类型选择对应文件
from memory.l2_extraction import add_correction, add_or_update_pattern, add_insight

# 实时纠正 → corrections.md
add_correction(agent_id='code', content='被纠正的内容', source='binary')

# 模式识别 → patterns.md（Agent 或系统自动）
add_or_update_pattern(agent_id='code', 
                      pattern_key='discussion-order',
                      description='讨论顺序偏好',
                      examples=['示例1', '示例2'])

# 洞察提炼 → insights.md（需验证后）
add_insight(agent_id='code',
            title='优先澄清需求',
            principle='在给出方案前，先确认用户真实需求',
            status='verified')
```

## 调用方式

### L1 命令

```bash
# 手动触发记忆蒸馏
python3 -m memory.automation manual --agent <agent_id>

# Heartbeat 触发
python3 -m memory.automation heartbeat --agent <agent_id>

# 处理旧 session
python3 -m memory.automation old-session <session_key> --agent <agent_id>
```

### L2 命令

**实时写入（L0→L2）：**
```bash
# 添加纠正记录 → corrections.md
python3 -m memory.automation l2 correct \
    --agent <agent_id> \
    --content "被纠正的具体内容" \
    --source binary \
    --context "场景上下文"
```

**定期处理（Corrections→Patterns）：**
```bash
# 从 corrections 聚合生成 patterns → patterns.md
python3 -m memory.automation l2 process --agent <agent_id>
```

**L1→L2 提升入口：**
```bash
# 从 L1 标签提升符合条件的到 patterns.md
python3 -m memory.l1_to_l2 --agent <agent_id> --days 7 --min 3
```

**查看 L2 状态：**
```bash
python3 -m memory.automation l2 status --agent <agent_id>
```

### L3 命令（新增）

**L2→L3 提升（长期记忆）：**
```bash
# 将符合条件的 L2 提升到 L3
python3 -m memory.automation l3 promote --agent <agent_id>

# 模拟运行（不实际写入）
python3 -m memory.automation l3 promote --agent <agent_id> --dry-run
```

**查看 L3 状态：**
```bash
python3 -m memory.automation l3 status --agent <agent_id>
```

**L3 升级规则：**

| 来源 | 条件 | 目标 |
|------|------|------|
| insights.md (verified) | status=verified, >=7天 | L3 Verified Insights |
| patterns.md | count>=5, >=30天 | L3 Consolidated Patterns |

**L3 存储位置：**
```
~/self-improving/memory.md
```

### Python API

```python
from memory import MemoryAutomation

# L1 自动蒸馏
auto = MemoryAutomation(agent_id="code")
auto.run_manual()

# L2 实时纠正（从 l2_extraction 导入）
from memory.l2_extraction import add_correction
add_correction(
    agent_id="code",
    content="被纠正的内容",
    source="binary",
    context="场景上下文"
)
```

## 静默时段

自动蒸馏会在 **03:55 - 04:10** 跳过（避免与 Auto-Dream 等其他定时任务冲突）。

## L1 记忆存储格式

### 7类记忆类型

| 类型 | 说明 | 示例 |
|------|------|------|
| Event | 客观事实、问题、需求 | "创建了文件"、"遇到了bug" |
| Decision | 结论、规则、方案 | "决定采用"、"确认用" |
| Preference | 用户偏好、习惯 | "我喜欢"、"不要用" |
| Improve | 用户纠正、改进 | "改成"、"不对" |
| To-do | 待办、下一步 | "去做"、"开始" |
| Output | 产出物 | "完成了"、"生成了" |
| Emotion | 情绪（只记积极/负面） | "烦躁"/"满意" |

### 5类事件类型

| 类型 | 说明 |
|------|------|
| CoreWork | 本职核心业务与关键任务 |
| CollabResult | 接收其他 Agent 交付的成果 |
| AuxTask | 临时辅助、无重要成果的事务 |
| SelfEvolve | 知识、纠错、规则、红线 |
| EnvAwareness | 用户、系统、分工、规律 |

## L2 文件格式

### corrections.md
```markdown
# Corrections

## 2026-04-07 15:30
**来源**: binary
**内容**: 被纠正的具体内容
**上下文**: 场景上下文
---
```

### patterns.md
```markdown
# Patterns

## discussion-order
**Description**: 讨论顺序模式
**Count**: 3
**Created**: 2026-04-07 15:30
**Updated**: 2026-04-07 15:30

**Examples**:
- 示例1
```

### insights.md
```markdown
# Insights

## 优先澄清需求
**Principle**: 在给出方案前，先确认用户真实需求
**Status**: verified
**Created**: 2026-04-07 15:30
**Updated**: 2026-04-07 15:30
```

## 与 l2-extraction 的关系

**历史**：`l2-extraction` 曾是独立的 skill，现已整合为 `memory-automation` 的子模块。

**整合方式**：
- 原 `l2-extraction/l2_extraction/` → `memory-automation/memory/l2_extraction/`
- 原独立 CLI → 统一入口 `python -m memory.automation l2 ...`
- 统一的四层架构定义

## 配置管理

### API Key 管理
- key 存储在 `config.json` 的 `llm.api_key`
- 用户可通过提供新 key 来更新

### Agent 询问用户时的标准话术

**首次询问 API key：**
```
memory-automation 需要配置以下信息：
1. API key（从哪里获取？）
2. 供应商（默认 minimax）
3. 模型（默认 MiniMax-M2.7）

如暂不提供，将使用 regex 蒸馏（效果较差）。
```

**API 错误询问：**
```
memory-automation 的 API key 已失效或配置有误。
请检查或提供新的 API key。
```

## HEARTBEAT 配置

每个 agent 的 HEARTBEAT.md 必须包含 --agent 参数：

```bash
# 示例：code agent 的 HEARTBEAT.md
cd ~/.openclaw/skills/memory-automation && python3 -m memory.automation heartbeat --agent code
```

### agent_id 说明

| agent | agent_id |
|-------|----------|
| code | code |
| xiaoxian | xiaoxian |
| TS | TS |

## 首次激活流程

当用户说"请使用 memory-automation"时：
1. Agent 执行 run_manual()
2. 如果脚本输出 `[MEMORY-AUTOMATION] API_KEY: not_configured`，
   Agent 询问用户是否提供 API key 和供应商
3. 用户提供了 → Agent 将 key 写入 config.json
4. 用户没有 → 使用 regex 蒸馏
