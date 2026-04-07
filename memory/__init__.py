"""
Memory Automation Skill - 分层记忆管理模块

统一四层架构：
- L0: Session 原始记录
- L1: 每日日志（Event/Decision/Preference/Improve/To-do/Output/Emotion）
- L2: 自我改进层（corrections → patterns → insights）
- L3: 长期记忆（verified insights）
"""

__version__ = "2.0.0"
__author__ = "OpenClaw"

# 核心模块
from .session_manager import SessionManager
from .session_distiller import SessionDistiller
from .automation import MemoryAutomation
from .tag_analyzer import TagAnalyzer
from .l2_writer import L2Writer
from .l1_to_l2 import L1ToL2Promoter

# L2 子模块（从 l2-extraction 整合）
from .l2_extraction import (
    add_correction, get_corrections,
    add_or_update_pattern, get_patterns, process_patterns_from_corrections,
    add_insight, update_insight_status, get_insights,
    L2_DIR, CORRECTIONS_FILE, PATTERNS_FILE, INSIGHTS_FILE
)

__all__ = [
    # 核心
    "SessionManager",
    "SessionDistiller", 
    "MemoryAutomation",
    "TagAnalyzer",
    "L2Writer",
    "L1ToL2Promoter",
    # L2 实时改进
    "add_correction",
    "get_corrections",
    "add_or_update_pattern",
    "get_patterns",
    "process_patterns_from_corrections",
    "add_insight",
    "update_insight_status",
    "get_insights",
    # L2 常量
    "L2_DIR",
    "CORRECTIONS_FILE",
    "PATTERNS_FILE",
    "INSIGHTS_FILE",
]
