#!/usr/bin/env python3
"""
File Logger - 文件日志模块
为 memory-automation 提供 JSONL 格式的文件日志

用法:
    from .file_logger import FileLogger
    logger = FileLogger(agent_id)
    logger.log("heartbeat", "ok", "新消息: 3 条")
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


class FileLogger:
    """文件日志器 - 写入 JSONL 格式日志，保留最近 1000 行"""

    MAX_LINES = 1000

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.log_path = Path(f"~/.openclaw/agents/{agent_id}/memory-automation.log").expanduser()
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """确保日志目录存在"""
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"[FileLogger] ⚠️ 无法创建日志目录: {e}")

    def log(self, mode: str, status: str, detail: str = "") -> None:
        """
        写入一条日志记录

        Args:
            mode: 运行模式 (heartbeat/manual/setup/process-backlog/l2 等)
            status: 状态 (ok/error/warning/skipped 等)
            detail: 详细描述
        """
        entry = {
            "ts": datetime.now().astimezone().isoformat(),
            "mode": mode,
            "agent": self.agent_id,
            "status": status,
            "detail": detail,
        }

        try:
            # 追加写入
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            # 截断到最近 1000 行
            self._truncate_if_needed()

        except OSError as e:
            print(f"[FileLogger] ⚠️ 写入日志失败: {e}")

    def _truncate_if_needed(self) -> None:
        """如果日志超过 MAX_LINES 行，保留最近行"""
        try:
            if not self.log_path.exists():
                return

            # 快速检查行数（不读取全部内容到内存）
            line_count = 0
            with open(self.log_path, "r", encoding="utf-8") as f:
                for _ in f:
                    line_count += 1

            if line_count <= self.MAX_LINES:
                return

            # 读取所有行，保留最近 MAX_LINES 行
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            keep_lines = lines[-self.MAX_LINES:]

            with open(self.log_path, "w", encoding="utf-8") as f:
                f.writelines(keep_lines)

        except OSError as e:
            print(f"[FileLogger] ⚠️ 截断日志失败: {e}")

    def get_recent(self, n: int = 10) -> list:
        """
        读取最近 n 条日志

        Returns:
            最近 n 条日志记录列表（字典）
        """
        entries = []
        try:
            if not self.log_path.exists():
                return entries

            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for line in lines[-n:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

        except OSError as e:
            print(f"[FileLogger] ⚠️ 读取日志失败: {e}")

        return entries
