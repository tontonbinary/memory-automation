"""
Corrections Module -底层原始记录
被纠正的内容、场景、时间戳
"""

import os
from datetime import datetime
from pathlib import Path


def get_l2_dir(agent_id: str) -> Path:
    return Path(os.path.expanduser(f"~/.openclaw/workspaces/{agent_id}/workspace/memory/L2"))


def get_corrections_file(agent_id: str) -> Path:
    return get_l2_dir(agent_id) / "corrections.md"


def ensure_l2_dir(agent_id: str):
    """确保 L2 目录存在"""
    l2_dir = get_l2_dir(agent_id)
    l2_dir.mkdir(parents=True, exist_ok=True)
    return l2_dir


def add_correction(agent_id: str, content: str, source: str = "self", context: str = ""):
    """
    添加纠正记录到 corrections.md
    
    Args:
        agent_id: agent 标识
        content: 被纠正的具体内容
        source: 来源 (binary/self)
        context: 场景上下文（可选）
    """
    ensure_l2_dir(agent_id)
    corrections_file = get_corrections_file(agent_id)
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    entry = f"""## {timestamp}

**来源**: {source}
**内容**: {content}
**上下文**: {context if context else "无"}

---
"""
    
    if corrections_file.exists():
        existing = corrections_file.read_text()
        if "## " in existing and "---" in existing:
            # 已有内容，追加新条目
            new_content = existing.replace("\n---\n", "\n") + entry
        else:
            new_content = entry
    else:
        header = """# Corrections

底层原始记录 - 被纠正的内容、场景、时间戳

"""
        new_content = header + entry
    
    corrections_file.write_text(new_content)
    return True


def get_corrections(agent_id: str, limit: int = 50) -> list:
    """
    获取最近的纠正记录
    
    Returns:
        list of dict with keys: timestamp, source, content, context
    """
    corrections_file = get_corrections_file(agent_id)
    if not corrections_file.exists():
        return []
    
    content = corrections_file.read_text()
    # 简单解析 - 按 --- 分隔
    entries = content.split("---")
    results = []
    
    for entry in entries[-limit:]:
        if "**来源**:" in entry:
            lines = entry.strip().split("\n")
            item = {"timestamp": "", "source": "", "content": "", "context": ""}
            for line in lines:
                if line.startswith("## "):
                    item["timestamp"] = line.replace("## ", "").strip()
                elif "**来源**:" in line:
                    item["source"] = line.split("**来源**:")[1].strip()
                elif "**内容**:" in line:
                    item["content"] = line.split("**内容**:")[1].strip()
                elif "**上下文**:" in line:
                    item["context"] = line.split("**上下文**:")[1].strip()
            if item["content"]:
                results.append(item)
    
    return results


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "add":
        # CLI: python -m l2_extraction.corrections add --agent xiaoxian --content "xxx" --source binary
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--agent", required=True)
        parser.add_argument("--content", required=True)
        parser.add_argument("--source", default="self")
        parser.add_argument("--context", default="")
        args = parser.parse_args()
        add_correction(args.agent, args.content, args.source, args.context)
        print(f"Added correction for {args.agent}")
