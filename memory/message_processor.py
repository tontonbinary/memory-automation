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
                           max_messages_per_chunk: int = 200) -> List[Tuple[List[Dict[str, Any]], int, str]]:
        """
        将消息列表切分成多个块

        Args:
            messages: 消息列表
            max_messages_per_chunk: 每块最大消息数，默认 200

        Returns:
            [(messages_chunk, chunk_idx, chunk_name), ...]
            - messages_chunk: 该块的消息列表
            - chunk_idx: 块索引（从1开始）
            - chunk_name: 块名称（如 "03-25#L1"）
        """
        if not messages:
            return []
        
        # 获取 session 日期（从第一条消息的 timestamp）
        session_date = None
        if messages and messages[0].get('timestamp'):
            ts = messages[0]['timestamp']
            if isinstance(ts, str) and len(ts) >= 10:
                session_date = ts[:10].replace("-", "")[4:]  # MMDD 格式
        
        if not session_date:
            session_date = datetime.now().strftime("%m%d")

        chunks = []
        total_messages = len(messages)
        
        # 计算需要的块数
        num_chunks = (total_messages + max_messages_per_chunk - 1) // max_messages_per_chunk
        
        for chunk_idx in range(num_chunks):
            start_idx = chunk_idx * max_messages_per_chunk
            end_idx = min(start_idx + max_messages_per_chunk, total_messages)
            
            chunk_messages = messages[start_idx:end_idx]
            # 块名称格式: MMDD#L{N} （L 表示 LLM chunk）
            chunk_name = f"{session_date}#L{chunk_idx + 1}"
            
            chunks.append((chunk_messages, chunk_idx + 1, chunk_name))
        
        return chunks

    def _save_clean_session(self, cleaned_messages: List[Dict[str, Any]], 
                           chunk_name: str) -> Optional[Path]:
        """
        保存清洗后的消息到 clean_session 目录
        
        Args:
            cleaned_messages: 清洗后的消息列表
            chunk_name: 块名称（如 "03-25#L1"）
            
        Returns:
            保存的文件路径，或 None（失败时）
        """
        # 获取 clean_session 目录（优先用 config，fallback 到 agent 目录）
        clean_dir_str = self.config.get("output", {}).get("clean_session_dir",
            f"~/.openclaw/agents/{self.agent_id}/clean_session")
        clean_dir = Path(clean_dir_str).expanduser()
        
        try:
            clean_dir.mkdir(parents=True, exist_ok=True)
            clean_path = clean_dir / f"{chunk_name}.json"
            
            # 保存为 JSON 格式，包含完整的消息内容
            with open(clean_path, 'w', encoding='utf-8') as f:
                json.dump(cleaned_messages, f, ensure_ascii=False, indent=2)
            
            return clean_path
        except Exception as e:
            print(f"[MessageProcessor] 保存 clean_session 失败: {e}")
            return None

    def process_session(self, messages: List[Dict[str, Any]],
                       force: bool = False) -> Tuple[int, List[Dict[str, Any]], Optional[str]]:
        """
        处理会话消息，蒸馏并写入 L1

        流程（优化后 v3 - 修复切块顺序）：
        1. 预清洗全部消息（parentId 链过滤 + 富文本提取 + _clean_content）
        2. 切块（控制 LLM 上下文长度）
        3. 对每个块：
           a. 保存 clean_session
           b. LLM 蒸馏该块
           c. 写入 L1

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

        # 2. 切块（在蒸馏前切块，控制 LLM 上下文长度）
        chunk_size = self.config.get("distillation", {}).get("max_messages_per_chunk", 200)
        chunks = self._get_session_chunks(cleaned_all, max_messages_per_chunk=chunk_size)
        print(f"[MessageProcessor] 切块: {len(chunks)} 块，每块最多 {chunk_size} 条消息")

        total_lines = 0
        all_items = []

        # 3. 对每个块：保存 clean_session → 蒸馏 → 写入 L1
        for chunk_messages, chunk_idx, chunk_name in chunks:
            print(f"[MessageProcessor] 处理块 {chunk_idx}/{len(chunks)}: {len(chunk_messages)} 条消息")

            # 3.1 保存 clean_session（已清洗）
            clean_path = self._save_clean_session(chunk_messages, chunk_name)

            # 3.2 对该块进行 LLM 蒸馏
            raw_items = self.distiller.distill_messages(chunk_messages, use_llm=True, pre_cleaned=True)

            if raw_items is None:
                print(f"[MessageProcessor] 块 {chunk_idx} LLM 蒸馏失败，跳过")
                continue

            if not raw_items:
                print(f"[MessageProcessor] 块 {chunk_idx} 无有效内容可提取")
                continue

            # 转换 DistilledItem 为 dict，并展开 timestamp
            chunk_items = []
            for item in raw_items:
                if hasattr(item, 'item_type'):
                    d = asdict(item)
                    d.pop('follow_up', None)
                    d.pop('outcome', None)
                    # source_idx 是相对于当前块的，需要保持
                    src_idx = d.get('source_idx', 0)
                    if src_idx and 1 <= src_idx <= len(chunk_messages):
                        d['timestamp'] = chunk_messages[src_idx - 1].get('timestamp', '')
                    chunk_items.append(d)
                else:
                    chunk_items.append(item)

            if not chunk_items:
                print(f"[MessageProcessor] 块 {chunk_idx} 蒸馏后无有效项")
                continue

            # 事件类型判断
            chunk_items = self._classify_event_types(chunk_items)

            # 提取 timestamps
            item_times = []
            for item in chunk_items:
                ts = item.get('timestamp', '') if isinstance(item, dict) else getattr(item, 'timestamp', '')
                item_times.append(ts or '')

            session_start_time = chunk_messages[0].get('timestamp') if chunk_messages else None

            # 3.3 写入 L1
            lines_written = self.l1_writer.write(
                chunk_items, session_start_time, item_times=item_times,
                source=f"clean_session/{chunk_name}")

            print(f"[MessageProcessor] 块 {chunk_idx}: {len(chunk_items)} 项 -> {lines_written} 行")

            total_lines += lines_written
            all_items.extend(chunk_items)

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

        total_items = 0
        all_items = []

        for old_file in old_files:
            print(f"[MessageProcessor] 处理旧文件: {old_file}")

            # 读取旧 session 的消息
            messages = self.session_manager.read_session_messages(old_file)

            if not messages:
                print(f"[MessageProcessor] 旧文件无消息: {old_file}")
                continue

            # 如果指定了 last_processed_msg_id，只处理该 ID 之后的消息
            if last_processed_msg_id:
                start_idx = None
                for idx, msg in enumerate(messages):
                    if msg.get('id') == last_processed_msg_id:
                        start_idx = idx + 1
                        break

                if start_idx is not None and start_idx < len(messages):
                    messages = messages[start_idx:]
                    print(f"[MessageProcessor] 从上次位置后继续: {len(messages)} 条新消息")
                elif start_idx is not None:
                    print(f"[MessageProcessor] 旧 session 无新消息")
                    continue
                else:
                    # last_processed_msg_id 不在消息列表中，全量处理
                    print(f"[MessageProcessor] 未找到上次处理位置，全量处理: {len(messages)} 条")

            # 处理这些消息
            lines_written, items, _ = self.process_session(messages, force=True)

            total_items += len(items)
            all_items.extend(items)

        return total_items, all_items

    def _classify_event_types(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        判断事件类型（基于 agent_types 和消息内容）

        Args:
            items: 蒸馏项列表

        Returns:
            添加 event_type 字段后的列表
        """
        # 从 reference_manager 获取 agent 类型
        agent_types = []
        if self.reference_manager:
            agent_types = self.reference_manager.get_agent_type()
            if isinstance(agent_types, str):
                agent_types = [agent_types]

        # 默认类型映射
        for item in items:
            item_type = item.get('item_type', '').lower()
            content = item.get('content', '').lower()

            # 基于 item_type 初判
            if item_type in ['preference', 'emotion']:
                item['event_type'] = 'SocialEcology'
            elif item_type in ['decision', 'action']:
                item['event_type'] = 'RuleDecision'
            elif item_type == 'improvement':
                item['event_type'] = 'SelfEvolve'
            elif item_type == 'event':
                # 基于内容进一步判断
                if any(kw in content for kw in ['项目', '开发', '代码', '系统']):
                    item['event_type'] = 'CoreWork'
                elif any(kw in content for kw in ['临时', '帮忙', '协助']):
                    item['event_type'] = 'EventsOutside'
                else:
                    item['event_type'] = 'CoreWork'  # 默认
            else:
                item['event_type'] = 'CoreWork'  # 默认

        return items
