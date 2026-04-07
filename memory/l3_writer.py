"""
L3 写入模块 - 长期记忆管理

负责将 verified insights 和稳定 patterns 提升到 L3 (~/self-improving/memory.md)
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from .l2_extraction import get_insights, get_patterns, L2_DIR


class L3Writer:
    """
    L3 长期记忆写入器
    
    L3 存储位置: ~/self-improving/memory.md
    
    结构：
    - Verified Insights: 已验证的原则（来自 insights.md）
    - Consolidated Patterns: 稳定的行为模式（来自 patterns.md）
    - Archive: 归档内容
    """
    
    DEFAULT_L3_PATH = "~/self-improving/memory.md"
    
    # 升级阈值配置
    THRESHOLDS = {
        "insight_verified": {"min_count": 3, "min_days": 7},
        "pattern_stable": {"min_count": 5, "min_days": 30},
        "l1_tag": {"min_count": 7, "min_days": 7}
    }
    
    def __init__(self, agent_id: str, l3_path: Optional[str] = None):
        """
        初始化 L3 写入器
        
        Args:
            agent_id: Agent ID（必需，用于检查 L2 数据）
            l3_path: 可选的自定义 L3 路径
        """
        if not agent_id:
            raise ValueError("agent_id 是必需的")
        
        self.agent_id = agent_id
        self.l3_path = Path(l3_path or self.DEFAULT_L3_PATH).expanduser()
        self.l2_dir = Path(L2_DIR.format(agent_id=agent_id)).expanduser()
        
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
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """解析日期字符串"""
        formats = ["%Y-%m-%d", "%Y-%m-%d %H:%M"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None
    
    def _days_since(self, date_str: str) -> int:
        """计算从日期到现在经过的天数"""
        dt = self._parse_date(date_str)
        if not dt:
            return 0
        return (datetime.now() - dt).days
    
    def check_insight_promotable(self, insight: dict) -> tuple[bool, str]:
        """
        检查 insight 是否可以提升到 L3
        
        Returns:
            (是否可以提升, 原因)
        """
        status = insight.get('status', '')
        if status != 'verified':
            return False, f"status={status} (需要 verified)"
        
        created = insight.get('created', '')
        days = self._days_since(created)
        min_days = self.THRESHOLDS["insight_verified"]["min_days"]
        
        if days < min_days:
            return False, f"仅 {days} 天 (需要 >= {min_days} 天)"
        
        return True, f"符合提升条件 ({days} 天)"
    
    def check_pattern_promotable(self, pattern: dict) -> tuple[bool, str]:
        """检查 pattern 是否可以提升到 L3"""
        count = pattern.get('count', 0)
        min_count = self.THRESHOLDS["pattern_stable"]["min_count"]
        
        if count < min_count:
            return False, f"count={count} (需要 >= {min_count})"
        
        created = pattern.get('created', '')
        days = self._days_since(created)
        min_days = self.THRESHOLDS["pattern_stable"]["min_days"]
        
        if days < min_days:
            return False, f"仅 {days} 天 (需要 >= {min_days} 天)"
        
        return True, f"符合提升条件 (count={count}, {days} 天)"
    
    def _section_exists(self, content: str, title: str) -> bool:
        """检查 L3 中是否已存在该条目"""
        # 匹配 ### 标题
        pattern = rf'### \d{{4}}-\d{{2}}-\d{{2}}: {re.escape(title)}\n'
        return bool(re.search(pattern, content))
    
    def promote_insight(self, insight: dict, dry_run: bool = False) -> bool:
        """
        将 insight 提升到 L3
        
        Args:
            insight: insight 字典
            dry_run: 仅模拟，不实际写入
        """
        can_promote, reason = self.check_insight_promotable(insight)
        if not can_promote:
            print(f"  [跳过] {insight.get('title', 'Unknown')}: {reason}")
            return False
        
        title = insight.get('title', '')
        principle = insight.get('principle', '')
        created = insight.get('created', datetime.now().strftime('%Y-%m-%d'))
        
        if dry_run:
            print(f"  [模拟提升] {title}")
            return True
        
        # 确保结构
        content = self._ensure_l3_structure()
        
        # 检查是否已存在
        if self._section_exists(content, title):
            print(f"  [已存在] {title}")
            return False
        
        # 构建条目
        entry = f"""### {datetime.now().strftime('%Y-%m-%d')}: {title}
- **来源**: insights.md (verified)
- **原则**: {principle}
- **置信度**: high
- **首次记录**: {created}
- **验证日期**: {datetime.now().strftime('%Y-%m-%d')}

"""
        
        # 插入到 Verified Insights 章节
        content = self.l3_path.read_text(encoding='utf-8')
        section_marker = "## Verified Insights\n"
        pos = content.find(section_marker)
        if pos >= 0:
            insert_pos = pos + len(section_marker)
            new_content = content[:insert_pos] + "\n" + entry + content[insert_pos:]
            self.l3_path.write_text(new_content, encoding='utf-8')
            print(f"  [已提升] {title}")
            return True
        
        return False
    
    def promote_pattern(self, pattern: dict, dry_run: bool = False) -> bool:
        """将 pattern 提升到 L3"""
        can_promote, reason = self.check_pattern_promotable(pattern)
        if not can_promote:
            print(f"  [跳过] {pattern.get('key', 'Unknown')}: {reason}")
            return False
        
        key = pattern.get('key', '')
        description = pattern.get('description', '')
        count = pattern.get('count', 0)
        created = pattern.get('created', datetime.now().strftime('%Y-%m-%d'))
        
        if dry_run:
            print(f"  [模拟提升] {key}")
            return True
        
        content = self._ensure_l3_structure()
        
        if self._section_exists(content, key):
            print(f"  [已存在] {key}")
            return False
        
        entry = f"""### {datetime.now().strftime('%Y-%m-%d')}: {key}
- **来源**: patterns.md
- **描述**: {description}
- **出现次数**: {count}
- **首次记录**: {created}
- **稳定性**: {self._days_since(created)} 天
- **标签**: #{key}

"""
        
        content = self.l3_path.read_text(encoding='utf-8')
        section_marker = "## Consolidated Patterns\n"
        pos = content.find(section_marker)
        if pos >= 0:
            insert_pos = pos + len(section_marker)
            new_content = content[:insert_pos] + "\n" + entry + content[insert_pos:]
            self.l3_path.write_text(new_content, encoding='utf-8')
            print(f"  [已提升] {key}")
            return True
        
        return False
    
    def run_promotion(self, dry_run: bool = False) -> dict:
        """
        运行完整的 L2→L3 提升流程
        
        Returns:
            {"insights_promoted": int, "patterns_promoted": int}
        """
        print(f"\n{'='*60}")
        print(f"[L2→L3] 开始提升检查")
        print(f"  Agent: {self.agent_id}")
        print(f"  L3 路径: {self.l3_path}")
        print(f"  模式: {'模拟' if dry_run else '实际'}")
        print(f"{'='*60}\n")
        
        # 确保结构
        if not dry_run:
            self._ensure_l3_structure()
        
        results = {"insights_promoted": 0, "patterns_promoted": 0}
        
        # 1. 提升 verified insights
        print("[1/2] 检查 Verified Insights...")
        insights = get_insights(self.agent_id, status='verified')
        print(f"  找到 {len(insights)} 个 verified insights")
        
        for insight in insights:
            if self.promote_insight(insight, dry_run=dry_run):
                results["insights_promoted"] += 1
        
        # 2. 提升稳定 patterns
        print("\n[2/2] 检查稳定 Patterns...")
        patterns = get_patterns(self.agent_id)
        print(f"  找到 {len(patterns)} 个 patterns")
        
        for pattern in patterns:
            if self.promote_pattern(pattern, dry_run=dry_run):
                results["patterns_promoted"] += 1
        
        # 总结
        print(f"\n{'='*60}")
        print(f"[L2→L3] 完成")
        print(f"  Insights 提升: {results['insights_promoted']}")
        print(f"  Patterns 提升: {results['patterns_promoted']}")
        print(f"{'='*60}\n")
        
        return results
