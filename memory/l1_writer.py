#!/usr/bin/env python3
"""
L1 Writer - L1 存储写入模块（简化版）
支持 Agent 主动总结写入的新格式
"""

import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


class L1Writer:
    """L1 存储写入器 - 简化版"""

    # 有效的事件类型和记忆标签
    EVENT_TYPES = {"CoreWork", "EventsOutside", "SelfEvolve", "SocialEcology", "RuleDecision"}
    MEMORY_TAGS = {"Event", "Preference", "To-do", "Output", "Emotion"}

    def __init__(self, agent_id: str, config: Dict[str, Any]):
        self.agent_id = agent_id
        self.config = config

    def _get_l1_path(self, date_str: str = None) -> Path:
        """获取 L1 文件路径"""
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        template = self.config.get("output", {}).get("l1_template") \
            or self.config.get("l1_template") \
            or "~/.openclaw/workspaces/{agent}/workspace/memory/{date}.md"
        path_str = template.format(agent=self.agent_id, date=date_str)
        return Path(path_str).expanduser()

    def _validate_entry(self, entry: Dict[str, Any]) -> tuple:
        """
        验证条目格式

        Returns:
            (is_valid, error_msg)
        """
        tag = entry.get("tag", "")
        event_type = entry.get("event_type", "")
        content = entry.get("content", "")

        if not content.strip():
            return False, "内容不能为空"

        if tag and tag not in self.MEMORY_TAGS:
            return False, f"无效的记忆标签: {tag}，有效值: {self.MEMORY_TAGS}"

        if event_type and event_type not in self.EVENT_TYPES:
            return False, f"无效的事件类型: {event_type}，有效值: {self.EVENT_TYPES}"

        return True, ""

    def _format_entries(self, entries: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        将条目按事件类型分组，生成 Markdown 行

        Returns:
            {event_type: ["- [Tag] content", ...]}
        """
        grouped = {}
        for entry in entries:
            is_valid, error = self._validate_entry(entry)
            if not is_valid:
                print(f"[L1Writer] 跳过无效条目: {error}")
                continue

            tag = entry.get("tag", "Event")
            event_type = entry.get("event_type", "CoreWork")
            content = entry.get("content", "").strip()

            line = f"- [{tag}] {content}"

            if event_type not in grouped:
                grouped[event_type] = []
            grouped[event_type].append(line)

        return grouped

    def _build_index_lines(self, entries: List[Dict[str, Any]]) -> List[str]:
        """
        构建标签索引行

        Returns:
            ["| To-do | CoreWork |", ...]
        """
        seen = set()
        lines = []
        for entry in entries:
            tag = entry.get("tag", "Event")
            event_type = entry.get("event_type", "CoreWork")
            key = (tag, event_type)
            if key not in seen:
                seen.add(key)
                lines.append(f"| {tag} | {event_type} |")
        return lines

    def write(self, entries: List[Dict[str, Any]], date_str: str = None) -> int:
        """
        写入 L1 存储文件（新格式）

        Args:
            entries: 条目列表，每项格式：
                {
                    "tag": "Event|Preference|To-do|Output|Emotion",
                    "event_type": "CoreWork|EventsOutside|SelfEvolve|SocialEcology|RuleDecision",
                    "content": "内容摘要"
                }
            date_str: 日期字符串 (YYYY-MM-DD)，默认今天

        Returns:
            写入行数
        """
        if not entries:
            return 0

        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        l1_path = self._get_l1_path(date_str)
        l1_path.parent.mkdir(parents=True, exist_ok=True)

        # 检查是否已有当天文件
        existing_entries = []
        if l1_path.exists():
            existing_entries = self._parse_existing_entries(l1_path)

        # 合并新旧条目
        all_entries = existing_entries + entries

        # 去重（基于 content + tag + event_type）
        seen = set()
        unique_entries = []
        for e in all_entries:
            key = (e.get("tag", ""), e.get("event_type", ""), e.get("content", "").strip())
            if key not in seen:
                seen.add(key)
                unique_entries.append(e)

        # 构建索引
        index_lines = self._build_index_lines(unique_entries)

        # 按事件类型分组构建正文
        grouped = self._format_entries(unique_entries)

        # 写入文件
        lines_written = 0
        with open(l1_path, 'w', encoding='utf-8') as f:
            # 标题
            f.write(f"# Memory Log - {date_str}\n\n")
            lines_written += 2

            # 标签索引
            f.write("| 记忆标签 | 事件类型 |\n")
            f.write("|----------|----------|\n")
            lines_written += 2
            for line in index_lines:
                f.write(line + "\n")
                lines_written += 1

            # 分隔线
            f.write("\n---\n\n")
            lines_written += 3

            # 正文：按事件类型分组
            for event_type in sorted(grouped.keys()):
                f.write(f"## {event_type}\n")
                lines_written += 1
                for entry_line in grouped[event_type]:
                    f.write(entry_line + "\n")
                    lines_written += 1
                f.write("\n")
                lines_written += 1

        print(f"[L1Writer] 写入 {len(unique_entries)} 条到 {l1_path} ({lines_written} 行)")
        return lines_written

    def _parse_existing_entries(self, l1_path: Path) -> List[Dict[str, Any]]:
        """
        解析现有的 L1 文件，提取已有条目

        Returns:
            条目列表
        """
        try:
            content = l1_path.read_text(encoding='utf-8')
        except Exception:
            return []

        entries = []
        current_event_type = "CoreWork"

        for line in content.split('\n'):
            line = line.strip()

            # 跳过空行、分隔线、标题
            if not line or line == '---' or line.startswith('# '):
                continue

            # 跳过索引表头
            if line.startswith('| 记忆标签') or line.startswith('|----------'):
                continue

            # 解析索引行：| To-do | CoreWork |
            if line.startswith('| ') and line.endswith(' |'):
                parts = line[2:-2].split(' | ')
                if len(parts) == 2:
                    continue  # 索引行不需要提取为条目

            # 检测事件类型标题
            if line.startswith('## '):
                current_event_type = line[3:].strip()
                continue

            # 解析条目行：- [To-do] 内容
            match = re.match(r'^- \[([^\]]+)\] (.+)$', line)
            if match:
                tag = match.group(1)
                content_text = match.group(2)
                entries.append({
                    "tag": tag,
                    "event_type": current_event_type,
                    "content": content_text
                })

        return entries

    def append(self, entries: List[Dict[str, Any]], date_str: str = None) -> int:
        """
        追加条目到现有 L1 文件（读取 + 合并 + 重写）

        Args:
            entries: 要追加的条目
            date_str: 日期字符串

        Returns:
            写入行数
        """
        return self.write(entries, date_str)
