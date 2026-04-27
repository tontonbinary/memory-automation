#!/usr/bin/env python3
"""
Session Manager - Session 管理模块
处理会话的获取、查找、读取和状态管理
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


class SessionManager:
    """Session 管理器（合并 state_manager 功能）"""

    def __init__(self, agent_id: str, state_file: Optional[str] = None):
        self.agent_id = agent_id
        # 状态文件路径（取代 state_manager）
        if state_file:
            self.state_file = Path(state_file).expanduser()
        else:
            self.state_file = Path(f"~/.openclaw/workspaces/{agent_id}/workspace/memory/heartbeat-state.json").expanduser()
        self._ensure_directory()

    def _ensure_directory(self):
        """确保状态文件所在目录存在"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> Dict[str, Any]:
        """加载状态"""
        if not self.state_file.exists():
            return {
                "last_session_key": None,
                "last_processed_time": None,
                "last_processed_msg_id": None,
                "last_saved_messages": 0,
                "version": "2.0.0"
            }
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return {
                        "last_session_key": None,
                        "last_processed_time": None,
                        "last_processed_msg_id": None,
                        "last_saved_messages": 0,
                        "version": "2.0.0"
                    }
                return json.loads(content)
        except (json.JSONDecodeError, IOError):
            return {
                "last_session_key": None,
                "last_processed_time": None,
                "last_processed_msg_id": None,
                "last_saved_messages": 0,
                "version": "2.0.0"
            }

    def _save_state(self, state: Dict[str, Any]) -> bool:
        """保存状态"""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            return True
        except IOError as e:
            print(f"[SessionManager] 保存状态失败: {e}")
            return False

    def update_last(self, session_key: str, last_msg_id: Optional[str], message_count: int = 0) -> bool:
        """
        更新最后处理的 session 信息（取代 state_manager.update_after_process）

        Args:
            session_key: 当前 session key
            last_msg_id: 最后处理的消息 ID
            message_count: 本次处理的消息数

        Returns:
            是否保存成功
        """
        state = self._load_state()
        state.update({
            "last_session_key": session_key,
            "last_processed_time": datetime.now().isoformat(),
            "last_processed_msg_id": last_msg_id,
            "last_saved_messages": message_count
        })
        return self._save_state(state)

    def get_last_processed_msg_id(self) -> Optional[str]:
        """获取上次处理的最后消息 ID"""
        state = self._load_state()
        return state.get("last_processed_msg_id")

    def check_should_process(self, session_key: str, interval_minutes: int = 30) -> Tuple[bool, str]:
        """
        检查是否需要处理（取代 state_manager.check_should_process）

        Args:
            session_key: 当前 session key
            interval_minutes: 最小处理间隔（分钟）

        Returns:
            (是否需要处理, 原因)
        """
        state = self._load_state()
        last_time = state.get("last_processed_time")
        last_session = state.get("last_session_key")

        if not last_time:
            return True, "首次处理"

        if last_session != session_key:
            return True, f"session_key 变化: {last_session} -> {session_key}"

        # 检查时间间隔
        try:
            last_dt = datetime.fromisoformat(last_time.replace("Z", "+00:00"))
            now_dt = datetime.now()
            diff_minutes = (now_dt - last_dt).total_seconds() / 60

            if diff_minutes >= interval_minutes:
                return True, f"时间间隔足够 ({diff_minutes:.0f} 分钟)"
            else:
                return False, f"时间间隔不足 ({diff_minutes:.0f} 分钟 < {interval_minutes} 分钟)"
        except (ValueError, TypeError):
            return True, "时间解析异常，重新处理"

    def get_current_session(self) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
        """
        获取当前会话信息（扫描 sessions 目录，不依赖 openclaw sessions 命令）

        逻辑：
        1. 优先使用状态文件记录的 last_session_key 对应的文件
        2. 否则找到 sessions 目录下最近修改的 .jsonl 文件

        Returns:
            (session_key, messages, last_msg_id)
        """
        sessions_dir = self._get_sessions_dir()

        if not sessions_dir.exists():
            print(f"[SessionManager] Sessions 目录不存在: {sessions_dir}")
            return "", [], None

        # 获取所有 session 文件（包括 reset 的）
        session_files = []
        for f in sessions_dir.iterdir():
            if f.is_file() and (f.suffix == '.jsonl' or '.jsonl.' in f.name):
                session_files.append(f)

        if not session_files:
            print(f"[SessionManager] Sessions 目录为空: {sessions_dir}")
            return "", [], None

        # 优先用状态文件记录的 session
        state = self._load_state()
        last_session_key = state.get("last_session_key")

        # 找最近修改的 session 文件
        # 排序：优先 last_session_key 对应的文件，然后按修改时间
        def sort_key(f):
            # 优先 last_session_key 对应的文件
            is_last = (last_session_key and (
                f.name == f"{last_session_key}.jsonl" or
                f.name.startswith(f"{last_session_key}.jsonl.")
            ))
            # 按修改时间降序
            mtime = f.stat().st_mtime
            return (not is_last, -mtime)

        session_files.sort(key=sort_key)
        session_file = session_files[0]

        # 从文件名构造 session_key（去掉 .jsonl 相关后缀）
        session_id = session_file.stem.replace('.reset.', '.').replace('.bak', '')
        session_key = last_session_key or session_id

        print(f"[SessionManager] 使用 session 文件: {session_file.name} (mtime={datetime.fromtimestamp(session_file.stat().st_mtime)})")

        # 读取消息
        all_messages, last_msg_id = self._read_messages_from_session_file(session_file)

        if not all_messages:
            print(f"[SessionManager] Session 文件无消息: {session_file}")
            return session_key, [], None

        # 过滤已处理的消息
        last_processed_msg_id = self.get_last_processed_msg_id()
        if last_processed_msg_id:
            id_exists = any(msg.get("id") == last_processed_msg_id for msg in all_messages)

            if not id_exists:
                print(f"[SessionManager] ⚠️ last_processed_msg_id={last_processed_msg_id} 不在当前 session 文件，全量处理 ({len(all_messages)} 条)")
                return session_key, all_messages, last_msg_id

            # 过滤
            new_messages = []
            found_last = False
            for msg in all_messages:
                if found_last:
                    new_messages.append(msg)
                elif msg.get("id") == last_processed_msg_id:
                    found_last = True

            print(f"[SessionManager] ✅ 过滤: last={last_processed_msg_id}, 过滤后={len(new_messages)}/{len(all_messages)} 条")
            return session_key, new_messages, last_msg_id
        else:
            print(f"[SessionManager] 首次处理，全量返回 ({len(all_messages)} 条)")
            return session_key, all_messages, last_msg_id

    def _get_sessions_dir(self) -> Path:
        """
        获取当前 agent 的 sessions 目录

        Returns:
            sessions 目录路径
        """
        return Path(f"~/.openclaw/agents/{self.agent_id}/sessions").expanduser()

    def find_old_session_files(self, old_session_key: str) -> List[Path]:
        """
        查找旧 session 的文件（包括已被 reset 的 session）

        查找逻辑：
        - 活跃 session: {session_id}.jsonl
        - 已 reset session: {session_id}.jsonl.reset.* 或 {session_id}.jsonl.bak

        Args:
            old_session_key: 旧的 session_key

        Returns:
            找到的 session 文件路径列表
        """
        sessions_dir = self._get_sessions_dir()
        if not sessions_dir.exists():
            print(f"[SessionManager] Sessions 目录不存在: {sessions_dir}")
            return []

        found_files = []

        # 遍历 sessions 目录查找匹配的文件
        for f in sessions_dir.iterdir():
            if f.is_file():
                # 匹配模式：
                # 1. {old_session_key}.jsonl（如果 session_key 就是 session_id）
                # 2. {something}.jsonl.reset.* 或 {something}.jsonl.bak（reset 过的）
                name = f.name

                # 直接匹配 session_key
                if name == f"{old_session_key}.jsonl":
                    found_files.append(f)
                # 匹配 reset 文件：session_id.jsonl.reset.N 或 session_id.jsonl.bak
                elif ".reset." in name or name.endswith(".bak"):
                    # 检查基础 session_id 是否匹配
                    base = name.replace(".jsonl.reset.", ".").replace(".jsonl.bak", "")
                    if base == old_session_key or name.startswith(f"{old_session_key}."):
                        found_files.append(f)
                # 注意：不支持通过读取文件内容来匹配 session_key
                # session_key 必须是文件名的一部分（精确匹配、前缀匹配、或 reset 文件模式）

        print(f"[SessionManager] 查找旧 session {old_session_key} -> 找到 {len(found_files)} 个文件: {[str(f) for f in found_files]}")
        return found_files

    def _read_messages_from_session_file(self, session_file: Path,
                                          after_msg_id: Optional[str] = None
                                          ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        从 session 文件中读取消息

        Args:
            session_file: session 文件路径
            after_msg_id: 只读取此消息ID之后的消息

        Returns:
            (messages, last_msg_id)
        """
        messages = []
        last_msg_id = None

        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("type") == "message":
                            msg_id = entry.get("id", "") or f"msg_{len(messages)}"
                            parent_id = entry.get("parentId", "")
                            msg_data = entry.get("message", {})
                            msg = {
                                "role": msg_data.get("role", ""),
                                "content": msg_data.get("content", ""),
                                "id": msg_id,
                                "parentId": parent_id,
                                "timestamp": entry.get("timestamp", "")
                            }

                            # 过滤：如果指定了 after_msg_id，跳过之前的消息
                            if after_msg_id:
                                if msg_id == after_msg_id:
                                    # 找到目标ID，继续读取后续消息
                                    after_msg_id = None  # 关闭过滤器
                                continue

                            messages.append(msg)
                            last_msg_id = msg_id
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"[SessionManager] 读取 session 文件失败 {session_file}: {e}")

        return messages, last_msg_id
