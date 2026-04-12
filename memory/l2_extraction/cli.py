#!/usr/bin/env python3
"""
L2 Extraction CLI
用法:
    python3 -m l2_extraction.cli add_correction --agent xiaoxian --topic "代码风格" --wrong "双引号" --correct "单引号"
    python3 -m l2_extraction.cli process --agent xiaoxian
    python3 -m l2_extraction.cli status --agent xiaoxian
"""

import argparse
import sys


def add_correction(args):
    from .corrections import add_correction
    success = add_correction(args.agent, args.topic, args.wrong, args.correct, args.source, args.context or "")
    print(f"Added correction for {args.agent}: {'success' if success else 'failed'}")
    return 0


def process(args):
    """定期处理：从 corrections 生成 patterns"""
    from .patterns import process_patterns_from_corrections
    
    result = process_patterns_from_corrections(args.agent, min_count=args.min_count, dry_run=args.dry_run)
    print(f"Processed {result.get('processed', 0)} corrections for {args.agent}")
    print(f"  Created: {result.get('created', 0)}, Updated: {result.get('updated', 0)}")
    return 0


def status(args):
    """查看 L2 状态"""
    from .corrections import get_corrections
    from .patterns import get_patterns
    from .insights_writer import get_insights
    
    corrections = get_corrections(args.agent)
    patterns = get_patterns(args.agent)
    insights = get_insights(args.agent)
    
    print(f"\nL2 Status for {args.agent}:")
    print(f"  corrections: {len(corrections)}")
    print(f"  patterns: {len(patterns)}")
    print(f"  insights: {len(insights)} (Agent 手动维护)")
    
    if args.verbose:
        if patterns:
            print(f"\n📌 Patterns:")
            for p in patterns[:5]:
                print(f"  - {p.get('key')}: {p.get('description')} (count={p.get('count', 0)})")
        
        if insights:
            verified = [i for i in insights if i.get('status') == 'verified']
            if verified:
                print(f"\n✨ Verified Insights:")
                for i in verified[:5]:
                    print(f"  - {i.get('title')}: {i.get('principle')}")
    
    return 0


def main():
    parser = argparse.ArgumentParser(description="L2 Extraction CLI")
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # add_correction
    p_add = subparsers.add_parser("add_correction", help="添加纠正记录")
    p_add.add_argument("--agent", required=True, help="agent 标识")
    p_add.add_argument("--topic", required=True, help="纠正主题")
    p_add.add_argument("--wrong", required=True, help="错误做法")
    p_add.add_argument("--correct", required=True, help="正确做法")
    p_add.add_argument("--source", default="self", help="来源 (binary/self)")
    p_add.add_argument("--context", default="", help="上下文")
    
    # process
    p_process = subparsers.add_parser("process", help="定期处理 corrections 生成 patterns")
    p_process.add_argument("--agent", required=True, help="agent 标识")
    p_process.add_argument("--min", type=int, default=3, dest="min_count", help="最小次数阈值")
    p_process.add_argument("--dry-run", action="store_true", help="模拟模式")
    
    # status
    p_status = subparsers.add_parser("status", help="查看 L2 状态")
    p_status.add_argument("--agent", required=True, help="agent 标识")
    p_status.add_argument("--verbose", action="store_true", help="详细信息")
    
    args = parser.parse_args()
    
    if args.command == "add_correction":
        return add_correction(args)
    elif args.command == "process":
        return process(args)
    elif args.command == "status":
        return status(args)
    else:
        parser.print_help()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
