---
name: memory-automation
type: public  # 公用 skill（所有 agent 可用）
description: |
  记忆自动化 Skill，实现会话内容的智能蒸馏与持久化存储。
  支持手动触发（关键词"记住""记忆"）和 Heartbeat 自动触发（每30分钟）。
  注意：每次调用必须指定 --agent 参数，指定当前 agent 的 ID。
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
  old-session: "memory/automation.py"
---

# Memory Automation Skill

## 功能

1. **手动记忆**：用户说"记住"或"记忆"时，自动蒸馏当前会话内容并写入 L1 存储
2. **自动记忆**：每30分钟检测会话变化，自动处理并记录

## 调用方式

### 命令行参数

```bash
# 手动触发
python3 -m memory.automation manual --agent <agent_id>

# 心跳触发
python3 -m memory.automation heartbeat --agent <agent_id>
```

### HEARTBEAT 配置

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

## 目录结构

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

1. **系统自动提取** → 尝试从 OpenClaw 配置 (`~/.openclaw/agents/{agent}/agent/auth-profiles.json`) 自动提取 API key
2. **提取成功** → 立即开始使用 LLM 蒸馏，无需用户干预
3. **提取失败** → 脚本输出详细的配置指导，Agent 协助用户手动配置

### API Key 获取优先级

系统按以下顺序尝试获取 API key：

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | 环境变量 | `MINIMAX_API_KEY` 或 `MINIMAX_API_TOKEN` |
| 2 | config.local.json | `~/.openclaw/skills/memory-automation/config.local.json`（本地配置，不提交 Git） |
| 3 | config.json | `~/.openclaw/skills/memory-automation/config.json`（模板配置） |
| 4 | OpenClaw 配置 | `~/.openclaw/agents/{agent}/agent/auth-profiles.json` |

### 本地开发与 Git 提交的最佳实践

**推荐方案：config.local.json（本地）+ config.json（模板）**

```bash
# 1. 本地开发使用 config.local.json（真实 API key，不提交 Git）
cp config.json config.local.json
# 编辑 config.local.json，填入真实 api_key

# 2. 保持 config.json 作为模板（api_key 为空或占位符）
# 此文件提交到 Git，供其他用户使用
```

**文件说明：**

| 文件 | 用途 | 是否提交 Git |
|------|------|-------------|
| `config.local.json` | 本地开发配置，存放真实 API key | ❌ 否（已在 .gitignore） |
| `config.json` | 模板配置，api_key 为空或占位符 | ✅ 是 |
| `config.example.json` | 空模板示例 | ✅ 是 |

### 配置失败时的补救措施

如果自动提取失败，脚本会输出以下配置选项：

```
[MemoryAutomation] ❌ 需要配置 api_key

系统已尝试自动提取但未成功。请通过以下方式之一手动配置：

方法 1: 环境变量（推荐，立即生效）
  export MINIMAX_API_KEY="your-api-key"

方法 2: 配置文件
  创建或编辑：~/.openclaw/skills/memory-automation/config.json
  
  内容格式：
  {
    "llm": {
      "api_key": "your-api-key",
      "provider": "minimax",
      "model": "MiniMax-Text-01"
    }
  }

方法 3: OpenClaw 默认配置
  确保以下文件存在且包含有效 key：
  ~/.openclaw/agents/{agent_id}/agent/auth-profiles.json
```

### 无需配置即可使用（已废弃）

~~原设计支持 regex 蒸馏作为 fallback，无需 API key 也能使用。~~

**v2.0 起已移除 regex 蒸馏**。原因：
- 效果远不如 LLM 蒸馏（质量差距大）
- 增加代码复杂度
- 用户反馈更倾向于"要么用好，要么不用"

**现在：API key 是必需的**。如果没有配置，系统会：
1. 返回清晰的错误信息
2. 提供详细的配置指导
3. 等待用户配置完成后再次尝试

## 蒸馏模式

| 模式 | 触发条件 | 需要 API key |
|------|----------|-------------|
| LLM 蒸馏 | API key 可用 | ✅ |
| ~~Regex 蒸馏~~ | ~~v2.0 已移除~~ | ❌ |

- 每次 heartbeat 检查 api_key
- API 失败时**不再 fallback**，返回错误并提示用户
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

## L1 记忆存储格式

### L1 索引（双索引：时间 + 记忆标签）

```
| 时间 | 记忆标签 | 事件类型 | 内容标签 |
|------|----------|----------|----------|
| 14:30 | Decision | CoreWork | #feature #coding |
```

**字段说明：**
- **时间**：HH:MM（UTC 原始时间）
- **记忆标签**：7类记忆类型（Event/Decision/Preference/Improve/To-do/Output/Emotion）
- **事件类型**：5类事件类型（CoreWork/CollabResult/AuxTask/SelfEvolve/EnvAwareness）
- **内容标签**：#tag1 #tag2（具体内容标签）

### L1 完整日志

```markdown
## HH:MM
### Event
- **内容**：记忆内容摘要
- **标签**：`#{标签1} #{标签2}`
- **来源**：session/03-26#L行号
```

### 记忆检索流程（Agent 调用时）

当 Agent 需要调用记忆时：

1. **匹配 L1/L2 标签索引**
   - 在上下文中识别关键词（如 #feature、#bug、#decision）
   - 通过「时间 + 记忆标签」双索引定位相关 L1 条目

2. **获取 L1 条目内容**
   - 根据 L1 条目中的「来源」字段定位 session 内容
   - 或直接读取 L1 完整日志中的内容

3. **L1 → L2 升级依据**
   - 核心依据：**事件类型 + 内容标签**
   - 当 L1 条目同时满足：
     - 事件类型（如 CoreWork/SelfEvolve）
     - 内容标签达到升级阈值
   - 则升级到 L2

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
