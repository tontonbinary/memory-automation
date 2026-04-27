#!/usr/bin/env python3
"""
Message Processor - 消息处理模块（简化版）
只负责保存 clean_session，不再做 LLM 蒸馏和 L1 写入
"""

import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from .session_distiller import SessionCleaner
from .session_manager import SessionManager


class MessageProcessor:
    """消息处理器 - 简化版"""

    def __init__(self, agent_id: str, config: Dict[str, Any],
                 session_manager: SessionManager,
                 cleaner: SessionCleaner):
        self.agent_id = agent_id
        self.config = config
        self.session_manager = session_manager
        self.cleaner = cleaner

    def _get_session_chunks(self, messages: List[Dict[str, Any]],
                           max_messages_per_chunk: int = 200) -> List[Tuple[List[Dict[str, Any]], int, str]]:
        """
        将消息列表切分成多个块

        Returns:
            [(messages_chunk, chunk_idx, chunk_name), ...]
        """
        if not messages:
            return []

        # 获取 session 日期
        session_date = None
        if messages and messages[0].get('timestamp'):
            ts = messages[0]['timestamp']
            if isinstance(ts, str) and len(ts) >= 10:
                session_date = ts[:10].replace("-", "")[4:]  # MMDD

        if not session_date:
            session_date = datetime.now().strftime("%m%d")

        chunks = []
        total = len(messages)
        num_chunks = (total + max_messages_per_chunk - 1) // max_messages_per_chunk

        for chunk_idx in range(num_chunks):
            start = chunk_idx * max_messages_per_chunk
            end = min(start + max_messages_per_chunk, total)
            chunk_messages = messages[start:end]
            chunk_name = f"{session_date}#L{chunk_idx + 1}"
            chunks.append((chunk_messages, chunk_idx + 1, chunk_name))

        return chunks

    def _save_clean_session(self, cleaned_messages: List[Dict[str, Any]],
                           chunk_name: str) -> Optional[Path]:
        """
        保存清洗后的消息到 clean_session 目录
        """
        clean_dir_str = self.config.get("output", {}).get("clean_session_dir",
            f"~/.openclaw/agents/{self.agent_id}/clean_session")
        clean_dir = Path(clean_dir_str).expanduser()

        try:
            clean_dir.mkdir(parents=True, exist_ok=True)
            clean_path = clean_dir / f"{chunk_name}.json"

            # 保存为精简 JSON 格式
            data = self.cleaner.format_as_json(cleaned_messages)
            with open(clean_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"[MessageProcessor] 保存 clean_session: {clean_path}")
            return clean_path
        except Exception as e:
            print(f"[MessageProcessor] 保存 clean_session 失败: {e}")
            return None

    def process_session(self, messages: List[Dict[str, Any]],
                       force: bool = False) -> Tuple[int, List[Path]]:
        """
        处理会话消息：清洗 → 切块 → 保存 clean_session

        Returns:
            (保存的块数, clean_session 文件路径列表)
        """
        if not messages:
            return 0, []

        # 1. 清洗消息
        cleaned = self.cleaner.clean_messages(messages)
        if not cleaned:
            print("[MessageProcessor] 清洗后无有效消息")
            return 0, []

        print(f"[MessageProcessor] 清洗完成: {len(messages)} 条 -> {len(cleaned)} 条")

        # 2. 切块
        chunk_size = self.config.get("distillation", {}).get("max_messages_per_chunk", 200)
        chunks = self._get_session_chunks(cleaned, max_messages_per_chunk=chunk_size)
        print(f"[MessageProcessor] 切块: {len(chunks)} 块")

        # 3. 保存每块为 clean_session
        saved_paths = []
        for chunk_messages, chunk_idx, chunk_name in chunks:
            clean_path = self._save_clean_session(chunk_messages, chunk_name)
            if clean_path:
                saved_paths.append(clean_path)

        print(f"[MessageProcessor] 完成: 保存 {len(saved_paths)} 个 clean_session 文件")
        return len(saved_paths), saved_paths

    def process_old_session(self, old_session_key: str,
                           last_processed_msg_id: Optional[str] = None) -> Tuple[int, List[Path]]:
        """
        处理旧 session 中未保存的消息

        Returns:
            (保存的块数, clean_session 文件路径列表)
        """
        print(f"[MessageProcessor] 处理旧 session: {old_session_key}")

        old_files = self.session_manager.find_old_session_files(old_session_key)
        if not old_files:
            print(f"[MessageProcessor] 未找到旧 session 文件: {old_session_key}")
            return 0, []

        total_saved = 0
        all_paths = []

        for old_file in old_files:
            messages, _ = self.session_manager._read_messages_from_session_file(old_file)
            if not messages:
                continue

            # 如果指定了 last_processed_msg_id，只处理之后的消息
            if last_processed_msg_id:
                start_idx = None
                for idx, msg in enumerate(messages):
                    if msg.get('id') == last_processed_msg_id:
                        start_idx = idx + 1
                        break

                if start_idx is not None and start_idx < len(messages):
                    messages = messages[start_idx:]
                elif start_idx is not None:
                    continue

            saved, paths = self.process_session(messages, force=True)
            total_saved += saved
            all_paths.extend(paths)

        return total_saved, all_paths
