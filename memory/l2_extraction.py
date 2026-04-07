#!/usr/bin/env python3
"""
L2 Extraction Script - 实时写入 corrections/patterns/insights 到 per-agent L2 存储

路径: ~/.openclaw/workspaces/{agent_id}/workspace/memory/L2/
文件: corrections.md | patterns.md | insights.md

用法:
    l2_extraction.py add_correction --agent mautoer --content "..." --source binary [--context "..."]
    l2_extraction.py add_pattern    --agent mautoer --content "..." --confidence N [--source "..."]
    l2_extraction.py add_insight   --agent mautoer --content "..." --importance high [--context "..."]
    l2_extraction.py process       --agent mautoer [--days 7]  # 今天不做
    l2_extraction.py list          --agent mautoer [--type corrections|patterns|insights]
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path


def get_l2_path(agent_id: str) -> Path:
    """动态解析 per-agent L2 目录"""
    base = Path.home() / ".openclaw" / "workspaces" / agent_id / "workspace" / "memory" / "L2"
    base.mkdir(parents=True, exist_ok=True)
    return base


def frontmatter_str(entries: dict) -> str:
    """生成 YAML frontmatter"""
    lines = ["---"]
    for k, v in entries.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---\n")
    return "\n".join(lines)


def append_entry(l2_path: Path, filename: str, content: str, metadata: dict):
    """追加条目到指定文件（带 frontmatter）"""
    filepath = l2_path / filename
    now = datetime.now()
    metadata["date"] = now.strftime("%Y-%m-%d")
    metadata["time"] = now.strftime("%H:%M")
    metadata["timestamp"] = now.isoformat()

    entry = frontmatter_str(metadata) + content + "\n"

    with open(filepath, "a", encoding="utf-8") as f:
        f.write(entry + "\n")

    print(f"[L2] 已写入 {filename}: {metadata.get('type', 'entry')}")
    return True


def cmd_add_correction(args):
    agent = args.agent
    content = args.content
    source = args.source
    context = args.context or ""

    l2 = get_l2_path(agent)
    metadata = {
        "source": source,
        "type": "correction",
        "status": "pending",
    }
    body = f"## 纠正内容\n\n{content}\n"
    if context:
        body += f"\n**上下文**: {context}\n"

    append_entry(l2, "corrections.md", body, metadata)


def cmd_add_pattern(args):
    agent = args.agent
    content = args.content
    confidence = args.confidence or 1
    source = args.source or "session"

    l2 = get_l2_path(agent)
    metadata = {
        "source": source,
        "type": "pattern",
        "confidence": confidence,
    }
    body = f"## 行为模式\n\n{content}\n"

    append_entry(l2, "patterns.md", body, metadata)


def cmd_add_insight(args):
    agent = args.agent
    content = args.content
    importance = args.importance or "medium"
    context = args.context or ""

    l2 = get_l2_path(agent)
    metadata = {
        "source": "agent",
        "type": "insight",
        "status": "new",
        "importance": importance,
    }
    body = f"## 洞察\n\n{content}\n"
    if context:
        body += f"\n**上下文**: {context}\n"

    append_entry(l2, "insights.md", body, metadata)


def cmd_list(args):
    """查看已有条目"""
    agent = args.agent
    l2 = get_l2_path(agent)

    filetype = args.type
    if filetype:
        files = [f"{filetype}.md"]
    else:
        files = ["corrections.md", "patterns.md", "insights.md"]

    for fname in files:
        path = l2 / fname
        if path.exists():
            print(f"\n=== {fname} ({path.stat().st_size} bytes) ===")
            print(path.read_text(encoding="utf-8")[:500])
        else:
            print(f"\n{fname}: (空)")


def main():
    parser = argparse.ArgumentParser(description="L2 Extraction CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # add_correction
    p_corr = sub.add_parser("add_correction", help="追加纠正条目")
    p_corr.add_argument("--agent", required=True, help="Agent ID")
    p_corr.add_argument("--content", required=True, help="纠正内容")
    p_corr.add_argument("--source", required=True, help="来源（如 binary/xiaoxian）")
    p_corr.add_argument("--context", help="上下文场景（可选）")

    # add_pattern
    p_pat = sub.add_parser("add_pattern", help="追加行为模式")
    p_pat.add_argument("--agent", required=True, help="Agent ID")
    p_pat.add_argument("--content", required=True, help="模式内容")
    p_pat.add_argument("--confidence", type=int, default=1, help="置信度/出现次数")
    p_pat.add_argument("--source", help="来源（可选）")

    # add_insight
    p_ins = sub.add_parser("add_insight", help="追加洞察")
    p_ins.add_argument("--agent", required=True, help="Agent ID")
    p_ins.add_argument("--content", required=True, help="洞察内容")
    p_ins.add_argument("--importance", default="medium",
                       choices=["low", "medium", "high", "critical"], help="重要程度")
    p_ins.add_argument("--context", help="上下文（可选）")

    # list
    p_list = sub.add_parser("list", help="查看已有条目")
    p_list.add_argument("--agent", required=True, help="Agent ID")
    p_list.add_argument("--type", choices=["corrections", "patterns", "insights"],
                        help="筛选类型（可选）")

    # process (stub, 今天不做)
    p_proc = sub.add_parser("process", help="定期处理：L1 检查（未实现）")
    p_proc.add_argument("--agent", required=True, help="Agent ID")
    p_proc.add_argument("--days", type=int, default=7, help="回溯天数")

    args = parser.parse_args()

    if args.cmd == "add_correction":
        cmd_add_correction(args)
    elif args.cmd == "add_pattern":
        cmd_add_pattern(args)
    elif args.cmd == "add_insight":
        cmd_add_insight(args)
    elif args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "process":
        print("[L2] process 今天不做，跳过")
        sys.exit(0)


if __name__ == "__main__":
    main()
