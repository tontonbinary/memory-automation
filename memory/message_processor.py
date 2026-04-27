#!/usr/bin/env python3
"""
Message Processor - 消息处理模块（简化版）
只负责保存 clean_session，不再切块、不做 LLM 蒸馏
"""

import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from .session_distiller import SessionCleaner
from .session_manager import SessionManager


class MessageProcessor:
    """消息处理器 - 简化版（不切块）"""

    def __init__(self, agent_id: str, config: Dict[str, Any],
                 session_manager: SessionManager,
                 cleaner: SessionCleaner):
        self.agent_id = agent_id
        self.config = config
        self.session_manager = session_manager
        self.cleaner = cleaner

    def _get_date_str(self, messages: List[Dict[str, Any]]) -> str:
        """从消息中获取日期字符串（北京时间）"""
        if messages and messages[0].get('timestamp'):
            ts = messages[0]['timestamp']
            if isinstance(ts, str) and len(ts) >= 10:
                try:
                    # 处理 UTC 时间转换为北京时间
                    ts_clean = ts.replace('Z', '+00:00')
                    dt = datetime.fromisoformat(ts_clean)
                    # 转换为北京时间
                    bj = timezone(timedelta(hours=8))
                    dt_bj = dt.astimezone(bj)
                    return dt_bj.strftime("%Y-%m-%d")
                except:
                    pass
        return datetime.now().strftime("%Y-%m-%d")

    def _save_clean_session(self, cleaned_messages: List[Dict[str, Any]],
                           date_str: str) -> Optional[Path]:
        """
        保存清洗后的消息到 clean_session 目录（追加模式）
        每天只保存一个文件：{YYYY-MM-DD}.json
        """
        clean_dir_str = self.config.get("output", {}).get("clean_session_dir",
            f"~/.openclaw/agents/{self.agent_id}/clean_session")
        clean_dir = Path(clean_dir_str).expanduser()

        try:
            clean_dir.mkdir(parents=True, exist_ok=True)
            clean_path = clean_dir / f"{date_str}.json"

            # 读取已有内容（如果存在）
            existing_data = []
            if clean_path.exists():
                try:
                    with open(clean_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                except:
                    pass  # 文件损坏则覆盖

            # 追加新消息
            new_data = self.cleaner.format_as_json(cleaned_messages)
            all_data = existing_data + new_data

            # 保存
            with open(clean_path, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)

            msg_count = len(new_data)
            total_count = len(all_data)
            print(f"[MessageProcessor] 保存 {msg_count} 条到 {clean_path}（共 {total_count} 条）")
            return clean_path
        except Exception as e:
            print(f"[MessageProcessor] 保存 clean_session 失败: {e}")
            return None

    def process_session(self, messages: List[Dict[str, Any]],
                       force: bool = False) -> Tuple[int, List[Path]]:
        """
        处理会话消息：清洗 → 保存到当天的单个 clean_session 文件

        Returns:
            (保存的文件数, clean_session 文件路径列表)
        """
        if not messages:
            return 0, []

        # 1. 清洗消息
        cleaned = self.cleaner.clean_messages(messages)
        if not cleaned:
            print("[MessageProcessor] 清洗后无有效消息")
            return 0, []

        print(f"[MessageProcessor] 清洗完成: {len(messages)} 条 -> {len(cleaned)} 条")

        # 2. 获取当天的日期字符串
        date_str = self._get_date_str(messages)

        # 3. 保存到当天的单个文件
        clean_path = self._save_clean_session(cleaned, date_str)

        if clean_path:
            print(f"[MessageProcessor] 完成: {clean_path}")
            return 1, [clean_path]

        return 0, []

    def process_old_session(self, old_session_key: str,
                           last_processed_msg_id: Optional[str] = None) -> Tuple[int, List[Path]]:
        """
        处理旧 session 中未保存的消息

        Returns:
            (保存的文件数, clean_session 文件路径列表)
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
