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
    
    def __init__(self, agent_id: str, l1_path: Optional[str] = None):
        """
        初始化标签分析器
        
        Args:
            agent_id: Agent ID（必需），用于构建默认 L1 路径
            l1_path: 自定义 L1 路径，覆盖默认模板
        
        Raises:
            ValueError: 如果 agent_id 为空且未提供 l1_path
        """
        if l1_path:
            self.l1_base_path = Path(l1_path).expanduser()
        elif agent_id:
            self.l1_base_path = Path(
                self.L1_PATH_TEMPLATE.format(agent=agent_id)
            ).expanduser()
        else:
            raise ValueError("必须提供 agent_id 或 l1_path")
    
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
    
    def extract_selfevolve_entries(self, filepath: Path) -> List[Dict]:
        """
        从 L1 文件中提取事件类型为 SelfEvolve 的条目
        
        通过按顺序配对索引段和日志段来精确筛选，避免同一时间的多个条目混淆。
        兼容多种 L1 文件格式。
        
        Args:
            filepath: 记忆文件路径
            
        Returns:
            SelfEvolve 条目列表，每条包含完整字段
        """
        entries = []
        date_str = filepath.stem
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except (IOError, UnicodeDecodeError) as e:
            print(f"[TagAnalyzer] 读取文件失败 {filepath}: {e}")
            return entries
        
        # 尝试多种分隔符定位索引段和日志段
        parts = None
        for sep in ["# ============================================", "\n---\n"]:
            if sep in content:
                parts = content.split(sep)
                if len(parts) >= 3:
                    break
        
        if not parts or len(parts) < 3:
            # fallback: 按标题定位
            if "# L1 标签索引" in content and "# L1 完整日志" in content:
                idx_start = content.find("# L1 标签索引")
                log_start = content.find("# L1 完整日志")
                if idx_start < log_start:
                    index_section = content[idx_start:log_start]
                    log_section = content[log_start:]
                else:
                    return entries
            else:
                return entries
        else:
            index_section = parts[1] if len(parts) > 1 else ""
            log_section = parts[2] if len(parts) > 2 else ""
        
        # 1. 解析索引段，收集所有条目（按顺序）
        index_entries = []
        for line in index_section.split("\n"):
            line = line.strip()
            if line.startswith("|") and not line.startswith("|------"):
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if len(cells) >= 4:
                    index_entries.append({
                        "time": cells[0],
                        "item_type": cells[1],
                        "event_type": cells[2],
                        "tags_str": cells[3]
                    })
        
        # 2. 解析日志段，收集所有条目（按顺序）
        log_entries = []
        entry_blocks = re.split(r'\n## ', log_section)
        for block in entry_blocks[1:]:
            lines = block.strip().split("\n")
            if not lines:
                continue
            
            time = lines[0].strip()
            content_text = ""
            tags = []
            source = ""
            emotion = ""
            improve = ""
            action = ""
            oput = ""
            
            for line in lines[1:]:
                line = line.strip()
                if line.startswith("- **内容**："):
                    content_text = line[9:].strip()
                elif line.startswith("- **情绪**："):
                    emotion = line[9:].strip()
                elif line.startswith("- **标签**："):
                    tag_str = line[9:].strip().strip('`')
                    tags = [t.strip('#') for t in tag_str.split() if t.startswith('#')]
                elif line.startswith("- **来源**："):
                    source = line[9:].strip()
                elif line.startswith("- **后续行动**："):
                    action = line[11:].strip()
                elif line.startswith("- **成果**："):
                    oput = line[8:].strip()
                elif line.startswith("- **纠正**："):
                    improve = line[8:].strip()
            
            if content_text:
                log_entries.append({
                    "time": time,
                    "content": content_text,
                    "tags": tags,
                    "source": source,
                    "emotion": emotion,
                    "improve": improve,
                    "action": action,
                    "oput": oput,
                })
        
        # 3. 按顺序配对，筛选 event_type == SelfEvolve
        pair_count = min(len(index_entries), len(log_entries))
        for i in range(pair_count):
            if index_entries[i]["event_type"] == "SelfEvolve":
                entry = log_entries[i].copy()
                entry["date"] = date_str
                entry["event_type"] = "SelfEvolve"
                entries.append(entry)
        
        return entries
    
    def analyze_selfevolve_entries(self, days_back: int = 7) -> List[Dict]:
        """
        分析最近 N 天 L1 中的 SelfEvolve 条目
        
        Args:
            days_back: 回溯天数
            
        Returns:
            SelfEvolve 条目列表
        """
        files = self.find_memory_files(days_back)
        if not files:
            print(f"[TagAnalyzer] 未找到最近 {days_back} 天的记忆文件")
            return []
        
        print(f"[TagAnalyzer] 分析 {len(files)} 个文件中的 SelfEvolve 条目...")
        
        all_entries = []
        for filepath in files:
            entries = self.extract_selfevolve_entries(filepath)
            if entries:
                print(f"[TagAnalyzer] {filepath.stem}: 发现 {len(entries)} 条 SelfEvolve")
            all_entries.extend(entries)
        
        print(f"[TagAnalyzer] 总计 {len(all_entries)} 条 SelfEvolve 条目")
        return all_entries
    
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