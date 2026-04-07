"""
L2 写入模块 - 统一的 L2 写入接口

现在 L2 统一使用三文件结构（corrections.md / patterns.md / insights.md）
本模块提供兼容性封装，实际写入由 l2_extraction 处理
"""

from typing import Dict, List, Optional

# 导入 l2_extraction 的核心函数
from .l2_extraction import (
    add_correction,
    add_or_update_pattern,
    add_insight,
    get_corrections,
    get_patterns,
    get_insights,
)


class L2Writer:
    """
    L2 写入器 - 兼容层
    
    实际写入操作委托给 l2_extraction 模块，确保统一使用三文件结构：
    - corrections.md: 纠正记录
    - patterns.md: 行为模式
    - insights.md: 洞察原则
    """
    
    def __init__(self, agent_id: str, l2_path: Optional[str] = None):
        """
        初始化 L2 写入器
        
        Args:
            agent_id: Agent ID（必需）
            l2_path: 保留参数用于兼容，实际不使用（路径由 l2_extraction 决定）
        
        Raises:
            ValueError: 如果 agent_id 为空
        """
        if not agent_id:
            raise ValueError("agent_id 是必需的，不能为空")
        self.agent_id = agent_id
    
    def add_correction(self, content: str, source: str = "self", context: str = "") -> bool:
        """添加纠正记录到 corrections.md"""
        return add_correction(self.agent_id, content, source, context)
    
    def add_pattern(self, pattern_key: str, description: str, examples: List[str] = None) -> bool:
        """添加/更新 pattern 到 patterns.md"""
        return add_or_update_pattern(self.agent_id, pattern_key, description, examples)
    
    def add_insight(self, title: str, principle: str, status: str = "pending", 
                   related_patterns: List[str] = None) -> bool:
        """添加洞察到 insights.md"""
        return add_insight(self.agent_id, title, principle, status, related_patterns)
    
    def get_all_patterns(self) -> List[Dict]:
        """获取所有 patterns"""
        return get_patterns(self.agent_id)
    
    def get_all_insights(self, status: Optional[str] = None) -> List[Dict]:
        """获取所有 insights，可按状态过滤"""
        return get_insights(self.agent_id, status)
    
    # 保留旧接口用于兼容，但标记为 deprecated
    def append_tag(self, tag_name: str, stats: dict) -> bool:
        """
        [兼容性接口] 将标签作为 pattern 写入
        
        这是 L1→L2 提升的入口，将 L1 标签提升为 L2 pattern
        """
        description = f"从 L1 提升的标签，出现 {stats.get('count', 1)} 次"
        examples = [f"来源: {s}" for s in stats.get('sources', [])]
        return self.add_pattern(tag_name, description, examples)
    
    def tag_exists(self, tag_name: str) -> bool:
        """检查 pattern 是否已存在"""
        patterns = get_patterns(self.agent_id)
        return any(p.get('key') == tag_name for p in patterns)
