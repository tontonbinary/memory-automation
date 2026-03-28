"""
标签统计与分析模块 - 分析 L1 记忆文件中的标签使用情况
"""

import re
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set


class TagAnalyzer:
    """分析 L1 记忆文件中的标签统计信息"""
    
    # 默认 L1 路径模板
    L1_PATH_TEMPLATE = "~/.openclaw/workspaces/{agent}/workspace/memory"
    
    # 标签正则表达式 - 匹配 #标签名 格式
    TAG_PATTERN = re.compile(r'#([^\s#]+)')
    
    def __init__(self, agent_id: str = "code", l1_path: Optional[str] = None):
        """
        初始化标签分析器
        
        Args:
            agent_id: Agent ID，用于构建默认 L1 路径
            l1_path: 自定义 L1 路径，覆盖默认模板
        """
        if l1_path:
            self.l1_base_path = Path(l1_path).expanduser()
        else:
            self.l1_base_path = Path(
                self.L1_PATH_TEMPLATE.format(agent=agent_id)
            ).expanduser()
    
    def find_memory_files(self, days_back: int = 7) -> List[Path]:
        """
        查找指定天数内的记忆文件
        
        Args:
            days_back: 回溯天数，默认7天（一周）
            
        Returns:
            记忆文件路径列表
        """
        if not self.l1_base_path.exists():
            print(f"[TagAnalyzer] L1 路径不存在: {self.l1_base_path}")
            return []
        
        # 获取今天日期
        today = datetime.now()
        files = []
        
        # 遍历最近 N 天的文件
        for i in range(days_back):
            date = today - __import__('datetime').timedelta(days=i)
            filename = date.strftime("%Y-%m-%d") + ".md"
            filepath = self.l1_base_path / filename
            
            if filepath.exists():
                files.append(filepath)
        
        # 按日期排序（旧的在前）
        files.sort()
        return files
    
    def extract_tags_from_file(self, filepath: Path) -> Dict[str, List[str]]:
        """
        从单个文件中提取标签及其上下文
        
        Args:
            filepath: 记忆文件路径
            
        Returns:
            标签到来源行列表的映射
        """
        tags = defaultdict(list)
        date_str = filepath.stem  # 文件名即日期 (YYYY-MM-DD)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except (IOError, UnicodeDecodeError) as e:
            print(f"[TagAnalyzer] 读取文件失败 {filepath}: {e}")
            return dict(tags)
        
        # 查找所有标签行
        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            # 查找 **标签**：或 **标签**: 格式
            if '**标签**' in line or '- 标签：' in line:
                found_tags = self.TAG_PATTERN.findall(line)
                for tag in found_tags:
                    # 记录标签及其来源
                    tags[tag].append({
                        'date': date_str,
                        'line': line_num,
                        'content': line.strip()
                    })
        
        return dict(tags)
    
    def analyze_tags(self, days_back: int = 7, min_occurrences: int = 3) -> Dict[str, dict]:
        """
        分析标签统计信息
        
        Args:
            days_back: 回溯天数
            min_occurrences: 最小出现次数阈值，默认3次
            
        Returns:
            符合条件的标签统计字典，格式：
            {
                "tag_name": {
                    "count": 5,
                    "first_seen": "2026-03-24",
                    "sources": ["2026-03-24", "2026-03-25", ...],
                    "occurrences": [...]  # 详细出现记录
                }
            }
        """
        files = self.find_memory_files(days_back)
        if not files:
            print(f"[TagAnalyzer] 未找到最近 {days_back} 天的记忆文件")
            return {}
        
        print(f"[TagAnalyzer] 分析 {len(files)} 个文件...")
        
        # 聚合所有标签
        all_tags = defaultdict(lambda: {
            "count": 0,
            "first_seen": None,
            "sources": set(),
            "occurrences": []
        })
        
        for filepath in files:
            file_tags = self.extract_tags_from_file(filepath)
            date_str = filepath.stem
            
            for tag, occurrences in file_tags.items():
                all_tags[tag]["count"] += len(occurrences)
                all_tags[tag]["sources"].add(date_str)
                all_tags[tag]["occurrences"].extend(occurrences)
                
                # 更新首次出现日期（取最早的）
                if all_tags[tag]["first_seen"] is None or date_str < all_tags[tag]["first_seen"]:
                    all_tags[tag]["first_seen"] = date_str
        
        # 筛选符合条件的标签（出现次数 >= min_occurrences）
        qualified_tags = {}
        for tag, stats in all_tags.items():
            if stats["count"] >= min_occurrences:
                qualified_tags[tag] = {
                    "count": stats["count"],
                    "first_seen": stats["first_seen"],
                    "sources": sorted(list(stats["sources"])),
                    "occurrences": stats["occurrences"]
                }
        
        print(f"[TagAnalyzer] 发现 {len(all_tags)} 个标签，{len(qualified_tags)} 个符合条件")
        return qualified_tags
    
    def get_all_tags(self, days_back: int = 7) -> Dict[str, dict]:
        """
        获取所有标签的统计（不筛选）
        
        Args:
            days_back: 回溯天数
            
        Returns:
            所有标签的统计字典
        """
        files = self.find_memory_files(days_back)
        
        all_tags = defaultdict(lambda: {
            "count": 0,
            "sources": set()
        })
        
        for filepath in files:
            file_tags = self.extract_tags_from_file(filepath)
            date_str = filepath.stem
            
            for tag, occurrences in file_tags.items():
                all_tags[tag]["count"] += len(occurrences)
                all_tags[tag]["sources"].add(date_str)
        
        # 转换为普通 dict
        return {
            tag: {
                "count": stats["count"],
                "sources": sorted(list(stats["sources"]))
            }
            for tag, stats in all_tags.items()
        }