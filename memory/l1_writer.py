#!/usr/bin/env python3
"""
L1 Writer - L1 存储写入模块
处理 L1 记忆文件的格式化写入
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


class L1Writer:
    """L1 存储写入器"""

    def __init__(self, agent_id: str, config: Dict[str, Any]):
        self.agent_id = agent_id
        self.config = config

    def _get_l1_path(self, date_str: str = None) -> Path:
        """
        获取当前 L1 文件路径
        
        Args:
            date_str: 日期字符串 (YYYY-MM-DD)，None 则使用当前日期
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        # 从配置构建路径
        template = self.config.get("l1_template",
            "~/.openclaw/workspaces/{agent}/workspace/memory/{date}.md")

        path_str = template.format(agent=self.agent_id, date=date_str)
        return Path(path_str).expanduser()

    def _format_l1_entry(self, item: Dict[str, Any], line_number: int = 0, 
                         entry_time: str = None, session_date: str = None) -> str:
        """
        格式化为 L1 存储格式

        Args:
            item: 蒸馏项
            line_number: 行号
            entry_time: 条目时间戳 (HH:MM)，None 则使用当前时间
            session_date: session 日期 (YYYY-MM-DD)，用于来源字段

        Returns:
            Markdown 格式的记忆条目
        """
        if entry_time is None:
            entry_time = datetime.now().strftime("%H:%M")

        lines = [
            f"## {entry_time}",
            f"### {item['item_type'].capitalize()}",
            f"- **内容**：{item['content']}",
        ]

        if item.get("emotion"):
            lines.append(f"- **情绪**：{item['emotion']}")

        if item.get("action"):
            lines.append(f"- **后续行动**：{item['action']}")

        if item.get("oput"):
            lines.append(f"- **成果**：{item['oput']}")

        if item.get("improve"):
            lines.append(f"- **纠正**：{item['improve']}")

        if item.get("tags"):
            tag_str = " ".join([f"#{tag}" for tag in item["tags"]])
            lines.append(f"- **标签**：`{tag_str}`")

        # 添加来源信息（使用 session 原始日期）
        if session_date is None:
            session_date = datetime.now().strftime("%Y-%m-%d")
        lines.append(f"- **来源**：session/{session_date[5:]}#L{line_number}")

        lines.append("")  # 空行分隔

        return "\n".join(lines)

    def write(self, items: List[Dict[str, Any]], 
              session_start_time: str = None,
              session_end_time: str = None,
              item_times: List[str] = None) -> int:
        """
        写入 L1 存储文件（两段式格式）

        第一段：标签索引（启动时只读这个）
        第二段：完整日志（按需调取）

        Args:
            items: 蒸馏项列表
            session_start_time: session 开始时间戳 (ISO 8601 格式)
            session_end_time: session 结束时间戳 (ISO 8601 格式)
            item_times: 可选，每项的时间戳列表(HH:MM)，与items对齐。
                        如不提供，则所有项使用session_start_time。

        Returns:
            写入行数
        """
        # 从 session 时间计算日期和条目时间戳
        if session_start_time:
            try:
                # 解析 ISO 8601 时间（处理 Z 后缀为 UTC）
                start_dt = datetime.fromisoformat(session_start_time.replace('Z', '+00:00'))
                # 转换到 Asia/Shanghai 时区（UTC+8）
                from zoneinfo import ZoneInfo
                start_dt = start_dt.astimezone(ZoneInfo("Asia/Shanghai"))
                date_str = start_dt.strftime("%Y-%m-%d")
                entry_time_default = start_dt.strftime("%H:%M")
            except (ValueError, AttributeError):
                # 解析失败，使用当前时间
                date_str = datetime.now().strftime("%Y-%m-%d")
                entry_time_default = datetime.now().strftime("%H:%M")
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")
            entry_time_default = datetime.now().strftime("%H:%M")

        # per-item 时间戳（如果提供了）
        has_item_times = item_times is not None and len(item_times) >= len(items)

        l1_path = self._get_l1_path(date_str)

        # 确保目录存在
        l1_path.parent.mkdir(parents=True, exist_ok=True)

        # 检查文件是否存在
        is_new_file = not l1_path.exists()

        # 读取现有内容并计算行数（只读一次）
        existing_content = ""
        start_line = 1
        if not is_new_file:
            with open(l1_path, 'r', encoding='utf-8') as f:
                existing_content = f.read()
                # 从已读取的内容计算行数（无需再次读取文件）
                start_line = len(existing_content.splitlines()) + 1

        # 构建新的标签索引行
        new_index_lines = []
        for idx, item in enumerate(items):
            item_time = item_times[idx] if has_item_times else entry_time_default
            tags_str = " ".join([f"#{tag}" for tag in item.get("tags", [])]) if item.get("tags") else "-"
            # 索引行格式：| 时间 | 标签 | 类型 | 位置 |
            index_entry = f"| {item_time} | {tags_str} | {item['item_type']} | ## {item_time} |"
            new_index_lines.append(index_entry)

        # 构建新的完整日志条目
        new_log_entries = []
        for idx, item in enumerate(items):
            item_time = item_times[idx] if has_item_times else entry_time_default
            entry = self._format_l1_entry(item, start_line + idx, item_time, date_str)
            new_log_entries.append(entry)

        # 写入文件
        lines_written = 0
        with open(l1_path, 'w', encoding='utf-8') as f:

            if is_new_file:
                # 新文件：写入完整的两段式结构
                f.write(f"# Memory Log - {date_str}\n\n")
                lines_written += 2

                # 第一段：标签索引
                f.write("# L1 标签索引\n\n")
                f.write("| 时间 | 标签 | 类型 | 位置 |\n")
                f.write("|------|------|------|------|\n")
                for line in new_index_lines:
                    f.write(line + "\n")
                    lines_written += 1

                # 分隔符
                f.write("\n---\n\n")
                lines_written += 2

                # 第二段：完整日志
                f.write("# L1 完整日志\n\n")
                lines_written += 2

                # 写入日志条目
                for entry in new_log_entries:
                    f.write(entry + "\n")
                    lines_written += entry.count("\n") + 1
            else:
                # 已有文件：保留第一段，追加到第二段
                # 找到分隔符位置
                parts = existing_content.split("\n---\n")
                if len(parts) >= 2:
                    # 重写第一段（标签索引）
                    first_part = parts[0]
                    f.write(first_part + "\n")
                    lines_written += len(first_part.split("\n"))

                    # 追加新的索引行
                    for line in new_index_lines:
                        f.write(line + "\n")
                        lines_written += 1

                    # 分隔符和第二段
                    f.write("\n---\n\n")
                    lines_written += 2

                    # 写入第二段标题（如果被删除了）
                    second_part = parts[1]
                    if not second_part.strip().startswith("# L1 完整日志"):
                        f.write("# L1 完整日志\n\n")
                        lines_written += 2
                    else:
                        f.write(second_part)
                        lines_written += len(second_part.split("\n"))

                    # 追加完整日志
                    for entry in new_log_entries:
                        f.write(entry + "\n")
                        lines_written += entry.count("\n") + 1
                else:
                    # 格式不对，当作新文件处理
                    f.write(f"# Memory Log - {date_str}\n\n")
                    lines_written += 2
                    f.write("# L1 标签索引\n\n")
                    f.write("| 时间 | 标签 | 类型 | 位置 |\n")
                    f.write("|------|------|------|------|\n")
                    for line in new_index_lines:
                        f.write(line + "\n")
                        lines_written += 1
                    f.write("\n---\n\n")
                    f.write("# L1 完整日志\n\n")
                    lines_written += 2
                    for entry in new_log_entries:
                        f.write(entry + "\n")
                        lines_written += entry.count("\n") + 1

        return lines_written

    def write_pending_queue(self, messages: List[Dict[str, Any]]) -> Path:
        """
        将新消息写入待处理队列文件

        Args:
            messages: 待处理的消息列表

        Returns:
            队列文件路径
        """
        # 构建 pending_queue.json 路径（与 L1 同目录）
        l1_path = self._get_l1_path()
        queue_path = l1_path.parent / "pending_queue.json"

        # 确保目录存在
        queue_path.parent.mkdir(parents=True, exist_ok=True)

        # 构建队列数据
        queue_data = {
            "pending_count": len(messages),
            "messages": [
                {
                    "msg_id": msg.get("msg_id", ""),
                    "role": msg.get("role", ""),
                    "content": msg.get("content", ""),
                    "timestamp": msg.get("timestamp", "")
                }
                for msg in messages
            ]
        }

        # 写入文件
        with open(queue_path, 'w', encoding='utf-8') as f:
            json.dump(queue_data, f, ensure_ascii=False, indent=2)

        return queue_path
