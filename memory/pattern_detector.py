#!/usr/bin/env python3
"""
Pattern Detector - 模式检测模块
检测用户偏好和行为模式
"""

import re
import subprocess
from datetime import timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional


class PatternDetector:
    """模式检测器"""

    def __init__(self, agent_id: str, config: Dict[str, Any]):
        self.agent_id = agent_id
        self.config = config

    def _get_l1_history_files(self) -> List[Path]:
        """
        获取 L1 历史文件列表

        Returns:
            历史文件路径列表（按日期排序）
        """
        from datetime import datetime

        days = self.config.get("l1_history_days", 7)
        history_files = []

        # 构建 L1 目录路径
        template = self.config.get("l1_template",
            "~/.openclaw/workspaces/{agent}/workspace/memory/{date}.md")

        # 获取最近 N 天的文件
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            path_str = template.format(agent=self.agent_id, date=date_str)
            path = Path(path_str).expanduser()
            if path.exists():
                history_files.append(path)

        return history_files

    def _extract_keywords_from_message(self, user_message: str) -> List[str]:
        """
        从用户消息中提取关键内容

        提取规则：去除停用词，保留实词（名词、动词、形容词）

        Args:
            user_message: 用户消息

        Returns:
            关键词列表
        """
        # 去除触发关键词本身
        pattern_keywords = self.config.get("pattern_keywords",
            ["我喜欢", "我决定", "我偏好", "我想要", "以后都用"])

        cleaned = user_message
        for kw in pattern_keywords:
            cleaned = cleaned.replace(kw, "")

        # 去除标点和多余空格
        cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # 简单分词：按空格分割，取长度 >=2 的词
        words = [w.strip() for w in cleaned.split() if len(w.strip()) >= 2]

        return words

    def detect_pattern_realtime(self, user_message: str) -> Optional[Dict[str, Any]]:
        """
        实时检测用户偏好/行为模式

        当用户表达偏好时，搜索 L1 历史中是否已有相同标签 ≥3 次

        Args:
            user_message: 用户消息

        Returns:
            检测结果字典，无模式时返回 None
            {
                "tag": str,  # 检测到的标签
                "count": int,  # 历史出现次数
                "suggestion": str  # 建议信息
            }
        """
        # 1. 检查是否触发模式检测
        pattern_keywords = self.config.get("pattern_keywords",
            ["我喜欢", "我决定", "我偏好", "我想要", "以后都用"])

        message_lower = user_message.lower()
        if not any(kw.lower() in message_lower for kw in pattern_keywords):
            return None

        # 2. 提取关键词
        keywords = self._extract_keywords_from_message(user_message)
        if not keywords:
            return None

        # 3. Grep 搜索 L1 历史文件
        history_files = self._get_l1_history_files()
        if not history_files:
            return None

        # 统计每个关键词的出现次数
        tag_counts = {}

        for kw in keywords:
            count = 0
            for l1_file in history_files:
                try:
                    # 使用 grep 搜索（-i 不区分大小写，-w 匹配完整单词）
                    result = subprocess.run(
                        ["grep", "-i", "-w", "-c", kw, str(l1_file)],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode == 0:
                        # grep -c 返回匹配行数
                        file_count = int(result.stdout.strip() or "0")
                        count += file_count
                except (subprocess.TimeoutExpired, ValueError, Exception):
                    continue

            if count > 0:
                tag_counts[kw] = count

        if not tag_counts:
            return None

        # 4. 找到出现次数最多的标签
        threshold = self.config.get("pattern_threshold", 3)
        max_tag = max(tag_counts.items(), key=lambda x: x[1])

        if max_tag[1] >= threshold:
            return {
                "tag": max_tag[0],
                "count": max_tag[1],
                "suggestion": f"历史出现 {max_tag[1]} 次，要提升为 L2 吗？"
            }

        return None
