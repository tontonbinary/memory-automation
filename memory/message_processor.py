#!/usr/bin/env python3
"""
Message Processor - 消息处理模块
处理会话消息的蒸馏和写入
"""

import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from dataclasses import asdict

from .session_distiller import SessionDistiller
from .l1_writer import L1Writer
from .session_manager import SessionManager
from .reference_manager import ReferenceManager


class MessageProcessor:
    """消息处理器"""

    def __init__(self, agent_id: str, config: Dict[str, Any],
                 session_manager: SessionManager,
                 l1_writer: L1Writer,
                 distiller: SessionDistiller,
                 reference_manager: Optional[ReferenceManager] = None):
        self.agent_id = agent_id
        self.config = config
        self.session_manager = session_manager
        self.l1_writer = l1_writer
        self.distiller = distiller
        self.reference_manager = reference_manager

    def _get_session_chunks(self, messages: List[Dict[str, Any]], 
                           max_messages_per_chunk: int = 600) -> List[Tuple[List[Dict[str, Any]], int, str]]:
        """
        将消息列表切分成多个块

        Args:
            messages: 消息列表
            max_messages_per_chunk: 每块最大消息数，默认 600

        Returns:
            [(messages_chunk, chunk_idx, chunk_name), ...]
            - messages_chunk: 该块的消息列表
            - chunk_idx: 块索引（从1开始）
            - chunk_name: 块名称（如 "03-25#L1"）
        """
        if not messages:
            return []

        # 从第一条消息获取日期
        first_ts = messages[0].get("timestamp", "") if messages else ""
        date_str = first_ts[:10] if first_ts else datetime.now().strftime("%m-%d")
        # 格式化为 MM-DD
        if "-" in date_str and len(date_str) == 10:
            date_str = date_str[5:7] + "-" + date_str[8:10]  # "03-25"
        else:
            date_str = datetime.now().strftime("%m-%d")

        chunks = []
        total = len(messages)

        for i in range(0, total, max_messages_per_chunk):
            chunk_messages = messages[i:i + max_messages_per_chunk]
            chunk_idx = (i // max_messages_per_chunk) + 1
            chunk_name = f"{date_str}#L{chunk_idx}"
            chunks.append((chunk_messages, chunk_idx, chunk_name))

        return chunks

    def _save_clean_session(self, chunk_messages: List[Dict[str, Any]], 
                           chunk_name: str) -> Optional[Path]:
        """
        保存清洗后的 session 块到文件

        Args:
            chunk_messages: 块的消息列表
            chunk_name: 块名称（如 "03-25#L1"）

        Returns:
            保存的文件路径，或 None（失败时）
        """
        # 获取 clean_session 目录（优先用 config，fallback 到 agent 目录）
        clean_dir_str = self.config.get("output", {}).get("clean_session_dir",
            f"~/.openclaw/agents/{self.agent_id}/clean_session")
        clean_dir = Path(clean_dir_str).expanduser()
        clean_dir.mkdir(parents=True, exist_ok=True)

        file_path = clean_dir / f"{chunk_name}.json"

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(chunk_messages, f, ensure_ascii=False, indent=2)
            print(f"[MessageProcessor] 保存 clean_session: {file_path} ({len(chunk_messages)} 条)")
            return file_path
        except IOError as e:
            print(f"[MessageProcessor] 保存 clean_session 失败: {e}")
            return None

    def process_session(self, messages: List[Dict[str, Any]],
                       force: bool = False) -> Tuple[int, List[Dict[str, Any]], Optional[str]]:
        """
        处理会话消息，蒸馏并写入 L1

        流程（优化后 v2）：
        1. 预清洗全部消息（parentId 链过滤 + 富文本提取 + _clean_content）
        2. 对完整清洗消息蒸馏（得绝对 source_idx）
        3. 切块（为 clean_session 文件保存 + L1 批次分组）
        4. 保存每个块到 clean_session
        5. 按块分组蒸馏结果，写入对应 L1

        Args:
            messages: 消息列表
            force: 是否强制处理（忽略状态检查）

        Returns:
            (总写入行数, 所有蒸馏项列表, 最后消息ID)
        """
        if not messages:
            return 0, [], None

        # 1. 预清洗全部消息
        cleaned_all = self.distiller.pre_clean_messages(messages)

        if not cleaned_all:
            print("[MessageProcessor] 预清洗后无有效消息")
            return 0, [], None

        print(f"[MessageProcessor] 预清洗完成: {len(messages)} 条 -> {len(cleaned_all)} 条")

        # 2. 对完整清洗消息蒸馏（一次性，得到绝对 source_idx）
        raw_items = self.distiller.distill_messages(cleaned_all, use_llm=True, pre_cleaned=True)

        # 转换 DistilledItem dataclass 为 dict，展开 timestamp
        distilled_all = []
        for item in raw_items:
            if hasattr(item, 'item_type'):
                d = asdict(item)
                d.pop('follow_up', None)
                d.pop('outcome', None)
                # 用 source_idx（1-based）从 cleaned_all 取对应 timestamp
                src_idx = d.get('source_idx', 0)
                if src_idx and 1 <= src_idx <= len(cleaned_all):
                    d['timestamp'] = cleaned_all[src_idx - 1].get('timestamp', '')
                distilled_all.append(d)
            else:
                distilled_all.append(item)

        if not distilled_all:
            print("[MessageProcessor] 蒸馏无有效结果")
            return 0, [], cleaned_all[-1].get('id') if cleaned_all else None

        # 事件类型判断
        distilled_all = self._classify_event_types(distilled_all)

        # 3. 切块（用于 clean_session 保存 + L1 分组）
        chunks = self._get_session_chunks(cleaned_all, max_messages_per_chunk=600)
        print(f"[MessageProcessor] 切块: {len(chunks)} 块，共 {len(distilled_all)} 项蒸馏结果")

        total_lines = 0
        all_items = []

        # 4. 对每个块：保存 clean_session + 筛选该块的蒸馏结果写 L1
        chunk_start = 0
        for chunk_messages, chunk_idx, chunk_name in chunks:
            chunk_size = len(chunk_messages)
            chunk_end = chunk_start + chunk_size  # exclusive

            # 4.1 保存 clean_session（已清洗）
            clean_path = self._save_clean_session(chunk_messages, chunk_name)

            # 4.2 筛选 source_idx 落在 [chunk_start, chunk_end) 的蒸馏项
            chunk_items = [
                item for item in distilled_all
                if item.get('source_idx') and chunk_start < item['source_idx'] <= chunk_end
            ]

            if not chunk_items:
                print(f"[MessageProcessor] 块 {chunk_idx} 无蒸馏项，跳过")
                chunk_start = chunk_end
                continue

            # 提取 timestamps（与 chunk_items 对齐）
            item_times = []
            for item in chunk_items:
                ts = item.get('timestamp', '') if isinstance(item, dict) else getattr(item, 'timestamp', '')
                item_times.append(ts or '')

            session_start_time = chunk_messages[0].get('timestamp') if chunk_messages else None

            # 4.3 写入 L1
            lines_written = self.l1_writer.write(
                chunk_items, session_start_time, item_times=item_times,
                source=f"clean_session/{chunk_name}")

            print(f"[MessageProcessor] 块 {chunk_idx}: {len(chunk_items)} 项 -> {lines_written} 行")

            total_lines += lines_written
            all_items.extend(chunk_items)
            chunk_start = chunk_end

        last_msg_id = cleaned_all[-1].get('id') if cleaned_all else None
        print(f"[MessageProcessor] 处理完成: {len(chunks)} 块, 共 {total_lines} 行, {len(all_items)} 项")
        return total_lines, all_items, last_msg_id

    def process_old_session(self, old_session_key: str,
                           last_processed_msg_id: Optional[str] = None) -> Tuple[int, List[Dict[str, Any]]]:
        """
        处理旧 session 中未蒸馏的消息

        在 session 切换时调用，用于补救处理，避免消息遗漏

        Args:
            old_session_key: 旧 session 的 session_key
            last_processed_msg_id: 上次处理到的消息ID

        Returns:
            (distilled_count, items)
        """
        print(f"[MessageProcessor] 开始处理旧 session: {old_session_key}, last_msg_id: {last_processed_msg_id}")

        # 查找旧 session 文件
        old_files = self.session_manager.find_old_session_files(old_session_key)

        if not old_files:
            print(f"[MessageProcessor] 未找到旧 session 文件: {old_session_key}")
            return 0, []

        all_messages = []
        # 按文件修改时间排序，最新的优先
        old_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        # 收集所有未处理的消息
        for session_file in old_files:
            messages, _ = self.session_manager._read_messages_from_session_file(session_file, last_processed_msg_id)
            all_messages.extend(messages)

        if not all_messages:
            print(f"[MessageProcessor] 旧 session 无新消息需要处理")
            return 0, []

        print(f"[MessageProcessor] 从旧 session 收集到 {len(all_messages)} 条消息待蒸馏")

        # 预清洗后蒸馏
        cleaned_messages = self.distiller.pre_clean_messages(all_messages)
        if not cleaned_messages:
            print("[MessageProcessor] 旧 session 预清洗后无有效消息")
            return 0, []

        # LLM 蒸馏（pre_cleaned=True）
        raw_items = self.distiller.distill_messages(cleaned_messages, use_llm=True, pre_cleaned=True)
        # 转换 DistilledItem dataclass 为 dict
        distilled_items = [asdict(item) if hasattr(item, 'item_type') else item for item in raw_items]

        if not distilled_items:
            print("[MessageProcessor] 旧 session 未提取到有效信息")
            return 0, []

        # 获取第一条消息的时间戳
        session_start_time = all_messages[0].get("timestamp") if all_messages else None

        # 从蒸馏项直接获取 timestamp
        item_times = []
        for item in distilled_items:
            ts = item.get('timestamp', '') if isinstance(item, dict) else getattr(item, 'timestamp', '')
            item_times.append(ts if ts else session_start_time or '')

        # 5 类事件类型判断
        distilled_items = self._classify_event_types(distilled_items)

        # 写入 L1
        lines_written = self.l1_writer.write(
            distilled_items, session_start_time, item_times=item_times)

        print(f"[MessageProcessor] 旧 session 已写入 {lines_written} 行，提取 {len(distilled_items)} 项")

        return len(distilled_items), distilled_items

    def _get_item_times_from_source_idx(self, distilled_items: List[Dict],
                                        messages: List[Dict]) -> List[str]:
        """
        通过 source_idx 直接查每条蒸馏项的原始 timestamp

        Args:
            distilled_items: 蒸馏项列表（含 source_idx）
            messages: 原始消息列表

        Returns:
            原始 timestamp 字符串列表，与 distilled_items 对齐
            格式如 "2026-03-30T20:04:22.758Z"（UTC）或 "2026-03-30T03:05:22.758+02:00"（欧洲）
        """
        item_times = []
        for item in distilled_items:
            source_idx = item.get('source_idx', 0)
            # source_idx 是 1-based，messages 是 0-based
            if source_idx and 1 <= source_idx <= len(messages):
                ts = messages[source_idx - 1].get('timestamp', '')
                item_times.append(ts if ts else '')
            elif messages:
                item_times.append(messages[0].get('timestamp', ''))
            else:
                item_times.append('')

        return item_times

    def _classify_event_types(self, distilled_items: List[Dict]) -> List[Dict]:
        """
        为每条蒸馏项判断事件类型（5 选 1）

        Args:
            distilled_items: 蒸馏项列表

        Returns:
            添加了 event_type 字段的蒸馏项列表
        """
        if not self.reference_manager:
            for item in distilled_items:
                item['event_type'] = 'CoreWork'
            return distilled_items

        for item in distilled_items:
            content = item.get('content', '')
            item_type = item.get('item_type', 'Event')
            event_type = self.reference_manager.classify_event_type(content, item_type)
            item['event_type'] = event_type

        return distilled_items
