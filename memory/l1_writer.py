#!/usr/bin/env python3
"""
L1 Writer - L1 存储写入模块（简化版）
支持 Agent 主动总结写入的新格式（7 分类）
"""

import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


class L1Writer:
    """L1 存储写入器 - 简化版（7 分类格式）"""

    # 6 分类固定顺序
    CATEGORIES = [
        "RuleDecision",
        "SelfEvolve",
        "SocialEcology",
        "To-do",
        "Output",
        "Event",
    ]

    def __init__(self, agent_id: str, config: Dict[str, Any]):
        self.agent_id = agent_id
        self.config = config

    def _get_l1_path(self, date_str: str = None, suffix: str = "") -> Path:
        """获取 L1 文件路径"""
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        template = self.config.get("output", {}).get("l1_template") \
            or self.config.get("l1_template") \
            or "~/.openclaw/workspaces/{agent}/workspace/memory/{date}.md"
        path_str = template.format(agent=self.agent_id, date=f"{date_str}{suffix}")
        return Path(path_str).expanduser()

    def _get_l1_glob(self, date_str: str) -> List[Path]:
        """获取同日期的所有 L1 文件（支持 glob）"""
        template = self.config.get("output", {}).get("l1_template") \
            or self.config.get("l1_template") \
            or "~/.openclaw/workspaces/{agent}/workspace/memory/{date}.md"
        # 替换 date 为 glob 模式
        glob_str = template.format(agent=self.agent_id, date=f"{date_str}*")
        parent = Path(glob_str).parent
        pattern = Path(glob_str).name
        return list(parent.glob(pattern))

    def write(self, entries: List[Dict[str, Any]], date_str: str = None, suffix: str = "") -> int:
        """
        写入 L1 存储文件（7 分类格式，无索引头部）

        Args:
            entries: 条目列表，每项格式：
                {
                    "tag": "Event|Preference|Decision|Todo|Output",
                    "event_type": "CoreWork|EventsOutside|SelfEvolve|SocialEcology|RuleDecision",
                    "content": "具体事实内容"
                }
            date_str: 日期字符串 (YYYY-MM-DD)，默认今天
            suffix: 文件后缀

        Returns:
            写入行数
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        l1_path = self._get_l1_path(date_str, suffix)
        l1_path.parent.mkdir(parents=True, exist_ok=True)

        # 解析现有条目：先 glob 合并所有同日期的 L1 文件
        existing_by_category = {cat: [] for cat in self.CATEGORIES}
        l1_glob = self._get_l1_glob(date_str)
        for glob_path in sorted(l1_glob):
            parsed = self._parse_existing_file(glob_path)
            for cat in self.CATEGORIES:
                for content in parsed.get(cat, []):
                    if content not in existing_by_category[cat]:
                        existing_by_category[cat].append(content)

        # 合并新条目（去重）
        seen = set()
        for e in entries:
            cat = e.get("event_type", "CoreWork")
            if cat not in self.CATEGORIES:
                cat = "CoreWork"
            content = e.get("content", "").strip()
            if not content:
                continue
            key = (cat, content)
            if key not in seen:
                seen.add(key)
                existing_by_category[cat].append(content)

        # 写入文件
        lines_written = 0
        with open(l1_path, 'w', encoding='utf-8') as f:
            # 标题
            f.write(f"# Memory Log - {date_str}\n\n")
            lines_written += 2

            # 正文：7 个分类，固定顺序
            for cat in self.CATEGORIES:
                f.write(f"## {cat}\n")
                lines_written += 1
                contents = existing_by_category[cat]
                if contents:
                    for content in contents:
                        f.write(content + "\n")
                        lines_written += 1
                else:
                    f.write("（空）\n")
                    lines_written += 1
                f.write("\n")
                lines_written += 1

        print(f"[L1Writer] 写入 {l1_path} ({lines_written} 行)")
        return lines_written

    def _parse_existing_file(self, l1_path: Path) -> Dict[str, List[str]]:
        """
        解析现有的 L1 文件，提取各分类内容（新格式：无索引头部）

        Returns:
            {category: [content, ...]}
        """
        result = {cat: [] for cat in self.CATEGORIES}
        current_cat = None

        try:
            content = l1_path.read_text(encoding='utf-8')
        except Exception:
            return result

        for line in content.split('\n'):
            line_stripped = line.strip()

            # 跳过空行、分隔线、标题
            if not line_stripped or line_stripped == '---' or line_stripped.startswith('# Memory Log'):
                continue

            # 检测分类标题
            if line_stripped.startswith('## '):
                current_cat = line_stripped[3:].strip()
                continue

            # 解析内容行
            if current_cat and current_cat in self.CATEGORIES:
                content_text = line_stripped
                if content_text and content_text != '（空）':
                    result[current_cat].append(content_text)

        return result

    def append(self, entries: List[Dict[str, Any]], date_str: str = None) -> int:
        """
        追加条目到现有 L1 文件
        """
        return self.write(entries, date_str)
