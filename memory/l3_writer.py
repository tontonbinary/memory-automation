"""
L3 写入模块 - 长期记忆管理

L3 存储位置: ~/.openclaw/workspaces/{agent}/workspace/MEMORY.md

功能：
1. 基础 L3 文件操作
2. 与 L3Consolidator 配合完成 L1→L3 整合
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class L3Writer:
    """
    L3 长期记忆写入器
    
    配合 L3Consolidator 完成 L1→L3 整合流程
    """
    
    @staticmethod
    def get_l3_path(agent_id: str) -> Path:
        """获取 L3 文件路径（agent 隔离）"""
        return Path(f"~/.openclaw/workspaces/{agent_id}/workspace/MEMORY.md").expanduser()
    
    def __init__(self, agent_id: str, l3_path: Optional[str] = None):
        """
        初始化 L3 写入器
        
        Args:
            agent_id: Agent ID
            l3_path: 可选的自定义 L3 路径（默认使用 agent 隔离路径）
        """
        self.agent_id = agent_id
        self.l3_path = Path(l3_path) if l3_path else self.get_l3_path(agent_id)
        
        # 确保目录存在
        self.l3_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _ensure_l3_structure(self) -> str:
        """确保 L3 文件有正确的结构"""
        if not self.l3_path.exists():
            header = f"""# Memory (L3 - Long-term)

> Auto-generated from L1/L2 via memory-automation
> Agent: {self.agent_id}
> Created: {datetime.now().strftime('%Y-%m-%d')}

## Verified Insights

## Consolidated Patterns

## Archive

"""
            self.l3_path.write_text(header, encoding='utf-8')
            return header
        
        content = self.l3_path.read_text(encoding='utf-8')
        
        # 检查并添加缺失的章节
        sections = ["## Verified Insights", "## Consolidated Patterns", "## Archive"]
        for section in sections:
            if section not in content:
                content += f"\n{section}\n\n"
        
        self.l3_path.write_text(content, encoding='utf-8')
        return content
    
    def get_status(self) -> dict:
        """
        获取 L3 文件状态
        
        Returns:
            {"exists": bool, "path": str, "entry_count": int}
        """
        exists = self.l3_path.exists()
        entry_count = 0
        
        if exists:
            content = self.l3_path.read_text(encoding='utf-8')
            # 简单统计 ### 开头的条目数
            entry_count = len(re.findall(r'^### ', content, re.MULTILINE))
        
        return {
            "exists": exists,
            "path": str(self.l3_path),
            "entry_count": entry_count
        }
    
    def add_entry(self, section: str, title: str, content_lines: List[str]) -> bool:
        """
        添加条目到 L3（基础接口）
        
        Args:
            section: 章节名（如 "Verified Insights", "Consolidated Patterns"）
            title: 条目标题
            content_lines: 内容行列表
            
        Returns:
            是否成功
        """
        # 确保结构
        l3_content = self._ensure_l3_structure()
        
        # 检查是否已存在
        if re.search(rf'^### .*?: {re.escape(title)}$', l3_content, re.MULTILINE):
            return False
        
        # 构建条目
        date_str = datetime.now().strftime('%Y-%m-%d')
        entry_lines = [f"### {date_str}: {title}"]
        entry_lines.extend(content_lines)
        entry_lines.append("")
        entry_text = "\n".join(entry_lines)
        
        # 插入到指定章节
        section_marker = f"## {section}\n"
        pos = l3_content.find(section_marker)
        if pos >= 0:
            insert_pos = pos + len(section_marker)
            new_content = l3_content[:insert_pos] + "\n" + entry_text + l3_content[insert_pos:]
            self.l3_path.write_text(new_content, encoding='utf-8')
            return True
        
        return False
    
    # ============================================================
    # 以下接口已禁用（保留供将来重新实现）
    # ============================================================
    
    def run_promotion(self, dry_run: bool = False) -> dict:
        """
        [已禁用] L2→L3 自动提升流程
        
        此功能当前已禁用，仅返回空结果。
        将来会重新设计 L1/L2 → L3 的提升逻辑。
        
        Returns:
            {"insights_promoted": 0, "patterns_promoted": 0, "disabled": True}
        """
        print("[L3Writer] L2→L3 自动提升已禁用，等待重新设计")
        return {
            "insights_promoted": 0,
            "patterns_promoted": 0,
            "disabled": True,
            "message": "L2→L3 promotion is disabled, will be redesigned"
        }
    
    def check_insight_promotable(self, insight: dict) -> tuple:
        """[已禁用] 检查 insight 是否可提升"""
        return False, "Function disabled"
    
    def check_pattern_promotable(self, pattern: dict) -> tuple:
        """[已禁用] 检查 pattern 是否可提升"""
        return False, "Function disabled"
    
    def promote_insight(self, insight: dict, dry_run: bool = False) -> bool:
        """[已禁用] 提升 insight 到 L3"""
        print("[L3Writer] promote_insight is disabled")
        return False
    
    def promote_pattern(self, pattern: dict, dry_run: bool = False) -> bool:
        """[已禁用] 提升 pattern 到 L3"""
        print("[L3Writer] promote_pattern is disabled")
        return False
