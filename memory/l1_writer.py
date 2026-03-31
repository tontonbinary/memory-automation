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

    def _parse_timestamp(self, raw_ts: str) -> Tuple[str, str]:
        """
        从原始 timestamp 解析时区标签和 HH:MM 显示时间

        Args:
            raw_ts: 原始时间字符串，如 "2026-03-30T20:04:22.758Z" 或 "+02:00"

        Returns:
            (timezone_label, time_display)
            timezone_label: "UTC" | "Asia/Shanghai (UTC+8)" | "Europe/Barcelona (UTC+2)" | "Unknown"
            time_display: "HH:MM" 格式
        """
        if not raw_ts:
            return "Unknown", "??:??"
        try:
            if raw_ts.endswith('Z'):
                # UTC
                ts = raw_ts[:-1]  # 去掉 Z
                return "UTC", ts[11:16]
            elif '+' in raw_ts:
                # 带偏移量，如 +08:00、+02:00
                offset_start = raw_ts.rfind('+')
                offset = raw_ts[offset_start:]
                time_part = raw_ts[:offset_start]
                if offset == '+08:00':
                    tz_label = "Asia/Shanghai (UTC+8)"
                elif offset == '+02:00':
                    tz_label = "Europe/Barcelona (UTC+2)"
                elif offset == '+00:00':
                    tz_label = "UTC"
                else:
                    tz_label = offset  # 兜底直接用偏移量
                return tz_label, time_part[11:16]
            else:
                ts = raw_ts
                return "Local", ts[11:16]
        except:
            return "Unknown", "??"

    def _detect_last_timezone_change(self, content: str) -> Optional[str]:
        """
        从现有文件内容中读取最后一次时区变更标记

        Returns:
            时区标签，如 "Asia/Shanghai (UTC+8)"，或 None（未找到）
        """
        last_tz = None
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('# 时区变更:'):
                # 提取 "Asia/Shanghai (UTC+8) from 20:04" 中的时区部分
                after_colon = line[6:].strip()
                # "Asia/Shanghai (UTC+8) from 20:04" → "Asia/Shanghai (UTC+8)"
                if ' from ' in after_colon:
                    last_tz = after_colon.split(' from ')[0].strip()
                else:
                    last_tz = after_colon
            elif line.startswith('# 时区:'):
                # 文件头部的时区（不含变更）
                if '# 时区变更' not in line:
                    last_tz = line[5:].strip()
        return last_tz

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
            session_start_time: session 第一条消息的原始 timestamp
            session_end_time: session 结束时间戳
            item_times: 每项的原始 timestamp 列表，与 items 对齐

        Returns:
            写入行数
        """
        has_item_times = item_times is not None and len(item_times) >= len(items)

        # 从第一条消息获取当前 session 的时区
        current_tz, _ = self._parse_timestamp(session_start_time if session_start_time else (item_times[0] if has_item_times else ""))

        # 从第一条消息推断日期
        date_str = datetime.now().strftime("%Y-%m-%d")
        if session_start_time:
            date_str = session_start_time[:10]
        elif has_item_times and item_times[0]:
            date_str = item_times[0][:10]

        l1_path = self._get_l1_path(date_str)
        l1_path.parent.mkdir(parents=True, exist_ok=True)
        is_new_file = not l1_path.exists()

        # 读取现有内容
        existing_content = ""
        start_line = 1
        file_last_tz = None
        if not is_new_file:
            with open(l1_path, 'r', encoding='utf-8') as f:
                existing_content = f.read()
            start_line = len(existing_content.splitlines()) + 1
            file_last_tz = self._detect_last_timezone_change(existing_content)

        # 解析每条的时间（HH:MM 和时区标签）
        parsed_items = []
        current_batch_tz = current_tz
        tz_change_inserted = False
        for idx, item in enumerate(items):
            raw_ts = item_times[idx] if has_item_times else ''
            tz_label, time_display = self._parse_timestamp(raw_ts)
            parsed_items.append({
                'item': item,
                'tz': tz_label,
                'time_display': time_display,
                'raw_ts': raw_ts
            })
            # 检查本批次内是否有时区变化
            if idx == 0:
                current_batch_tz = tz_label
            elif tz_label != current_batch_tz:
                # 第一个时区变化点
                current_batch_tz = tz_label
                tz_change_inserted = True

        # 构建新的标签索引行
        new_index_lines = []
        for pi in parsed_items:
            item = pi['item']
            time_display = pi['time_display']
            item_type = item.get('item_type', '')
            tags_str = " ".join([f"#{tag}" for tag in item.get("tags", [])]) if item.get("tags") else "-"
            event_type = item.get('event_type', item['item_type'])
            new_index_lines.append(f"| {time_display} | {item_type} | {event_type} | {tags_str} |")
            item['session_date'] = date_str

        # 构建完整日志条目（带时区变更标注）
        new_log_entries = []
        for idx, pi in enumerate(parsed_items):
            item = pi['item']
            time_display = pi['time_display']
            tz_label = pi['tz']
            entry = self._format_l1_entry(item, start_line + len(new_index_lines) + idx, time_display)
            new_log_entries.append(entry)

        # 是否需要时区变更标记（本批次第一个时区 ≠ 文件最后一个时区）
        needs_tz_change = (file_last_tz is not None and
                            current_batch_tz != "Unknown" and
                            file_last_tz != current_batch_tz)

        # 写入
        lines_written = 0
        with open(l1_path, 'w', encoding='utf-8') as f:

            if is_new_file:
                # 新文件
                f.write(f"# Memory Log - {date_str}\n")
                f.write(f"# 时区: {current_tz}\n\n")
                lines_written += 3

                f.write("# L1 标签索引\n\n")
                f.write("| 时间 | 记忆标签 | 事件类型 | 内容标签 |\n")
                f.write("|------|----------|----------|----------|\n")
                for line in new_index_lines:
                    f.write(line + "\n")
                    lines_written += 1

                f.write("\n---\n\n")
                lines_written += 2

                f.write("# L1 完整日志\n\n")
                lines_written += 2

                for entry in new_log_entries:
                    f.write(entry + "\n")
                    lines_written += entry.count("\n") + 1

            else:
                # 已有文件
                parts = existing_content.split("\n---\n")
                if len(parts) >= 2:
                    first_part = parts[0]
                    # 如果没有时区头部，插入
                    if '# 时区:' not in first_part:
                        first_lines = first_part.split("\n")
                        insert_pos = 0
                        for i, line in enumerate(first_lines):
                            if line.startswith("# Memory Log"):
                                insert_pos = i + 2
                                break
                        first_lines.insert(insert_pos, f"# 时区: {current_tz}")
                        first_part = "\n".join(first_lines)

                    f.write(first_part + "\n")
                    lines_written += len(first_part.split("\n"))

                    for line in new_index_lines:
                        f.write(line + "\n")
                        lines_written += 1

                    f.write("\n---\n\n")
                    lines_written += 2

                    second_part = parts[1]
                    # 确保有"# L1 完整日志"标记
                    if not second_part.strip().startswith("# L1 完整日志") and not second_part.strip().startswith("# 时区变更"):
                        second_part = "# L1 完整日志\n\n" + second_part

                    # 时区变化：插入变更标注
                    if needs_tz_change:
                        # 找到第一个时区变化的时间点
                        change_time = parsed_items[0]['time_display']
                        for pi in parsed_items:
                            if pi['tz'] != file_last_tz:
                                change_time = pi['time_display']
                                break
                        tz_change_marker = f"# 时区变更: {current_batch_tz} from {change_time}\n\n"
                        second_part = tz_change_marker + second_part
                        lines_written += tz_change_marker.count("\n")

                    f.write(second_part)
                    lines_written += len(second_part.split("\n"))

                    for entry in new_log_entries:
                        f.write(entry + "\n")
                        lines_written += entry.count("\n") + 1
                else:
                    # 格式损坏，当新文件处理
                    f.write(f"# Memory Log - {date_str}\n")
                    f.write(f"# 时区: {current_tz}\n\n")
                    lines_written += 3
                    f.write("# L1 标签索引\n\n")
                    f.write("| 时间 | 记忆标签 | 事件类型 | 内容标签 |\n")
                    f.write("|------|----------|----------|----------|\n")
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
