# 记忆规则 (Memory Rules)

## L1 存储规范（新格式）

### 文件位置
- **全局路径模板**: `~/.openclaw/workspaces/{agent}/workspace/memory/YYYY-MM-DD.md`
- **按日期分文件**: 每天一个文件，便于管理和检索
- **写入者**: Agent 主动总结写入（不再由脚本自动蒸馏）

### 文件格式

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

### 格式规则

**标签索引**：
- 只保留「记忆标签」和「事件类型」两列
- 去重：同一标签+事件类型组合只出现一次
- 不记录时间和内容标签

**正文**：
- 按 `## 事件类型` 分组（5类：CoreWork, EventsOutside, SelfEvolve, SocialEcology, RuleDecision）
- 每条格式：`- [记忆标签] 内容摘要`
- 内容要提炼要点，不要复述对话

### 记忆标签（5类）
| 标签 | 说明 |
|------|------|
| Event | 客观事实、问题、需求、踩坑 |
| Preference | 用户偏好、习惯、忌讳 |
| To-do | 待办、承诺、需遵守事项 |
| Output | 产出物 |
| Emotion | 只记积极/负面（附加在其他标签上，不单独成条） |

### 事件类型（5维）
| 类型 | 说明 |
|------|------|
| CoreWork | 本职核心业务 |
| EventsOutside | 临时辅助、无重要成果 |
| SelfEvolve | 知识/纠错/习惯养成 |
| SocialEcology | 用户关系/组织/环境规律 |
| RuleDecision | 硬性规则、流程、约束 |

## Clean Session 规范

### 文件位置
- **目录**: `~/.openclaw/agents/{agent_id}/clean_session/`
- **文件名**: `{MMDD}#L{N}.json`（如 `0427#L1.json`）

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

## Heartbeat 行为

Heartbeat 现在只做：
1. 检测 session 切换 → 保存旧 session 的 clean_session
2. 检查积压 session → 保存积压的 clean_session
3. 处理当前 session → 清洗消息 → 保存 clean_session

**不再做**：
- ❌ 不调用 LLM API 蒸馏
- ❌ 不自动写入 L1
- ❌ 不触发 L3 Auto-Dream

## L2 层（保持不变）

L2 机制继续保留，由 Agent 手动维护：
- `corrections.jsonl` - 纠正记录
- `patterns.md` - 行为模式
- `insights.md` - 洞察原则

## L3 层（已删除）

L3 Auto-Dream 功能已移除：
- ❌ 不再自动整合 L1 到 MEMORY.md
- ❌ 不再生成整合报告
- MEMORY.md 改由 Agent 手动维护（如需）
