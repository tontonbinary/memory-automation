"""
L2 Extraction Module - Self-improving layer
整合进 memory-automation: corrections -> patterns

L2 统一架构：
- L0: Session 原始记录 → L2 (实时纠正)
- L1: 每日日志 → L2 (定期提升)
- L2: 自我改进层 (corrections/patterns/insights)
  - insights 不再由代码自动生成，改由 Agent 主动调用 LLM 从 patterns 提炼后写入 insights.md
- L3: 长期记忆 (由 L3Consolidator 自动整合，或 Agent 手动写入 MEMORY.md)

格式：
- corrections.jsonl: JSON Lines 格式（兼容 self-improving-agent）
- patterns.md: Markdown 格式
- insights.md: Markdown 格式（Agent 手动维护）
"""

__version__ = "2.1.0"

# Corrections (JSON Lines 格式)
from .corrections import (
    add_correction,
    get_corrections,
    get_correction_topics,
    search_corrections,
    get_high_frequency_corrections,
    add_correction_legacy,  # 兼容旧接口
    get_l2_dir as _get_corrections_dir,
)

# Patterns (Markdown 格式)
from .patterns import (
    add_or_update_pattern,
    get_patterns,
    process_patterns_from_corrections,
    get_high_confidence_patterns,
    get_l2_dir as _get_patterns_dir,
)

# Insights (Markdown 格式，Agent 手动维护)
from .insights_writer import (
    add_insight,
    get_insights,
    get_l2_dir as _get_insights_dir,
)


# 统一的 L2 目录获取函数
def get_l2_dir(agent_id: str) -> str:
    """获取指定 agent 的 L2 目录路径"""
    return _get_corrections_dir(agent_id)


# L2 存储路径（与 memory-automation 统一）
L2_DIR = "~/.openclaw/workspaces/{agent_id}/workspace/memory/L2"
CORRECTIONS_FILE = "corrections.jsonl"
PATTERNS_FILE = "patterns.md"
INSIGHTS_FILE = "insights.md"


__all__ = [
    # Corrections (JSON Lines)
    "add_correction",
    "get_corrections",
    "get_correction_topics",
    "search_corrections",
    "get_high_frequency_corrections",
    "add_correction_legacy",
    # Patterns (Markdown)
    "add_or_update_pattern",
    "get_patterns",
    "get_high_confidence_patterns",
    "process_patterns_from_corrections",
    # Insights (Markdown, Agent 手动维护)
    "add_insight",
    "get_insights",
    # Utils
    "get_l2_dir",
    # Constants
    "L2_DIR",
    "CORRECTIONS_FILE",
    "PATTERNS_FILE",
    "INSIGHTS_FILE",
]
