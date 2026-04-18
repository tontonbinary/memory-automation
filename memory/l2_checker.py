#!/usr/bin/env python3
"""
L2 Checker - L2 自我改进层检查模块

功能：
1. 检查遗漏的纠正（用户说了纠正关键词但没记录到 corrections）
2. 检查 L2 状态（corrections/patterns/insights 数量，是否达到处理阈值）
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


# 纠正关键词列表（来自 SKILL.md）
CORRECTION_KEYWORDS = [
    # 直接纠正
    "改", "改正", "修改", "调整", "更正",
    "不对", "错了", "错误", "有误",
    # 未来纠正
    "下次", "以后", "往后", "将来",
    "记得", "别忘了", "注意", "要",
    # 否定纠正
    "不要", "别", "不需要", "不用",
    # 强调纠正
    "必须", "一定", "务必", "千万",
]


class L2Checker:
    """L2 状态检查器"""
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.workspace_dir = Path(f"~/.openclaw/workspaces/{agent_id}/workspace").expanduser()
        self.l2_dir = self.workspace_dir / "memory" / "L2"
        self.clean_session_dir = Path(f"~/.openclaw/agents/{agent_id}/clean_session").expanduser()
        
        # 阈值配置
        self.process_threshold = 5  # corrections 达到 5 条建议 process
        self.insights_threshold = 3  # 高置信度 patterns 达到 3 条建议提炼 insights
        self.high_confidence_threshold = 7  # 高置信度阈值
    
    def _get_today_clean_session(self) -> Optional[Path]:
        """获取今天的 clean session 文件"""
        today = datetime.now().strftime("%m%d")
        # 查找今天生成的 clean session 文件（可能有多个块）
        pattern = f"{today}#L*.json"
        files = sorted(self.clean_session_dir.glob(pattern))
        return files[-1] if files else None
    
    def _load_clean_session_messages(self, clean_path: Path) -> List[Dict]:
        """加载 clean session 中的用户消息"""
        try:
            with open(clean_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # clean session 格式: [{"r": "u", "s": "", "t": "...", "c": "..."}, ...]
                return data if isinstance(data, list) else []
        except Exception:
            return []
    
    def _contains_correction_keywords(self, content: str) -> Tuple[bool, List[str]]:
        """检查内容是否包含纠正关键词"""
        content_lower = content.lower()
        matched = [kw for kw in CORRECTION_KEYWORDS if kw.lower() in content_lower]
        return bool(matched), matched
    
    def _load_recent_corrections(self, lookback_hours: int = 6) -> List[Dict]:
        """加载最近 N 小时的 corrections"""
        corrections_path = self.l2_dir / "corrections.jsonl"
        if not corrections_path.exists():
            return []
        
        cutoff_time = datetime.now() - timedelta(hours=lookback_hours)
        recent = []
        
        try:
            with open(corrections_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        corr = json.loads(line)
                        # 检查时间戳
                        ts = corr.get("timestamp", "")
                        if ts:
                            try:
                                corr_time = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                                if corr_time >= cutoff_time:
                                    recent.append(corr)
                            except:
                                # 无法解析时间戳，假设是最近的
                                recent.append(corr)
                        else:
                            recent.append(corr)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        
        return recent
    
    def _load_patterns(self) -> List[Dict]:
        """加载 patterns.md 内容"""
        patterns_path = self.l2_dir / "patterns.md"
        if not patterns_path.exists():
            return []
        
        try:
            content = patterns_path.read_text(encoding='utf-8')
            # 简单解析：统计 ### 开头的 pattern 数量
            patterns = []
            for line in content.split('\n'):
                if line.strip().startswith('### '):
                    # 提取置信度
                    confidence_match = re.search(r'置信度[:\s]*(\d+)', line)
                    confidence = int(confidence_match.group(1)) if confidence_match else 0
                    patterns.append({"confidence": confidence})
            return patterns
        except Exception:
            return []
    
    def check_missed_corrections(self) -> List[Dict]:
        """
        检查遗漏的纠正
        
        Returns:
            可能遗漏的纠正消息列表
        """
        # 获取今天的 clean session
        clean_path = self._get_today_clean_session()
        if not clean_path:
            return []
        
        # 加载用户消息
        messages = self._load_clean_session_messages(clean_path)
        user_msgs = [m for m in messages if m.get("r") == "u"]  # role = user
        
        # 加载最近的 corrections
        recent_corrections = self._load_recent_corrections(lookback_hours=6)
        
        # 检查每条用户消息
        missed = []
        for msg in user_msgs:
            content = msg.get("c", "")
            has_keywords, keywords = self._contains_correction_keywords(content)
            
            if not has_keywords:
                continue
            
            # 简单去重：检查这条消息的时间戳附近是否有 correction
            msg_time = msg.get("t", "")
            is_recorded = False
            
            for corr in recent_corrections:
                corr_time = corr.get("timestamp", "")
                # 如果时间接近（简化判断：都有时间戳就认为可能已记录）
                if msg_time and corr_time:
                    # 更精确的时间匹配可以在这里实现
                    is_recorded = True
                    break
            
            if not is_recorded:
                missed.append({
                    "content": content[:100] + "..." if len(content) > 100 else content,
                    "keywords": keywords,
                    "timestamp": msg_time
                })
        
        return missed
    
    def check_l2_status(self) -> Dict[str, Any]:
        """
        检查 L2 整体状态
        
        Returns:
            {
                "corrections_count": int,
                "patterns_count": int,
                "high_confidence_patterns": int,
                "should_process": bool,  # 是否需要执行 l2 process
                "should_extract_insights": bool,  # 是否需要提炼 insights
                "suggestions": List[str]
            }
        """
        result = {
            "corrections_count": 0,
            "patterns_count": 0,
            "high_confidence_patterns": 0,
            "should_process": False,
            "should_extract_insights": False,
            "suggestions": []
        }
        
        # 统计 corrections
        corrections = self._load_recent_corrections(lookback_hours=999999)  # 加载所有
        result["corrections_count"] = len(corrections)
        
        # 统计 patterns
        patterns = self._load_patterns()
        result["patterns_count"] = len(patterns)
        result["high_confidence_patterns"] = sum(
            1 for p in patterns if p.get("confidence", 0) >= self.high_confidence_threshold
        )
        
        # 判断是否需要 process
        if result["corrections_count"] >= self.process_threshold:
            result["should_process"] = True
            result["suggestions"].append(
                f"corrections 已达 {result['corrections_count']} 条，建议执行: l2 process --agent {self.agent_id}"
            )
        
        # 判断是否需要提炼 insights
        if result["high_confidence_patterns"] >= self.insights_threshold:
            result["should_extract_insights"] = True
            result["suggestions"].append(
                f"高置信度 patterns 已达 {result['high_confidence_patterns']} 条，建议提炼 insights"
            )
        
        return result
    
    def generate_reminder_report(self) -> str:
        """生成完整的 L2 提醒报告"""
        lines = []
        
        # 1. 检查遗漏的纠正
        missed = self.check_missed_corrections()
        if missed:
            lines.append("\n⚠️ 【可能遗漏的纠正】")
            lines.append(f"   发现 {len(missed)} 条含纠正关键词但未记录的消息：")
            for i, msg in enumerate(missed[:3], 1):  # 最多显示3条
                lines.append(f"   {i}. \"{msg['content'][:50]}...\"")
                lines.append(f"      关键词: {', '.join(msg['keywords'][:3])}")
            if len(missed) > 3:
                lines.append(f"   ... 还有 {len(missed) - 3} 条")
            lines.append(f"\n   如需记录: l2 correct --agent {self.agent_id} --topic <主题> --wrong <错误> --correct <正确>")
        
        # 2. 检查 L2 状态
        status = self.check_l2_status()
        if status["suggestions"]:
            lines.append("\n📊 【L2 状态提醒】")
            lines.append(f"   corrections: {status['corrections_count']} 条")
            lines.append(f"   patterns: {status['patterns_count']} 条 (高置信度: {status['high_confidence_patterns']})")
            lines.append("\n   建议操作：")
            for suggestion in status["suggestions"]:
                lines.append(f"   • {suggestion}")
        
        if not lines:
            return ""
        
        return "\n".join(lines)


def main():
    """测试入口"""
    import sys
    
    agent_id = sys.argv[1] if len(sys.argv) > 1 else "mautoer"
    checker = L2Checker(agent_id)
    
    print(f"=== L2 检查报告 ({agent_id}) ===")
    print(checker.generate_reminder_report())


if __name__ == "__main__":
    main()
