#!/usr/bin/env python3
"""
Message Processor - 消息处理模块
处理会话消息的蒸馏和写入
"""

from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from dataclasses import asdict

from .session_distiller import SessionDistiller
from .l1_writer import L1Writer
from .session_manager import SessionManager


class MessageProcessor:
    """消息处理器"""

    def __init__(self, agent_id: str, config: Dict[str, Any],
                 session_manager: SessionManager,
                 l1_writer: L1Writer,
                 distiller: SessionDistiller):
        self.agent_id = agent_id
        self.config = config
        self.session_manager = session_manager
        self.l1_writer = l1_writer
        self.distiller = distiller

    def process_session(self, messages: List[Dict[str, Any]],
                       force: bool = False) -> Tuple[int, List[Dict[str, Any]], Optional[str]]:
        """
        处理会话消息，蒸馏并写入 L1

        Args:
            messages: 消息列表
            force: 是否强制处理（忽略状态检查）

        Returns:
            (写入行数, 蒸馏项列表, 最后消息ID)
        """
        if not messages:
            return 0, [], None

        # LLM 蒸馏（支持 fallback 到正则）
        raw_items = self.distiller.distill_messages(messages, use_llm=True)
        # 转换 DistilledItem dataclass 为 dict（新格式：action/oput/improve）
        distilled_items = []
        for item in raw_items:
            if hasattr(item, 'item_type'):
                d = asdict(item)
                # 移除旧字段（兼容）
                d.pop('follow_up', None)
                d.pop('outcome', None)
                distilled_items.append(d)
            else:
                distilled_items.append(item)

        if not distilled_items:
            print("[MessageProcessor] 未提取到有效信息")
            # 返回最后一条消息的ID用于更新状态
            last_msg_id = messages[-1].get("msg_id") if messages else None
            return 0, [], last_msg_id

        # 获取第一条消息的时间戳作为 session 开始时间（用于推断时区）
        session_start_time = messages[0].get("timestamp") if messages else None

        # 用 source_idx 直接查每条蒸馏项的真实时间戳
        item_times = self._get_item_times_from_source_idx(distilled_items, messages)

        # 写入 L1
        lines_written = self.l1_writer.write(
            distilled_items, session_start_time, item_times=item_times)

        print(f"[MessageProcessor] 已写入 {lines_written} 行，提取 {len(distilled_items)} 项")

        # 获取最后一条消息的ID
        last_msg_id = messages[-1].get("msg_id") if messages else None

        return lines_written, distilled_items, last_msg_id

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

        # LLM 蒸馏（支持 fallback 到正则）
        raw_items = self.distiller.distill_messages(all_messages, use_llm=True)
        # 转换 DistilledItem dataclass 为 dict
        distilled_items = [asdict(item) if hasattr(item, 'item_type') else item for item in raw_items]

        if not distilled_items:
            print("[MessageProcessor] 旧 session 未提取到有效信息")
            return 0, []

        # 获取第一条消息的时间戳
        session_start_time = all_messages[0].get("timestamp") if all_messages else None

        # 用 source_idx 直接查时间
        item_times = self._get_item_times_from_source_idx(distilled_items, all_messages)

        # 写入 L1
        lines_written = self.l1_writer.write(
            distilled_items, session_start_time, item_times=item_times)

        print(f"[MessageProcessor] 旧 session 已写入 {lines_written} 行，提取 {len(distilled_items)} 项")

        return len(distilled_items), distilled_items

    def _get_item_times_from_source_idx(self, distilled_items: List[Dict],
                                        messages: List[Dict]) -> List[str]:
        """
        通过 source_idx 直接查每条蒸馏项的真实时间戳

        Args:
            distilled_items: 蒸馏项列表（含 source_idx）
            messages: 原始消息列表

        Returns:
            时间戳列表(HH:MM)，与 distilled_items 对齐
        """
        from datetime import datetime, timedelta
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            ZoneInfo = None

        def get_msg_time(msg: Dict) -> str:
            """从消息 timestamp 提取 HH:MM"""
            ts_utc = msg.get('timestamp', '')
            if not ts_utc:
                return '??:??'
            try:
                dt = datetime.fromisoformat(ts_utc.replace('Z', '+00:00'))
                if ZoneInfo is not None:
                    dt_local = dt.astimezone(ZoneInfo('Asia/Shanghai'))
                else:
                    dt_local = dt + timedelta(hours=8)
                return dt_local.strftime('%H:%M')
            except:
                return '??:??'

        item_times = []
        for item in distilled_items:
            source_idx = item.get('source_idx', 0)
            # source_idx 是 1-based，messages 是 0-based
            if source_idx and 1 <= source_idx <= len(messages):
                item_times.append(get_msg_time(messages[source_idx - 1]))
            elif messages:
                # 兜底：用第一条消息时间
                item_times.append(get_msg_time(messages[0]))
            else:
                item_times.append('??:??')

        return item_times
