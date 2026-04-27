# 记忆规则 (Memory Rules)

## L1 存储规范（新格式）

### 文件位置
- **全局路径模板**: `~/.openclaw/workspaces/{agent}/workspace/memory/YYYY-MM-DD.md`
- **按日期分文件**: 每天一个文件，便于管理和检索
- **写入者**: Agent 主动总结写入（不再由脚本自动蒸馏）

### 文件格式

```markdown
# Memory Log - 2026-04-27

## 索引
| CoreWork | Mauto简化 |
|----------|----------|
| SocialEcology | 偏好简洁 |
| To-do | 凌晨提醒 |
| Output | L1新格式 |

---

## CoreWork
用户要求简化 Mauto：去除 L3 auto-dream，L1 改为 agent 主动提炼

## EventsOutside
（空）

## SocialEcology
用户偏好简洁日志格式

## SelfEvolve
（空）

## RuleDecision
（空）

## To-do
每天凌晨 03:00-04:00 提醒总结前一日 clean_session

## Output
实现了新的 L1 格式：7 分类，索引 8 字摘要
```

### 格式规则

**7 分类（固定顺序）**：
1. CoreWork - 本职核心业务
2. EventsOutside - 临时辅助、无重要成果
3. SocialEcology - 用户关系/组织/环境规律
4. SelfEvolve - 知识/纠错/习惯养成
5. RuleDecision - 硬性规则、流程、约束
6. To-do - 待办、承诺、需遵守事项
7. Output - 产出物（含储存路径）

**索引**：
- 只出现有内容的分类
- 每个分类一行，8 字以内摘要
- 无内容的分类不出现

**正文**：
- 7 个分类都要写
- 无内容写 `（空）`
- 内容 = 事实本身，不是摘要

## Clean Session 规范

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

## Heartbeat 行为

Heartbeat 现在只做：
1. 检测 session 切换 → 保存旧 session 的 clean_session
2. 检查积压 session → 保存积压的 clean_session
3. 处理当前 session → 清洗消息 → 保存 clean_session
4. 凌晨 03:00-04:00 检查是否需要提醒总结前一日

**不再做**：
- ❌ 不调用 LLM API 蒸馏
- ❌ 不自动写入 L1
- ❌ 不触发 L3 Auto-Dream

## 凌晨总结提醒

触发条件：
- 当前时间在 03:00-04:00 之间
- 前一日有 clean_session 文件
- 前一日没有 L1 文件（或 L1 为空）

提醒内容：
```
📅 凌晨总结提醒 (2026-04-26)
检测到昨日有 clean_session 文件，但 L1 日志尚未写入。
建议读取 clean_session 并总结写入 L1。
```

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
