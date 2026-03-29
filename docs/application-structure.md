# Memory-Automation 应用结构文档

**版本**: 1.0
**更新日期**: 2026-03-29
**状态**: 维护中

---

## 一、整体架构

### 1.1 系统定位

Memory-Automation 是一个**会话记忆蒸馏系统**，用于从 Agent 对话中自动提取关键信息并持久化存储。

```
用户对话 → Session 文件 → 蒸馏系统 → L1/L2 记忆
```

### 1.2 核心模块

| 模块 | 文件 | 功能 |
|------|------|------|
| 主入口 | `memory/automation.py` | 统一调度、参数解析、模式切换 |
| 会话管理 | `memory/session_manager.py` | Session 文件读取、状态追踪 |
| 消息处理 | `memory/message_processor.py` | 消息过滤、蒸馏协调、写入 |
| 蒸馏引擎 | `memory/session_distiller.py` | LLM 蒸馏 + Regex 降级 |
| L1 写入 | `memory/l1_writer.py` | 按日期写入 L1 记忆文件 |
| L2 写入 | `memory/l2_writer.py` | 标签化、模式匹配 |
| 状态管理 | `memory/state_manager.py` | 处理进度、session 切换追踪 |
| 模式检测 | `memory/pattern_detector.py` | 关键词触发检测 |

### 1.3 数据流

```
┌─────────────────────────────────────────────────────────────┐
│  触发方式                                                      │
│  1. heartbeat（定时）                                         │
│  2. manual --session <file>（指定 session 文件）              │
│  3. run_manual()（关键词触发）                                 │
└─────────────────┬───────────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  automation.py                                               │
│  - 解析参数、检测 agent_id                                   │
│  - 调用 session_manager 读取消息                             │
│  - 协调 message_processor                                    │
└─────────────────┬───────────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  session_manager.py                                          │
│  - 读取 session 文件（按 agent_id 隔离）                     │
│  - 追踪 last_processed_msg_id                               │
│  - 处理 session 切换                                         │
└─────────────────┬───────────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  message_processor.py                                        │
│  - 过滤消息（去除空消息、系统消息）                          │
│  - 调用蒸馏引擎                                              │
│  - 协调 l1_writer 写入                                      │
└─────────────────┬───────────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  session_distiller.py                                        │
│  - LLM 蒸馏（优先）                                         │
│    - 调用 MiniMax API                                       │
│    - MiniMax-M2.7 模型                                      │
│  - Regex 蒸馏（fallback）                                   │
│    - 预定义模式匹配                                         │
│    - event/decision/preference/emotion/action              │
└─────────────────┬───────────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────────┐
│  l1_writer.py / l2_writer.py                                │
│  - L1: 按日期写入 memory/YYYY-MM-DD.md                       │
│  - L2: 标签化、聚类                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、文件清单

### 2.1 根目录文件

| 文件 | 说明 |
|------|------|
| `SKILL.md` | Skill 定义、使用说明、激活流程 |
| `README.md` | 功能说明、架构概览 |
| `config.json` | 配置文件 |
| `memory-rules.md` | 蒸馏规则（文档） |

### 2.2 memory/ 目录

| 文件 | 行数 | 功能 |
|------|------|------|
| `automation.py` | ~700 | 主入口、调度 |
| `session_manager.py` | ~400 | Session 管理 |
| `message_processor.py` | ~300 | 消息处理 |
| `session_distiller.py` | ~600 | 蒸馏引擎 |
| `l1_writer.py` | ~250 | L1 写入 |
| `l2_writer.py` | ~200 | L2 写入 |
| `state_manager.py` | ~150 | 状态管理 |
| `pattern_detector.py` | ~100 | 模式检测 |

### 2.3 Mauto/ 目录（开发工作区）

```
~/.openclaw/workspaces/code/workspace/Mauto/
├── docs/
│   ├── update-logic-2026-03-29.md   # 本次更新内容
│   └── application-structure.md       # 本文档
```

---

## 三、配置结构

### 3.1 config.json

```json
{
  "llm": {
    "enabled": true,
    "api_key": "<MiniMax API Key>",
    "provider": "minimax",
    "model": "MiniMax-M2.7",
    "api_endpoint": "https://api.minimax.chat/v1/text/chatcompletion_v2",
    "temperature": 0.3,
    "max_tokens": 4000,
    "timeout": 60,
    "stream": false,
    "api_key_asked": false
  },
  "regex": {
    "count": 0,
    "count_asked": false
  },
  "fallback_to_regex": true,
  "distillation": {
    "min_message_length": 10,
    "min_content_length": 20,
    "max_messages_per_batch": 500
  },
  "patterns": {
    "event": ["创建了", "完成了", "修复了", ...],
    "decision": ["决定", "确认", "采用", ...],
    "preference": ["我喜欢", "偏好", ...],
    "emotion": ["好的", "感谢", "太棒了", ...],
    "action": ["去做", "开始", "下一步", ...]
  }
}
```

### 3.2 配置项说明

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `llm.api_key` | string | MiniMax API Key（用户提供） |
| `llm.model` | string | 模型名称（MiniMax-M2.7） |
| `llm.api_key_asked` | boolean | 是否已询问用户 API Key |
| `regex.count` | int | Regex 蒸馏次数计数 |
| `regex.count_asked` | boolean | 是否已询问用户关于升级 |

---

## 四、蒸馏流程

### 4.1 触发模式

| 模式 | 命令 | 说明 |
|------|------|------|
| Heartbeat | `python3 -m memory.automation heartbeat` | 定时触发，写入 pending_queue |
| Manual | `python3 -m memory.automation manual` | 关键词触发，直接蒸馏 |
| 指定 Session | `python3 -m memory.automation manual --session <file>` | 处理指定 session 文件 |

### 4.2 蒸馏优先级

```
1. LLM 蒸馏（config.json 有 api_key）
   ↓ 失败
2. Regex 蒸馏（fallback）
```

### 4.3 LLM 蒸馏流程

```
1. 格式化消息为 prompt
2. 调用 MiniMax API（MiniMax-M2.7）
3. 解析 JSON 响应
4. 提取 DistilledItem 列表
```

### 4.4 Regex 蒸馏流程

```
1. 遍历预定义模式（event/decision/preference/emotion/action）
2. 使用 re.search 匹配
3. 提取匹配内容
4. 构建 DistilledItem
```

### 4.5 写入流程

```
1.蒸馏结果 → message_processor
2.按日期分组 → l1_writer.write()
3.追加到 memory/YYYY-MM-DD.md
```

---

## 五、Agent 隔离机制

### 5.1 Session 隔离

每个 Agent 的 session 存储在独立目录：

```
~/.openclaw/agents/{workspace_id}/sessions/
├── <session1>.jsonl
├── <session2>.jsonl
└── <session1>.jsonl.reset.<timestamp>
```

### 5.2 Memory 隔离

每个 Agent 的记忆存储在独立 workspace：

```
~/.openclaw/workspaces/{workspace_id}/workspace/memory/
├── 2026-03-28.md
├── 2026-03-29.md
└── Patterns.md
```

### 5.3 Agent ID 检测

`_detect_agent_id()` 优先级：
1. 环境变量 `OPENCLAW_AGENT_ID`
2. Workspace 路径推断
3. Session 目录推断
4. Config 默认值
5. Fallback `"code"`

---

## 六、状态管理

### 6.1 State 文件

```
~/.openclaw/agents/{workspace_id}/sessions/.session_state
```

### 6.2 状态内容

```json
{
  "last_session_key": "xxx",
  "last_processed_msg_id": "om_xxx",
  "last_processed_at": "2026-03-29T12:00:00Z",
  "regex_count": 5,
  "is_processing_old_session": false
}
```

### 6.3 Session 切换检测

当 `last_session_key != current_session_key` 时：
1. 先处理旧 session 的未蒸馏消息
2. 标记 `is_processing_old_session = true`
3. 处理完成后取消标记

---

## 七、API Key 管理

### 7.1 首次激活流程

```
用户说"请使用 memory-automation"
    ↓
脚本检测 api_key == null
    ↓
输出 "[MEMORY-AUTOMATION] API_KEY: not_configured"
    ↓
设置 api_key_asked = true
    ↓
Agent 询问用户是否提供 API Key
```

### 7.2 API Key 更新

用户可以直接提供新 Key，Agent 会更新 config.json。

### 7.3 Regex 升级机制

当 regex 蒸馏次数达到 30 次时：
```
输出 "[MEMORY-AUTOMATION] REGEX_LIMIT_REACHED"
Agent 主动询问用户是否升级到 LLM
```

---

## 八、已知问题

### 8.1 Issue #12（待修复）

**L1 时间戳使用 datetime.now() 而非 session 原始时间**

- 影响：蒸馏结果的时间是「写入时间」而非「实际发生时间」
- 修复方案：L1 writer 接受 session 时间范围参数

---

## 九、待办事项

### 9.1 Agent 自蒸馏架构（长期目标）

**目标**：实现 Agent 用自己的 model 能力蒸馏，而非 Python 调 API

**现状**：
- 当前：Python 调 MiniMax API
- 目标：Agent 用 OpenClaw 自己的 model 蒸馏

**需要**：
1. 设计消息协议（Python 如何触发 Agent 蒸馏）
2. Agent 系统支持（Agent 收到触发后执行蒸馏）

**状态**：待设计

---

## 十、更新日志

| 日期 | 内容 |
|------|------|
| 2026-03-29 | 初始版本 |
| 2026-03-29 | 添加 LLM 蒸馏支持（MiniMax-M2.7） |
| 2026-03-29 | 添加 API Key 配置流程 |
| 2026-03-29 | 添加 Regex 升级机制（30 次询问） |
| 2026-03-29 | 修复 session_manager hardcoded "code" 问题 |
| 2026-03-29 | 添加 `--session` 参数支持处理指定 session |
