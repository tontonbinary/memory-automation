"""
Processed Sessions Tracker - 追踪已处理和跳过的 session

功能：
1. 记录已处理的 session（避免重复处理）
2. 记录跳过的 session（记录原因）
3. 扫描目录找出未处理的 session
4. 智能筛选：基于时间、消息数等策略
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any


class ProcessedSessionsTracker:
    """追踪 session 处理状态"""
    
    def __init__(self, agent_id: str, config: Dict[str, Any]):
        self.agent_id = agent_id
        self.config = config
        self.tracker_file = self._get_tracker_file()
        self.data = self._load_tracker()
    
    def _get_tracker_file(self) -> Path:
        """获取 tracker 文件路径"""
        # 优先使用配置中的路径
        if self.config.get("processed_sessions_file"):
            return Path(self.config["processed_sessions_file"]).expanduser()
        
        # 默认路径
        base_dir = Path("~/.openclaw/skills/memory-automation").expanduser()
        return base_dir / f"processed-sessions-{self.agent_id}.json"
    
    def _load_tracker(self) -> Dict:
        """加载 tracker 数据"""
        if self.tracker_file.exists():
            try:
                with open(self.tracker_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        return {
            "version": "1.0",
            "agent_id": self.agent_id,
            "processed": {},
            "skipped": {},
            "last_scan_time": None
        }
    
    def _save_tracker(self) -> bool:
        """保存 tracker 数据"""
        try:
            self.tracker_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.tracker_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            return True
        except IOError as e:
            print(f"[ProcessedSessionsTracker] 保存失败: {e}")
            return False
    
    def mark_processed(self, session_key: str, session_file: Path, 
                       msg_count: int, saved_count: int) -> bool:
        """标记 session 为已处理"""
        self.data["processed"][session_key] = {
            "file": str(session_file),
            "processed_time": datetime.now().isoformat(),
            "msg_count": msg_count,
            "saved_count": saved_count
        }
        
        # 如果之前在 skipped 中，移除
        if session_key in self.data["skipped"]:
            del self.data["skipped"][session_key]
        
        return self._save_tracker()
    
    def mark_skipped(self, session_key: str, session_file: Path, 
                     reason: str, details: Optional[Dict] = None) -> bool:
        """标记 session 为跳过"""
        skip_info = {
            "file": str(session_file),
            "skipped_time": datetime.now().isoformat(),
            "reason": reason
        }
        if details:
            skip_info.update(details)
        
        self.data["skipped"][session_key] = skip_info
        return self._save_tracker()
    
    def is_processed(self, session_key: str) -> bool:
        """检查 session 是否已处理"""
        return session_key in self.data["processed"]
    
    def is_skipped(self, session_key: str) -> bool:
        """检查 session 是否被标记为跳过"""
        return session_key in self.data["skipped"]
    
    def get_unprocessed_sessions(self, sessions_dir: Path) -> List[Tuple[Path, Dict]]:
        """
        获取未处理的 session 文件列表
        
        Returns:
            [(session_file, file_info), ...]
            file_info: {"mtime": timestamp, "size": bytes, "line_count": int}
        """
        if not sessions_dir.exists():
            return []
        
        unprocessed = []
        
        for jsonl_file in sessions_dir.glob("*.jsonl"):
            # 从文件名提取 session_key（假设格式为 {session_id}.jsonl）
            session_id = jsonl_file.stem
            # 构建完整的 session_key（需要与 openclaw 格式一致）
            # 格式: agent:{agent_id}:{platform}:{chat_type}:{session_id}
            # 由于从文件名无法确定完整 key，我们用文件路径作为标识
            session_key = str(jsonl_file)
            
            # 跳过已处理和已标记跳过的
            if self.is_processed(session_key) or self.is_skipped(session_key):
                continue
            
            # 获取文件信息
            stat = jsonl_file.stat()
            file_info = {
                "mtime": stat.st_mtime,
                "size": stat.st_size,
                "line_count": self._count_lines(jsonl_file)
            }
            
            unprocessed.append((jsonl_file, file_info))
        
        # 更新扫描时间
        self.data["last_scan_time"] = datetime.now().isoformat()
        self._save_tracker()
        
        return unprocessed
    
    def _count_lines(self, file_path: Path) -> int:
        """计算文件行数"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return sum(1 for _ in f)
        except IOError:
            return 0
    
    def filter_sessions_by_policy(self, sessions: List[Tuple[Path, Dict]], 
                                   policy: Dict[str, Any]) -> List[Tuple[Path, Dict, str]]:
        """
        根据策略筛选 session
        
        Args:
            sessions: [(file, info), ...]
            policy: 策略配置
                - max_age_days: 最大天数
                - min_message_count: 最小消息数
                - process_order: 排序方式
        
        Returns:
            [(file, info, decision), ...]
            decision: "process" | "skip_too_old" | "skip_too_small" | "skip_other"
        """
        max_age_days = policy.get("max_age_days", 3)
        min_message_count = policy.get("min_message_count", 50)
        process_order = policy.get("process_order", "newest_first")
        
        now = datetime.now()
        cutoff_time = now - timedelta(days=max_age_days)
        
        results = []
        
        for file_path, file_info in sessions:
            mtime = datetime.fromtimestamp(file_info["mtime"])
            line_count = file_info["line_count"]
            
            # 检查时间
            if mtime < cutoff_time:
                results.append((file_path, file_info, "skip_too_old"))
                continue
            
            # 检查消息数
            if line_count < min_message_count:
                results.append((file_path, file_info, "skip_too_small"))
                continue
            
            results.append((file_path, file_info, "process"))
        
        # 排序
        if process_order == "newest_first":
            results.sort(key=lambda x: x[1]["mtime"], reverse=True)
        elif process_order == "largest_first":
            results.sort(key=lambda x: x[1]["line_count"], reverse=True)
        
        return results
    
    def get_next_session_to_process(self, sessions_dir: Path, 
                                    policy: Dict[str, Any]) -> Optional[Tuple[Path, Dict]]:
        """
        获取下一个应该处理的 session
        
        Returns:
            (session_file, file_info) 或 None
        """
        # 获取未处理的 session
        unprocessed = self.get_unprocessed_sessions(sessions_dir)
        
        if not unprocessed:
            return None
        
        # 应用策略筛选
        filtered = self.filter_sessions_by_policy(unprocessed, policy)
        
        # 找到第一个应该处理的
        for file_path, file_info, decision in filtered:
            session_key = str(file_path)
            
            if decision == "process":
                return (file_path, file_info)
            else:
                # 标记为跳过
                skip_reason = {
                    "skip_too_old": "文件太旧（超过最大天数）",
                    "skip_too_small": "消息太少（低于阈值）",
                    "skip_other": "其他原因"
                }.get(decision, "未知原因")
                
                self.mark_skipped(session_key, file_path, skip_reason, file_info)
        
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """获取处理统计"""
        return {
            "processed_count": len(self.data["processed"]),
            "skipped_count": len(self.data["skipped"]),
            "last_scan_time": self.data.get("last_scan_time")
        }
