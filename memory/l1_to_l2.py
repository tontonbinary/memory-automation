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
    DEFAULT_MIN_OCCURRENCES = 3  # 最少出现3次
    
    def __init__(self, 
                 agent_id: str = "code",
                 l1_path: Optional[str] = None,
                 l2_path: Optional[str] = None,
                 state_file: Optional[str] = None):
        """
        初始化 L1→L2 提升器
        
        Args:
            agent_id: Agent ID
            l1_path: L1 路径
            l2_path: L2 路径
            state_file: 状态文件路径
        """
        self.agent_id = agent_id
        self.state_file = Path(state_file or self.DEFAULT_STATE_FILE).expanduser()
        
        # 初始化组件
        self.analyzer = TagAnalyzer(agent_id=agent_id, l1_path=l1_path)
        self.writer = L2Writer(l2_path=l2_path)
        
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
            "last_check": None,
            "version": "1.0.0"
        }
    
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
        检查并提升标签
        
        Args:
            days_back: 回溯天数，默认使用 DEFAULT_DAYS_BACK
            min_occurrences: 最小出现次数，默认使用 DEFAULT_MIN_OCCURRENCES
            dry_run: 是否仅模拟，不实际写入
            
        Returns:
            执行结果报告
        """
        days_back = days_back or self.DEFAULT_DAYS_BACK
        min_occurrences = min_occurrences or self.DEFAULT_MIN_OCCURRENCES
        
        print(f"\n{'='*60}")
        print(f"[L1→L2] 开始检查")
        print(f"  时间范围: 最近 {days_back} 天")
        print(f"  最小次数: {min_occurrences} 次")
        print(f"  模拟模式: {dry_run}")
        print(f"{'='*60}\n")
        
        # 1. 分析标签
        qualified_tags = self.analyzer.analyze_tags(days_back, min_occurrences)
        
        if not qualified_tags:
            print("[L1→L2] 未发现符合条件的标签")
            return {
                "checked": True,
                "promoted": [],
                "skipped": [],
                "reason": "no_qualified_tags"
            }
        
        # 2. 获取已提升的标签
        promoted_tags = self.get_promoted_tags()
        
        # 3. 筛选未提升的标签
        new_tags = {}
        skipped_tags = []
        
        for tag_name, stats in qualified_tags.items():
            if tag_name in promoted_tags:
                print(f"[L1→L2] 跳过已提升标签: #{tag_name}")
                skipped_tags.append(tag_name)
            else:
                new_tags[tag_name] = stats
        
        # 4. 写入 L2
        promoted = []
        if new_tags:
            if dry_run:
                print(f"\n[L1→L2] 【模拟模式】将提升以下标签:")
                for tag_name in new_tags:
                    print(f"  - #{tag_name}")
                promoted = list(new_tags.keys())
            else:
                print(f"\n[L1→L2] 正在写入 L2...")
                for tag_name, stats in new_tags.items():
                    if self.writer.append_tag(tag_name, stats):
                        self.add_promoted_tag(tag_name)
                        promoted.append(tag_name)
        
        # 5. 保存状态
        if not dry_run:
            self._save_state()
        
        # 6. 生成报告
        result = {
            "checked": True,
            "qualified_count": len(qualified_tags),
            "promoted": promoted,
            "skipped": skipped_tags,
            "dry_run": dry_run
        }
        
        print(f"\n{'='*60}")
        print(f"[L1→L2] 检查完成")
        print(f"  符合条件: {len(qualified_tags)} 个标签")
        print(f"  本次提升: {len(promoted)} 个")
        print(f"  跳过(已存在): {len(skipped_tags)} 个")
        print(f"{'='*60}\n")
        
        return result


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="L1→L2 自动提升工具")
    parser.add_argument("--agent", default="code", help="Agent ID (默认: code)")
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
