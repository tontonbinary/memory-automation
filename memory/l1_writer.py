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

    def _get_l1_path(self) -> Path:
        """获取当前 L1 文件路径"""
        date_str = datetime.now().strftime("%Y-%m-%d")

        # 从配置构建路径
        template = self.config.get("l1_template",
            "~/.openclaw/workspaces/{agent}/workspace/memory/{date}.md")

        path_str = template.format(agent=self.agent_id, date=date_str)
        return Path(path_str).expanduser()

    def _format_l1_entry(self, item: Dict[str, Any], line_number: int = 0) -> str:
        """
        格式化为 L1 存储格式

        Args:
            item: 蒸馏项
            line_number: 行号

        Returns:
            Markdown 格式的记忆条目
        """
        timestamp = datetime.now().strftime("%H:%M")

        lines = [
            f"## {timestamp}",
            f"### {item['item_type'].capitalize()}",
            f"- **内容**：{item['content']}",
        ]

        if item.get("emotion"):
            lines.append(f"- **情绪**：{item['emotion']}")

        # 新增：成果字段
        if item.get("outcome"):
            lines.append(f"- **成果**：{item['outcome']}")

        if item.get("follow_up"):
            lines.append(f"- **后续行动**：{item['follow_up']}")

        if item.get("tags"):
            tag_str = " ".join([f"#{tag}" for tag in item["tags"]])
            lines.append(f"- **标签**：`{tag_str}`")

        # 添加来源信息
        date_str = datetime.now().strftime("%Y-%m-%d")
        lines.append(f"- **来源**：memory/{date_str}.md#L{line_number}")

        lines.append("")  # 空行分隔

        return "\n".join(lines)

    def write(self, items: List[Dict[str, Any]]) -> int:
        """
        写入 L1 存储文件（两段式格式）

        第一段：标签索引（启动时只读这个）
        第二段：完整日志（按需调取）

        Args:
            items: 蒸馏项列表

        Returns:
            写入行数
        """
        l1_path = self._get_l1_path()

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
            timestamp = datetime.now().strftime("%H:%M")
            tags_str = " ".join([f"#{tag}" for tag in item.get("tags", [])]) if item.get("tags") else "-"
            # 索引行格式：| 时间 | 标签 | 类型 | 位置 |
            index_entry = f"| {timestamp} | {tags_str} | {item['item_type']} | ## {timestamp} |"
            new_index_lines.append(index_entry)

        # 构建新的完整日志条目
        new_log_entries = []
        for idx, item in enumerate(items):
            entry = self._format_l1_entry(item, start_line + idx)
            new_log_entries.append(entry)

        # 写入文件
        lines_written = 0
        with open(l1_path, 'w', encoding='utf-8') as f:
            date_str = datetime.now().strftime("%Y-%m-%d")

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
