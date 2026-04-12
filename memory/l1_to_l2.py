"""
L1→L2 主逻辑模块 - 自动将符合条件的标签从 L1 提升到 L2

使用方法：
    python -m memory.l1_to_l2  # 手动执行
    
触发方式：
    1. 定时：每周通过 cron 或 heartbeat 执行
    2. 手动：直接运行此模块
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from .tag_analyzer import TagAnalyzer
from .l2_writer import L2Writer


class L1ToL2Promoter:
    """L1 到 L2 的自动提升器"""
    
    # 状态文件路径
    DEFAULT_STATE_FILE = "memory/l2-state.json"
    
    # 配置
    DEFAULT_DAYS_BACK = 7  # 检查最近7天
    DEFAULT_MIN_OCCURRENCES = 3  # 已废弃，保留兼容
    
    def __init__(self, 
                 agent_id: str,
                 l1_path: Optional[str] = None,
                 l2_path: Optional[str] = None,
                 state_file: Optional[str] = None):
        """
        初始化 L1→L2 提升器
        
        Args:
            agent_id: Agent ID（必需）
            l1_path: L1 路径
            l2_path: L2 路径（可选，默认使用 agent_id 隔离的路径）
            state_file: 状态文件路径
        
        Raises:
            ValueError: 如果 agent_id 为空
        """
        if not agent_id:
            raise ValueError("agent_id 是必需的，不能为空")
        
        self.agent_id = agent_id
        self.state_file = Path(state_file or self.DEFAULT_STATE_FILE).expanduser()
        
        # 初始化组件（确保按 agent 隔离）
        self.analyzer = TagAnalyzer(agent_id=agent_id, l1_path=l1_path)
        self.writer = L2Writer(agent_id=agent_id, l2_path=l2_path)
        
        # 加载状态
        self.state = self._load_state()
    
    def _load_state(self) -> Dict:
        """加载状态文件"""
        if not self.state_file.exists():
            return {
                "promoted_tags": [],
                "last_check": None,
                "version": "1.0.0"
            }
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return self._empty_state()
                return json.loads(content)
        except (json.JSONDecodeError, IOError):
            return self._empty_state()
    
    def _empty_state(self) -> Dict:
        """返回空状态"""
        return {
            "promoted_tags": [],
            "processed_selfevolve": [],
            "last_check": None,
            "version": "2.0.0"
        }
    
    def _is_selfevolve_processed(self, entry_id: str) -> bool:
        """检查 SelfEvolve 条目是否已处理"""
        return entry_id in self.state.get("processed_selfevolve", [])
    
    def _mark_selfevolve_processed(self, entry_id: str) -> None:
        """标记 SelfEvolve 条目为已处理"""
        processed = self.state.get("processed_selfevolve", [])
        if entry_id not in processed:
            processed.append(entry_id)
            self.state["processed_selfevolve"] = processed
    
    def _save_state(self) -> bool:
        """保存状态文件"""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state["last_check"] = datetime.now().strftime("%Y-%m-%d")
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
            return True
        except IOError as e:
            print(f"[L1ToL2] 保存状态失败: {e}")
            return False
    
    def get_promoted_tags(self) -> Set[str]:
        """获取已提升的标签集合"""
        return set(self.state.get("promoted_tags", []))
    
    def add_promoted_tag(self, tag_name: str) -> None:
        """添加已提升的标签"""
        promoted = self.state.get("promoted_tags", [])
        if tag_name not in promoted:
            promoted.append(tag_name)
            self.state["promoted_tags"] = promoted
    
    def check_and_promote(self, 
                         days_back: int = None, 
                         min_occurrences: int = None,
                         dry_run: bool = False) -> Dict:
        """
        检查并提取 SelfEvolve 条目到 corrections.jsonl
        
        逻辑变更 (v2.0):
        - 不再统计标签频次，而是直接提取 event_type == SelfEvolve 的条目
        - 每个 SelfEvolve 条目映射为 correction 格式写入 corrections.jsonl
        - 通过 processed_selfevolve 去重，避免重复写入
        
        Args:
            days_back: 回溯天数，默认使用 DEFAULT_DAYS_BACK
            min_occurrences: 已废弃，保留参数兼容
            dry_run: 是否仅模拟，不实际写入
            
        Returns:
            执行结果报告
        """
        days_back = days_back or self.DEFAULT_DAYS_BACK
        
        print(f"\n{'='*60}")
        print(f"[L1→L2] 开始提取 SelfEvolve 条目到 corrections")
        print(f"  时间范围: 最近 {days_back} 天")
        print(f"  筛选条件: event_type == SelfEvolve (即 item_type == improvement)")
        print(f"  模拟模式: {dry_run}")
        print(f"{'='*60}\n")
        
        # 1. 提取 SelfEvolve 条目
        entries = self.analyzer.analyze_selfevolve_entries(days_back)
        
        if not entries:
            print("[L1→L2] 未发现 SelfEvolve 条目")
            return {
                "checked": True,
                "promoted": [],
                "skipped": [],
                "reason": "no_selfevolve_entries"
            }
        
        # 2. 写入 L2 corrections
        promoted = []
        skipped = []
        
        for entry in entries:
            # 生成唯一标识用于去重
            entry_id = f"{entry['date']}|{entry['time']}|{entry['content'][:60]}"
            
            if self._is_selfevolve_processed(entry_id):
                print(f"[L1→L2] 跳过已处理条目: {entry['date']} {entry['time']}")
                skipped.append(entry_id)
                continue
            
            # 映射到 correction 格式
            topic = entry["tags"][0] if entry["tags"] else "self-evolve"
            # 如果 L1 条目的 improve 字段有值，用它作为 wrong；否则用占位符
            wrong = entry["improve"] if entry["improve"] else f"[SelfEvolve@{entry['date']} {entry['time']}]"
            correct = entry["content"]
            context_parts = [
                f"日期: {entry['date']} {entry['time']}",
            ]
            if entry["tags"]:
                context_parts.append(f"标签: {' '.join('#'+t for t in entry['tags'])}")
            if entry["source"]:
                context_parts.append(f"来源: {entry['source']}")
            if entry["action"]:
                context_parts.append(f"后续行动: {entry['action']}")
            context = ", ".join(context_parts)
            
            if dry_run:
                print(f"[L1→L2] 【模拟】将写入 correction:")
                print(f"  topic={topic}")
                print(f"  wrong={wrong[:50]}...")
                print(f"  correct={correct[:50]}...")
                promoted.append(entry_id)
            else:
                success = self.writer.add_correction(
                    topic=topic,
                    wrong=wrong,
                    correct=correct,
                    source="l1_selfevolve",
                    context=context
                )
                if success:
                    self._mark_selfevolve_processed(entry_id)
                    promoted.append(entry_id)
                    print(f"[L1→L2] 已写入 correction: [{topic}] {correct[:40]}...")
                else:
                    print(f"[L1→L2] 写入失败: [{topic}]")
        
        # 3. 保存状态
        if not dry_run:
            self._save_state()
        
        # 4. 生成报告
        result = {
            "checked": True,
            "total_entries": len(entries),
            "promoted": promoted,
            "skipped": skipped,
            "dry_run": dry_run
        }
        
        print(f"\n{'='*60}")
        print(f"[L1→L2] 提取完成")
        print(f"  发现条目: {len(entries)} 条")
        print(f"  本次写入: {len(promoted)} 条")
        print(f"  跳过(已处理): {len(skipped)} 条")
        print(f"{'='*60}\n")
        
        return result


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="L1→L2 自动提升工具")
    parser.add_argument("--agent", required=True, help="Agent ID (必需)")
    parser.add_argument("--days", type=int, default=7, help="回溯天数 (默认: 7)")
    parser.add_argument("--min", type=int, default=3, dest="min_occurrences",
                       help="最小出现次数 (默认: 3)")
    parser.add_argument("--dry-run", action="store_true", help="模拟模式，不实际写入")
    parser.add_argument("--l1-path", help="自定义 L1 路径")
    parser.add_argument("--l2-path", help="自定义 L2 路径")
    parser.add_argument("--state-file", help="自定义状态文件路径")
    
    args = parser.parse_args()
    
    # 创建提升器
    promoter = L1ToL2Promoter(
        agent_id=args.agent,
        l1_path=args.l1_path,
        l2_path=args.l2_path,
        state_file=args.state_file
    )
    
    # 执行检查
    result = promoter.check_and_promote(
        days_back=args.days,
        min_occurrences=args.min_occurrences,
        dry_run=args.dry_run
    )
    
    # 返回状态码
    return 0 if result["checked"] else 1


if __name__ == "__main__":
    exit(main())
