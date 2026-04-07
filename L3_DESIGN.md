# L1→L3 自动提升设计

## 目标
实现从 L1/L2 到 L3（长期记忆）的自动提升

## 架构

```
L1 (每日日志) ──┬──→ L2 (patterns/insights) ──→ L3 (长期记忆)
                │
                └──→ 直接分析 ────┘

L3 存储: ~/self-improving/memory.md
```

## 触发方式

1. **定期触发**: 通过 HEARTBEAT 或 cron (每天 04:00，避开 Auto-Dream)
2. **手动触发**: `python -m memory.automation l3 promote --agent <id>`
3. **阈值触发**: insights status=verified 且 count>=3

## 实现方案

### 方案 A: 调用 auto-dream（推荐）
- 复用现有 auto-dream skill
- memory-automation 提供数据接口
- auto-dream 负责 L3 写入

### 方案 B: 内置 L3 提升
- memory-automation 自行实现 L3 写入
- 优点：控制更灵活
- 缺点：与 auto-dream 可能冲突

## 数据结构

### L3 文件格式 (~/self-improving/memory.md)

```markdown
# Memory (L3 - Long-term)

> Auto-generated from L1/L2 via memory-automation

## Verified Insights

### 2026-04-07: 优先澄清需求
- **来源**: insights.md (verified)
- **原则**: 在给出方案前，先确认用户真实需求
- **置信度**: high (出现 5 次)
- **首次记录**: 2026-03-15
- **最后验证**: 2026-04-07

## Consolidated Patterns

### 2026-04-07: 工作流程偏好
- **来源**: patterns.md
- **描述**: 用户偏好先讨论架构再写代码
- **关联**: #architecture-first
- **稳定性**: 3个月+

## Archive
- 2026-03: [归档摘要]
```

## 升级规则

| 来源 | 条件 | 目标 L3 章节 |
|------|------|-------------|
| insights.md (verified) | status=verified, count>=3 | Verified Insights |
| patterns.md | count>=5, 持续1个月+ | Consolidated Patterns |
| L1 高频标签 | 出现>=7次, 跨7天+ | Consolidated Patterns |

## 接口设计

```python
# memory/l3_writer.py
class L3Writer:
    def promote_insight(self, insight: dict) -> bool
    def promote_pattern(self, pattern: dict) -> bool
    def consolidate_l1_tags(self, tags: list) -> bool

# memory/automation.py
# 新增子命令
python -m memory.automation l3 promote --agent <id>
python -m memory.automation l3 status --agent <id>
```

## 与 auto-dream 的关系

- 如果 auto-dream 已安装：调用 auto-dream API
- 如果 auto-dream 未安装：使用内置 L3 写入
- 避免重复：检查 auto-dream 是否存在
