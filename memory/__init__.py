"""
Memory Automation Skill - 分层记忆管理模块

统一四层架构：
- L0: Session 原始记录
- L1: 每日日志（Event/Preference/To-do/Output/Emotion）
- L2: 自我改进层（corrections → patterns → insights）
  - insights 不再由代码自动生成，改由 Agent 主动调用 LLM 从 patterns 提炼后写入 insights.md
- L3: 长期记忆（由 L3Consolidator 自动整合，或 Agent 手动写入 MEMORY.md）
"""

__version__ = "2.1.0"
__author__ = "OpenClaw"

# 核心模块
from .session_manager import SessionManager
from .session_distiller import SessionCleaner
from .automation import MemoryAutomation

# L2 子模块（从 l2-extraction 整合，可选加载）
try:
    from .l2_extraction import (
        add_correction,
        get_corrections,
        add_or_update_pattern,
        get_patterns,
        process_patterns_from_corrections,
        add_insight,
        get_insights,
        L2_DIR,
        CORRECTIONS_FILE,
        PATTERNS_FILE,
        INSIGHTS_FILE,
    )
except (ImportError, ModuleNotFoundError):
    # l2_extraction 模块暂不可用，定义为 None 备用
    add_correction = None
    get_corrections = None
    add_or_update_pattern = None
    get_patterns = None
    process_patterns_from_corrections = None
    add_insight = None
    get_insights = None
    L2_DIR = None
    CORRECTIONS_FILE = None
    PATTERNS_FILE = None
    INSIGHTS_FILE = None



__all__ = [
    # 核心
    "SessionManager",
    "SessionCleaner",
    "MemoryAutomation",
    # L2 实时改进
    "add_correction",
    "get_corrections",
    "add_or_update_pattern",
    "get_patterns",
    "process_patterns_from_corrections",
    "add_insight",
    "get_insights",
    # L2 常量
    "L2_DIR",
    "CORRECTIONS_FILE",
    "PATTERNS_FILE",
    "INSIGHTS_FILE",
]
