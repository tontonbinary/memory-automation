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

        # 获取第一条消息的时间戳作为 session 开始时间
        session_start_time = messages[0].get("timestamp") if messages else None

        # 计算 per-item 时间戳：每个蒸馏项匹配最相关的原始消息
        item_times = self._compute_item_times(distilled_items, messages)

        # 写入 L1
        lines_written = self.l1_writer.write(distilled_items, session_start_time, item_times=item_times)

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

        # 获取第一条消息的时间戳作为 session 开始时间
        session_start_time = all_messages[0].get("timestamp") if all_messages else None

        # 计算 per-item 时间戳
        item_times = self._compute_item_times(distilled_items, all_messages)

        # 写入 L1
        lines_written = self.l1_writer.write(distilled_items, session_start_time, item_times=item_times)

        print(f"[MessageProcessor] 旧 session 已写入 {lines_written} 行，提取 {len(distilled_items)} 项")

        return len(distilled_items), distilled_items

    def _compute_item_times(self, distilled_items: List[Dict], messages: List[Dict]) -> List[str]:
        """
        计算每个蒸馏项的时间戳：匹配最相关的原始消息，使用该消息的时间戳

        Args:
            distilled_items: 蒸馏项列表
            messages: 原始消息列表

        Returns:
            时间戳列表(HH:MM)，与distilled_items对齐
        """
        import re
        from datetime import datetime
        from zoneinfo import ZoneInfo

        # 提取消息时间
        def get_msg_time(msg: Dict) -> str:
            ts_utc = msg.get('timestamp', '')
            try:
                dt = datetime.fromisoformat(ts_utc.replace('Z', '+00:00'))
                dt_sh = dt.astimezone(ZoneInfo('Asia/Shanghai'))
                return dt_sh.strftime('%H:%M')
            except:
                return '??:??'

        def get_msg_words(msg: Dict) -> set:
            content = msg.get('content', '')
            if isinstance(content, list):
                content = ' '.join(c.get('text','') for c in content if isinstance(c,dict))
            return set(re.findall(r'\w{3,}', str(content).lower()))

        def get_item_words(item_content: str) -> set:
            return set(re.findall(r'\w{3,}', str(item_content).lower()))

        item_times = []
        for item in distilled_items:
            item_words = get_item_words(item.get('content', ''))
            best_j = -1
            best_score = 0
            for j, msg in enumerate(messages):
                msg_words = get_msg_words(msg)
                if not item_words or not msg_words:
                    continue
                score = len(item_words & msg_words) / len(item_words | msg_words)
                if score > best_score:
                    best_score = score
                    best_j = j
            if best_j >= 0 and best_score >= 0.02:
                item_times.append(get_msg_time(messages[best_j]))
            else:
                # 找不到匹配，使用第一条消息时间
                item_times.append(get_msg_time(messages[0]) if messages else '??:??')

        return item_times
