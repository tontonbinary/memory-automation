#!/usr/bin/env python3
"""
Session Manager - Session 管理模块
处理会话的获取、查找和读取
"""

import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


class SessionManager:
    """Session 管理器"""

    def __init__(self, agent_id: str, state_manager=None):
        self.agent_id = agent_id
        self.state_manager = state_manager

    def get_current_session(self) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
        """
        获取当前会话信息，只返回上次处理后新增的消息

        Returns:
            (session_key, messages, last_msg_id)
        """
        try:
            # 使用 openclaw CLI 获取当前会话
            result = subprocess.run(
                ["openclaw", "sessions", "--agent", self.agent_id, "--json"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                print(f"[SessionManager] 获取会话失败: {result.stderr}")
                return "", [], None

            data = json.loads(result.stdout)
            sessions = data.get("sessions", [])

            if not sessions:
                return "", [], None

            # 获取最新会话
            latest = sessions[0]
            session_key = latest.get("key", "")
            session_id = latest.get("sessionId", "")

            # 直接读取 session JSONL 文件
            session_file = Path(f"~/.openclaw/agents/{self.agent_id}/sessions/{session_id}.jsonl").expanduser()

            if not session_file.exists():
                print(f"[SessionManager] Session file not found: {session_file}")
                return session_key, [], None

            # 获取上次处理的消息ID
            last_processed_msg_id = None
            if self.state_manager:
                last_processed_msg_id = self.state_manager.get_last_processed_msg_id()

            # 读取 JSONL 文件解析消息
            all_messages = []
            last_msg_id = None

            with open(session_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("type") == "message":
                            # 生成消息ID（如果没有）
                            msg_id = entry.get("id") or entry.get("msg_id") or f"msg_{len(all_messages)}"
                            # 提取消息字段
                            msg = {
                                "role": entry.get("role", ""),
                                "content": entry.get("content", ""),
                                "timestamp": entry.get("timestamp", ""),
                                "msg_id": msg_id
                            }
                            all_messages.append(msg)
                            last_msg_id = msg_id
                    except json.JSONDecodeError:
                        continue

            # 如果只想要新消息，过滤掉已处理的消息
            if last_processed_msg_id:
                new_messages = []
                found_last = False
                last_msg = None  # 记录最后一条消息
                for msg in all_messages:
                    last_msg = msg
                    if found_last:
                        new_messages.append(msg)
                    elif msg.get("msg_id") == last_processed_msg_id:
                        found_last = True
                        # 不添加当前消息（跳过已处理的）

                # 如果没找到上次处理的消息ID，返回所有消息（可能是新会话）
                if not found_last:
                    new_messages = all_messages
                
                # 如果找到了但没有后续消息，说明目标就是最后一条
                # 这种情况下返回目标消息本身，用于更新 last_processed_msg_id
                if found_last and not new_messages and last_msg:
                    # 目标就是最后一条消息，不需要更新（已经是最新）
                    pass

                print(f"[SessionManager] 过滤后消息数: {len(new_messages)}/{len(all_messages)}")
                return session_key, new_messages, last_msg_id
            else:
                # 首次处理，返回所有消息
                return session_key, all_messages, last_msg_id

        except subprocess.TimeoutExpired:
            print("[SessionManager] ⚠️ 获取会话超时，请检查网络或 openclaw 服务")
            return "", [], None  # 保持兼容，但日志已改进
        except json.JSONDecodeError as e:
            print(f"[SessionManager] ❌ 解析 JSON 失败: {e}，请检查 session 文件格式")
            return "", [], None
        except Exception as e:
            print(f"[SessionManager] ❌ 获取会话异常: {e}")
            return "", [], None

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
                # 匹配所有 .jsonl 文件（排除所有 reset 版本），然后检查内容中的 session_key
                elif name.endswith(".jsonl") and ".reset." not in name and not name.endswith(".bak"):
                    # 读取文件检查 session_key
                    try:
                        with open(f, 'r', encoding='utf-8') as fh:
                            first_line = fh.readline()
                            if old_session_key in first_line:
                                found_files.append(f)
                    except Exception:
                        continue

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
                            msg_id = entry.get("id") or entry.get("msg_id") or f"msg_{len(messages)}"
                            msg = {
                                "role": entry.get("role", ""),
                                "content": entry.get("content", ""),
                                "timestamp": entry.get("timestamp", ""),
                                "msg_id": msg_id
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
