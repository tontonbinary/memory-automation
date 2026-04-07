"""
L2 Extraction Module - Self-improving layer
整合进 memory-automation: corrections -> patterns -> insights

L2 统一架构：
- L0: Session 原始记录 → L2 (实时纠正)
- L1: 每日日志 → L2 (定期提升)
- L2: 自我改进层 (corrections/patterns/insights)
- L3: 长期记忆 (verified insights → MEMORY.md)
"""

__version__ = "1.0.0"

from .corrections import add_correction, get_corrections
from .patterns import add_or_update_pattern, get_patterns, process_patterns_from_corrections
from .insights import add_insight, update_insight_status, get_insights

# L2 存储路径（与 memory-automation 统一）
L2_DIR = "~/.openclaw/workspaces/{agent_id}/workspace/memory/L2"
CORRECTIONS_FILE = "corrections.md"
PATTERNS_FILE = "patterns.md"
INSIGHTS_FILE = "insights.md"
