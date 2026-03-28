"""
L2 写入模块 - 将符合条件的标签写入 L2 记忆文件
"""

import re
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class L2Writer:
    """管理 L2 记忆文件的写入"""
    
    # L2 文件默认路径
    DEFAULT_L2_PATH = "~/self-improving/memory.md"
    
    # L2 格式模板
    PATTERN_TEMPLATE = """### {tag_name}
- **首次记录**：{first_seen}
- **出现次数**：{count} 次
- **来源**：{sources}
"""
    
    def __init__(self, l2_path: Optional[str] = None):
        """
        初始化 L2 写入器
        
        Args:
            l2_path: L2 记忆文件路径，默认使用 DEFAULT_L2_PATH
        """
        self.l2_path = Path(l2_path or self.DEFAULT_L2_PATH).expanduser()
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """确保 L2 文件和目录存在"""
        self.l2_path.parent.mkdir(parents=True, exist_ok=True)
        
        if not self.l2_path.exists():
            # 创建初始文件结构
            initial_content = """# Memory (HOT Tier)

> 分层说明：Patterns = **L2 行为层**，Rules = **L3 认知层**
> L4 核心层（价值观）不能自动写入，只能建议。见：MEMORY-RULES.md

## Preferences

## Patterns

## Rules
"""
            with open(self.l2_path, 'w', encoding='utf-8') as f:
                f.write(initial_content)
    
    def read_l2_content(self) -> str:
        """
        读取 L2 文件内容
        
        Returns:
            文件内容字符串
        """
        try:
            with open(self.l2_path, 'r', encoding='utf-8') as f:
                return f.read()
        except (IOError, UnicodeDecodeError) as e:
            print(f"[L2Writer] 读取 L2 文件失败: {e}")
            return ""
    
    def find_patterns_section(self, content: str) -> tuple[int, int]:
        """
        找到 ## Patterns 部分的位置
        
        Args:
            content: L2 文件内容
            
        Returns:
            (开始位置, 结束位置)，如果未找到返回 (-1, -1)
        """
        # 查找 ## Patterns 标题
        patterns_match = re.search(r'## Patterns\s*\n', content)
        if not patterns_match:
            return -1, -1
        
        start = patterns_match.end()
        
        # 查找下一个 ## 标题（即 Patterns 部分结束）
        next_section = re.search(r'\n## [^#]', content[start:])
        if next_section:
            end = start + next_section.start()
        else:
            end = len(content)
        
        return start, end
    
    def tag_exists(self, tag_name: str) -> bool:
        """
        检查标签是否已存在于 L2
        
        Args:
            tag_name: 标签名（不含 #）
            
        Returns:
            是否已存在
        """
        content = self.read_l2_content()
        # 匹配 ### {tag_name} 或 ### #{tag_name}
        pattern = rf'###\s#?{re.escape(tag_name)}\s*\n'
        return bool(re.search(pattern, content))
    
    def format_tag_entry(self, tag_name: str, stats: dict) -> str:
        """
        格式化标签条目
        
        Args:
            tag_name: 标签名
            stats: 标签统计信息
            
        Returns:
            格式化的 markdown 字符串
        """
        sources_str = ", ".join([f"memory/{s}.md" for s in stats["sources"]])
        
        return self.PATTERN_TEMPLATE.format(
            tag_name=f"#{tag_name}",
            first_seen=stats["first_seen"],
            count=stats["count"],
            sources=sources_str
        )
    
    def append_tag(self, tag_name: str, stats: dict) -> bool:
        """
        将单个标签追加到 L2 Patterns 部分
        
        Args:
            tag_name: 标签名
            stats: 标签统计信息
            
        Returns:
            是否写入成功
        """
        # 检查是否已存在
        if self.tag_exists(tag_name):
            print(f"[L2Writer] 标签 #{tag_name} 已存在于 L2，跳过")
            return False
        
        content = self.read_l2_content()
        start, end = self.find_patterns_section(content)
        
        if start == -1:
            print("[L2Writer] 未找到 ## Patterns 部分，无法写入")
            return False
        
        # 生成新条目
        new_entry = self.format_tag_entry(tag_name, stats)
        
        # 插入到 Patterns 部分末尾（在下一个 ## 之前）
        patterns_content = content[start:end]
        
        # 检查 Patterns 部分是否为空（只有标题）
        if patterns_content.strip() == "":
            # 直接在标题后添加
            new_patterns = "\n" + new_entry
        else:
            # 追加到现有内容后
            new_patterns = patterns_content.rstrip() + "\n\n" + new_entry
        
        # 重组内容
        new_content = content[:start] + new_patterns + content[end:]
        
        # 写入文件
        try:
            with open(self.l2_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"[L2Writer] 成功写入标签 #{tag_name} 到 L2")
            return True
        except IOError as e:
            print(f"[L2Writer] 写入 L2 文件失败: {e}")
            return False
    
    def append_tags(self, tags: Dict[str, dict]) -> List[str]:
        """
        批量追加标签到 L2
        
        Args:
            tags: 标签统计字典
            
        Returns:
            成功写入的标签列表
        """
        successful = []
        for tag_name, stats in tags.items():
            if self.append_tag(tag_name, stats):
                successful.append(tag_name)
        return successful
