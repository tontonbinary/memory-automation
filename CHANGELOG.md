# Changelog

所有版本更新记录。

---

## [1.1.0] - 2026-03-30

### 核心重构

#### L0→L1 蒸馏规则重构（7类）
- **session_distiller.py**: 新 prompt 模板，7类记忆类型
  - Event / Decision / Preference / Improve / Action / Oput / Emotion
  - 新字段：`action`（后续行动）、`oput`（成果）、`improve`（纠正）
  - 移除旧字段：`follow_up`、`outcome`
- **prompt 输出格式**：`{"items": [{"type": "...", "content": "...", "source_idx": N}]}`
- **`source_idx` 机制**：prompt 中消息带 `[1] [2] [3]` 序号，LLM 返回每条记忆对应的消息序号，写入时直接查真实时间戳

#### L0→L1 写入重构
- **l1_writer.py**:
  - 新文件写入 `# 时区: Asia/Shanghai (UTC+8)` 头部
  - 跨时区追加时在内容开头插入 `# 时区变更: UTC` 标记
  - 来源格式改为 `session/MM-DD#L行号`
- **message_processor.py**:
  - 移除 `_compute_item_times` 相似度匹配（Jaccard threshold 问题）
  - 改用 `source_idx` 直接查时间：`messages[source_idx - 1].timestamp`

### Bug Fix

- **toolResult 污染根因** (`session_manager.py`)
  - 读消息时过滤 `role=toolResult`
  - 之前 toolResult 的原始内容被当作对话送进蒸馏 prompt
- **msg_id 一致性容错** (`session_manager.py`)
  - `last_processed_msg_id` 在 session 文件切换后找不到时退化为全量处理，避免死过滤
- **时区转换** (`l1_writer.py`)
  - `session_start_time` 从 UTC 转换到 Asia/Shanghai
  - 加 `try/except ImportError` 兜底（zoneinfo 不可用时用 `timedelta(hours=8)`）

### 新文件

- `CHANGELOG.md` - 版本更新记录

### breaking change

- `DistilledItem` dataclass 字段变更
  - 移除：`follow_up`、`outcome`
  - 新增：`action`、`oput`、`improve`、`source_idx`
  - 外部引用需同步更新

### 建议关注（暂未修改）

- **Jaccard 相似度阈值 0.02** (`message_processor.py`)
  - `_compute_item_times` 已移除，但如后续改回相似度方案，阈值建议提升到 0.05
- **msg_id 容错退化逻辑**
  - 当前退化为全量处理，可进一步优化为跨 session 连续性匹配

---

## [1.0.0] - 2026-03-29

初始版本。
