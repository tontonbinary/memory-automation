#!/usr/bin/env python3
"""
Session Cleaner - 会话消息清洗模块
只负责清洗和格式化消息，不再做 LLM 蒸馏
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


class SessionCleaner:
    """会话清洗器 - 清洗消息内容供 Agent 自己总结"""

    def __init__(self, min_message_length: int = 10):
        self.min_message_length = min_message_length

    def _clean_content(self, content: str) -> str:
        """
        清洗消息内容，去除工具调用结果等噪声
        """
        if not content:
            return ""

        # 去掉 [HH:MM] toolResult: <frozen runpy...> 格式
        content = re.sub(r'\[\d{2}:\d{2}\]\s*toolResult:\s*<[^>]+>', '', content)
        # 去掉 <frozen runpy> 等 Python 内部表示
        content = re.sub(r'<frozen \w+[^>]*>', '', content)
        # 去掉 Exec result: 日志块
        content = re.sub(r'Exec\s+result:.*?(?=\n\n|\n[A-Z]|$)', '', content, flags=re.DOTALL)
        # 去掉 Markdown 文件内容dump
        content = re.sub(r'^#{1,3}\s+[^\n]*Template[^\n]*\n', '', content, flags=re.MULTILINE)
        # 去掉明显的工具输出片段
        content = re.sub(r'\n?\[\d{2}:\d{2}\]\s*toolResult:[^\n]*', '', content)
        # 去掉 JSON/dict dump
        lines = content.split('\n')
        cleaned_lines = []
        for line in lines:
            if re.match(r'^\s*"[^"]+"\s*:\s*("[^"]*"|\[|' r'\{|\d+|true|false|null)', line):
                continue
            cleaned_lines.append(line)
        content = '\n'.join(cleaned_lines)

        # 去掉各种 untrusted metadata 块
        content = re.sub(r'Conversation info \(untrusted metadata\):\s*```json\s*\{[\s\S]*?\}\s*```', '', content)
        content = re.sub(r'Sender \(untrusted metadata\):\s*```json\s*\{[\s\S]*?\}\s*```', '', content)
        content = re.sub(r'Thread starter \(untrusted, for context\):\s*```json\s*\{[\s\S]*?\}\s*```', '', content)
        content = re.sub(r'Replied message \(untrusted, for context\):\s*```json\s*\{[\s\S]*?\}\s*```', '', content)
        content = re.sub(r'Forwarded message context \(untrusted metadata\):\s*```json\s*\{[\s\S]*?\}\s*```', '', content)
        content = re.sub(r'Chat history since last reply \(untrusted, for context\):\s*```json\s*[\s\S]*?```', '', content)

        # 去掉 [message_id: xxx] 行
        content = re.sub(r'\[message_id:[^\]]+\]\s*\n?', '', content)

        # 去掉空 ```json 块
        content = re.sub(r'```json\s*\{[\s\S]*?\}\s*```', '', content)

        return content.strip()

    def _is_user_facing(self, msg: Dict[str, Any], id_map: Dict[str, Dict]) -> bool:
        """
        判断消息是否是给用户看的（不是内部思考）
        """
        role = msg.get('role', '')

        if role == 'user':
            return True

        if role in ('toolResult', 'system'):
            return False

        if role == 'assistant':
            current_id = msg.get('parentId')
            depth = 0
            max_depth = 10

            while current_id and depth < max_depth:
                parent = id_map.get(current_id)
                if not parent:
                    break
                parent_role = parent.get('role', '')
                if parent_role == 'user':
                    return True
                if parent_role == 'toolResult':
                    return False
                current_id = parent.get('parentId')
                depth += 1

            return True

        return True

    def clean_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        清洗消息列表：parentId 链过滤 + 富文本提取 + 去噪

        Args:
            messages: 原始消息列表

        Returns:
            清洗后的消息列表（每条含 role, sender, timestamp, content）
        """
        if not messages:
            return []

        # 构建 id 映射
        id_map = {msg.get('id'): msg for msg in messages if msg.get('id')}

        cleaned = []
        for msg in messages:
            if not self._is_user_facing(msg, id_map):
                continue

            role = msg.get('role', 'unknown')
            sender = msg.get('sender') or msg.get('sender_id', '')
            timestamp = msg.get('timestamp', '')

            # 提取内容
            raw_content = msg.get('content', '')
            if isinstance(raw_content, list):
                parts = []
                for item in raw_content:
                    if isinstance(item, dict):
                        item_type = item.get('type')
                        if item_type in ('thinking', 'toolCall', 'toolResult'):
                            continue
                        if item_type == 'text':
                            text = item.get('text', '')
                            if text:
                                cleaned_text = self._clean_content(text)
                                if cleaned_text.strip():
                                    parts.append(cleaned_text.strip())
                        elif item_type == 'image':
                            parts.append('[图片]')
                        elif item_type == 'audio':
                            parts.append('[语音]')
                content = '\n'.join(parts)
            else:
                content = self._clean_content(str(raw_content))

            content = content.strip()

            # 跳过短消息
            if len(content) < self.min_message_length:
                continue

            # 过滤纯 heartbeat 消息
            if role == 'user' and content.startswith('Read HEARTBEAT'):
                continue
            if role == 'assistant':
                first_line = content.split('\n')[0].strip()
                if first_line == 'HEARTBEAT_OK':
                    continue

            # 过滤 System Exec 消息
            if role == 'user' and content.startswith('System (untrusted):'):
                continue

            cleaned.append({
                'role': role,
                'sender': sender,
                'timestamp': timestamp,
                'content': content
            })

        print(f"[SessionCleaner] 清洗: {len(messages)} 条 -> {len(cleaned)} 条")
        return cleaned

    def format_for_display(self, messages: List[Dict[str, Any]]) -> str:
        """
        将清洗后的消息格式化为可读的文本（供 Agent 查看）

        Args:
            messages: 清洗后的消息列表

        Returns:
            格式化的文本
        """
        lines = []
        for idx, msg in enumerate(messages, 1):
            role_display = '用户' if msg['role'] == 'user' else '助手'
            sender_info = f"[{msg['sender']}] " if msg['sender'] else ""

            # 格式化时间
            time_str = ''
            ts = msg.get('timestamp', '')
            if ts:
                try:
                    if isinstance(ts, str) and 'T' in ts:
                        time_str = f"[{ts[11:16]}] "
                except:
                    pass

            lines.append(f"[{idx}] {time_str}{role_display}: {sender_info}{msg['content']}")

        return '\n\n'.join(lines)

    def format_as_json(self, messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """
        将清洗后的消息格式化为精简 JSON（用于保存 clean_session）

        Returns:
            [{"r": role, "s": sender, "t": timestamp, "c": content}, ...]
        """
        result = []
        for msg in messages:
            role_short = 'u' if msg.get('role') == 'user' else 'a'
            result.append({
                'r': role_short,
                's': msg.get('sender', ''),
                't': str(msg.get('timestamp', '')),
                'c': msg.get('content', '')[:500]  # 截断避免过大
            })
        return result
