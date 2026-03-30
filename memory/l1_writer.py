#!/usr/bin/env python3
"""
L1 Writer - L1 存储写入模块
处理 L1 记忆文件的格式化写入
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


class L1Writer:
    """L1 存储写入器"""

    def __init__(self, agent_id: str, config: Dict[str, Any]):
        self.agent_id = agent_id
        self.config = config

    def _get_l1_path(self, date_str: str = None) -> Path:
        """获取当前 L1 文件路径"""
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        template = self.config.get("l1_template",
            "~/.openclaw/workspaces/{agent}/workspace/memory/{date}.md")
        path_str = template.format(agent=self.agent_id, date=date_str)
        return Path(path_str).expanduser()

    def _infer_timezone(self, timestamp: str) -> Tuple[str, str]:
        """
        从 timestamp 推断时区和显示时间

        Args:
            timestamp: ISO 8601 时间字符串（可能带 Z）

        Returns:
            (timezone_label, time_display)
            timezone_label: "Asia/Shanghai (UTC+8)" | "UTC" | "Unknown"
            time_display: "HH:MM" 格式
        """
        if not timestamp:
            return "Unknown", "??:??"
        try:
            ts = timestamp.replace('Z', '+00:00')
            dt = datetime.fromisoformat(ts)
            if timestamp.endswith('Z'):
                # UTC 时间，尝试转换到 Asia/Shanghai
                try:
                    from zoneinfo import ZoneInfo
                    dt_local = dt.astimezone(ZoneInfo("Asia/Shanghai"))
                    tz_label = "Asia/Shanghai (UTC+8)"
                except ImportError:
                    dt_local = dt + timedelta(hours=8)
                    tz_label = "Asia/Shanghai (UTC+8)"  # 假设为上海
            else:
                # 非 UTC，直接用本地
                dt_local = dt
                tz_label = "Local"
            return tz_label, dt_local.strftime("%H:%M")
        except:
            return "Unknown", "??:??"

    def _detect_file_timezone(self, content: str) -> Optional[str]:
        """
        从现有文件内容中读取时区信息

        Returns:
            时区标签，如 "Asia/Shanghai (UTC+8)"，或 None（未找到）
        """
        # 匹配 "# 时区: Asia/Shanghai (UTC+8)" 或 "# 时区变更: UTC"
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('# 时区变更:'):
                return line[6:].strip()
            if line.startswith('# 时区:'):
                return line[5:].strip()
        return None

    def _format_l1_entry(self, item: Dict[str, Any], line_number: int = 0,
                         entry_time: str = None) -> str:
        """格式化为 L1 存储格式"""
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

        # 来源：session/MM-DD#L行号
        session_date = item.get("session_date", "")
        lines.append(f"- **来源**：session/{session_date[5:] if session_date else '??-??'}#L{line_number}")

        lines.append("")
        return "\n".join(lines)

    def write(self, items: List[Dict[str, Any]],
              session_start_time: str = None,
              session_end_time: str = None,
              item_times: List[str] = None) -> int:
        """
        写入 L1 存储文件（两段式格式）

        Args:
            items: 蒸馏项列表
            session_start_time: session 开始时间戳 (ISO 8601 格式)
            session_end_time: session 结束时间戳
            item_times: 每项的时间戳列表(HH:MM)，与 items 对齐

        Returns:
            写入行数
        """
        # 从第一条消息推断时区
        if session_start_time:
            current_tz, _ = self._infer_timezone(session_start_time)
        else:
            current_tz = "Unknown"

        # 推断日期
        if session_start_time:
            try:
                ts = session_start_time.replace('Z', '+00:00')
                dt = datetime.fromisoformat(ts)
                if session_start_time.endswith('Z'):
                    try:
                        from zoneinfo import ZoneInfo
                        dt = dt.astimezone(ZoneInfo("Asia/Shanghai"))
                    except ImportError:
                        dt = dt + timedelta(hours=8)
                date_str = dt.strftime("%Y-%m-%d")
            except:
                date_str = datetime.now().strftime("%Y-%m-%d")
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")

        has_item_times = item_times is not None and len(item_times) >= len(items)
        l1_path = self._get_l1_path(date_str)
        l1_path.parent.mkdir(parents=True, exist_ok=True)
        is_new_file = not l1_path.exists()

        # 读取现有内容
        existing_content = ""
        start_line = 1
        file_timezone = None
        if not is_new_file:
            with open(l1_path, 'r', encoding='utf-8') as f:
                existing_content = f.read()
            start_line = len(existing_content.splitlines()) + 1
            file_timezone = self._detect_file_timezone(existing_content)

        # 构建新的标签索引行
        new_index_lines = []
        for idx, item in enumerate(items):
            item_time = item_times[idx] if has_item_times else '??:??'
            tags_str = " ".join([f"#{tag}" for tag in item.get("tags", [])]) if item.get("tags") else "-"
            index_entry = f"| {item_time} | {tags_str} | {item['item_type']} | ## {item_time} |"
            new_index_lines.append(index_entry)
            item['session_date'] = date_str

        # 构建完整日志条目
        new_log_entries = []
        for idx, item in enumerate(items):
            item_time = item_times[idx] if has_item_times else '??:??'
            entry = self._format_l1_entry(item, start_line + idx, item_time)
            new_log_entries.append(entry)

        # 是否需要时区变更标记
        tz_changed = (file_timezone is not None and
                      current_tz != "Unknown" and
                      file_timezone != current_tz)

        # 写入
        lines_written = 0
        with open(l1_path, 'w', encoding='utf-8') as f:

            if is_new_file:
                # 新文件：写入完整两段式结构 + 时区头部
                f.write(f"# Memory Log - {date_str}\n")
                f.write(f"# 时区: {current_tz}\n\n")
                lines_written += 3

                # 第一段：标签索引
                f.write("# L1 标签索引\n\n")
                f.write("| 时间 | 标签 | 类型 | 位置 |\n")
                f.write("|------|------|------|------|\n")
                for line in new_index_lines:
                    f.write(line + "\n")
                    lines_written += 1

                f.write("\n---\n\n")
                lines_written += 2

                # 第二段：完整日志
                f.write("# L1 完整日志\n\n")
                lines_written += 2

                for entry in new_log_entries:
                    f.write(entry + "\n")
                    lines_written += entry.count("\n") + 1

            else:
                # 已有文件：保留第一段，追加到第二段
                parts = existing_content.split("\n---\n")
                if len(parts) >= 2:
                    first_part = parts[0]
                    # 如果没有时区头部，插入一个
                    if not first_part.startswith("# 时区:"):
                        first_lines = first_part.split("\n")
                        insert_pos = 0
                        for i, line in enumerate(first_lines):
                            if line.startswith("# Memory Log"):
                                insert_pos = i + 2  # after "# Memory Log - date"
                                break
                        first_lines.insert(insert_pos, f"# 时区: {current_tz}")
                        first_part = "\n".join(first_lines)

                    f.write(first_part + "\n")
                    lines_written += len(first_part.split("\n"))

                    # 追加新索引行
                    for line in new_index_lines:
                        f.write(line + "\n")
                        lines_written += 1

                    f.write("\n---\n\n")
                    lines_written += 2

                    # 第二段
                    second_part = parts[1]
                    # 检查是否有时区变更
                    if tz_changed and not second_part.strip().startswith("# 时区变更"):
                        # 插入时区变更标记
                        second_part = f"# 时区变更: {current_tz}\n\n" + second_part
                    elif not second_part.strip().startswith("# L1 完整日志"):
                        second_part = "# L1 完整日志\n\n" + second_part

                    f.write(second_part)
                    lines_written += len(second_part.split("\n"))

                    # 追加新日志
                    for entry in new_log_entries:
                        f.write(entry + "\n")
                        lines_written += entry.count("\n") + 1
                else:
                    # 格式损坏，当新文件处理
                    f.write(f"# Memory Log - {date_str}\n")
                    f.write(f"# 时区: {current_tz}\n\n")
                    lines_written += 3
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
        """将新消息写入待处理队列文件"""
        l1_path = self._get_l1_path()
        queue_path = l1_path.parent / "pending_queue.json"
        queue_path.parent.mkdir(parents=True, exist_ok=True)

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

        with open(queue_path, 'w', encoding='utf-8') as f:
            json.dump(queue_data, f, ensure_ascii=False, indent=2)

        return queue_path
