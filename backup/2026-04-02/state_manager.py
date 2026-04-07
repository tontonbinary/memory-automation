"""
状态管理模块 - 管理 heartbeat 状态文件的读写和检查
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


class StateManager:
    """管理 heartbeat 状态，跟踪 session_key 和时间戳"""
    
    def __init__(self, state_file: str = "memory/heartbeat-state.json"):
        """
        初始化状态管理器
        
        Args:
            state_file: 状态文件路径（相对或绝对）
        """
        self.state_file = Path(state_file).expanduser()
        self._ensure_directory()
    
    def _ensure_directory(self):
        """确保状态文件所在目录存在"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
    
    def load_state(self) -> Dict[str, Any]:
        """
        加载状态文件
        
        Returns:
            状态字典，若文件不存在返回空结构
        """
        if not self.state_file.exists():
            return {
                "last_session_key": None,
                "last_processed_time": None,
                "last_processed_msg_id": None,
                "last_distilled_messages": 0,
                "pending_queue": [],
                "version": "2.0.0"
            }
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return self._empty_state()
                state = json.loads(content)
                # 兼容旧版本：如果没有新字段，添加默认值
                if "last_processed_msg_id" not in state:
                    state["last_processed_msg_id"] = None
                if "pending_queue" not in state:
                    state["pending_queue"] = []
                if "version" not in state:
                    state["version"] = "2.0.0"
                return state
        except (json.JSONDecodeError, IOError):
            return self._empty_state()
    
    def _empty_state(self) -> Dict[str, Any]:
        """返回空状态结构"""
        return {
            "last_session_key": None,
            "last_processed_time": None,
            "last_processed_msg_id": None,
            "last_distilled_messages": 0,
            "pending_queue": [],
            "version": "2.0.0"
        }
    
    def save_state(self, state: Dict[str, Any]) -> bool:
        """
        保存状态到文件
        
        Args:
            state: 要保存的状态字典
            
        Returns:
            是否保存成功
        """
        try:
            self._ensure_directory()
            # 添加更新时间
            state["updated_at"] = datetime.now().isoformat()
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            return True
        except IOError as e:
            print(f"[StateManager] 保存状态失败: {e}")
            return False
    
    def check_should_process(self, current_session_key: str, 
                            timeout_minutes: int = 30) -> tuple[bool, Optional[str]]:
        """
        检查是否需要处理会话
        
        Args:
            current_session_key: 当前 session_key
            timeout_minutes: 超时时间（分钟）
            
        Returns:
            (是否需要处理, 原因)
        """
        state = self.load_state()
        last_session = state.get("last_session_key")
        last_time_str = state.get("last_processed_time")
        
        # 情况1: session_key 变化
        if last_session != current_session_key:
            return True, f"session_key 变化: {last_session} -> {current_session_key}"
        
        # 情况2: 超时检查
        if last_time_str:
            try:
                last_time = datetime.fromisoformat(last_time_str)
                elapsed = (datetime.now() - last_time).total_seconds() / 60
                if elapsed >= timeout_minutes:
                    return True, f"超过 {timeout_minutes} 分钟未处理 (已过去 {int(elapsed)} 分钟)"
            except ValueError:
                # 时间格式错误，强制处理
                return True, "时间格式错误，强制处理"
        else:
            # 从未处理过
            return True, "首次处理"
        
        return False, None
    
    def update_after_process(self, session_key: str, 
                           message_count: int = 0,
                           last_msg_id: Optional[str] = None) -> bool:
        """
        处理完成后更新状态
        
        Args:
            session_key: 当前 session_key
            message_count: 本次处理的消息数
            last_msg_id: 最后处理的消息ID
            
        Returns:
            是否更新成功
        """
        state = self.load_state()
        state["last_session_key"] = session_key
        state["last_processed_time"] = datetime.now().isoformat()
        state["last_distilled_messages"] = message_count
        if last_msg_id:
            state["last_processed_msg_id"] = last_msg_id
        
        return self.save_state(state)
    
    def add_to_pending_queue(self, messages: list) -> bool:
        """
        将新消息添加到待处理队列
        
        Args:
            messages: 待处理的消息列表
            
        Returns:
            是否添加成功
        """
        state = self.load_state()
        if "pending_queue" not in state:
            state["pending_queue"] = []
        
        # 添加消息到队列（只保存必要字段，保留完整内容）
        for msg in messages:
            queue_item = {
                "role": msg.get("role", ""),
                "content": msg.get("content", ""),  # 保留完整内容，不截断
                "timestamp": msg.get("timestamp", ""),
                "msg_id": msg.get("msg_id", "")
            }
            state["pending_queue"].append(queue_item)
        
        # 限制队列大小，防止无限增长
        max_queue_size = 100
        if len(state["pending_queue"]) > max_queue_size:
            state["pending_queue"] = state["pending_queue"][-max_queue_size:]
        
        return self.save_state(state)
    
    def get_pending_queue(self) -> list:
        """
        获取待处理队列中的消息
        
        Returns:
            待处理消息列表
        """
        state = self.load_state()
        return state.get("pending_queue", [])
    
    def clear_pending_queue(self) -> bool:
        """
        清空待处理队列
        
        Returns:
            是否清空成功
        """
        state = self.load_state()
        state["pending_queue"] = []
        return self.save_state(state)
    
    def get_last_processed_msg_id(self) -> Optional[str]:
        """
        获取最后处理的消息ID
        
        Returns:
            最后处理的消息ID，如果没有则返回None
        """
        state = self.load_state()
        return state.get("last_processed_msg_id")
    
    def get_last_session_info(self) -> Dict[str, Any]:
        """
        获取上次处理的会话信息（用于 session 切换时的补救处理）
        
        Returns:
            包含 last_session_key 和 last_processed_msg_id 的字典
        """
        state = self.load_state()
        return {
            "last_session_key": state.get("last_session_key"),
            "last_processed_msg_id": state.get("last_processed_msg_id"),
            "last_processed_time": state.get("last_processed_time")
        }
    
    def mark_old_session_processing(self, old_session_key: str) -> bool:
        """
        标记开始处理某个旧 session，防止重复处理
        
        Args:
            old_session_key: 旧 session 的 key
            
        Returns:
            是否标记成功
        """
        state = self.load_state()
        state["processing_old_session_key"] = old_session_key
        state["processing_old_session_started_at"] = datetime.now().isoformat()
        return self.save_state(state)
    
    def is_old_session_processing(self, old_session_key: str) -> bool:
        """
        检查是否正在处理某个旧 session
        
        Args:
            old_session_key: 旧 session 的 key
            
        Returns:
            是否正在处理
        """
        state = self.load_state()
        processing_key = state.get("processing_old_session_key")
        if processing_key != old_session_key:
            return False
        # 检查是否处理超时（超过5分钟视为处理失败）
        started_at = state.get("processing_old_session_started_at")
        if started_at:
            try:
                start_time = datetime.fromisoformat(started_at)
                elapsed = (datetime.now() - start_time).total_seconds() / 60
                if elapsed > 5:
                    # 处理超时，清除标记
                    self.unmark_old_session_processing()
                    return False
            except ValueError:
                return False
        return True
    
    def unmark_old_session_processing(self) -> bool:
        """
        清除正在处理旧 session 的标记
        
        Returns:
            是否清除成功
        """
        state = self.load_state()
        state["processing_old_session_key"] = None
        state["processing_old_session_started_at"] = None
        return self.save_state(state)