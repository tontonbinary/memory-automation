"""
Insights Module - 顶层提炼
从 patterns 中提炼出原则/洞察
有 status 状态：pending -> verified -> abandoned
"""

import os
from pathlib import Path
from datetime import datetime


def get_l2_dir(agent_id: str) -> Path:
    return Path(os.path.expanduser(f"~/.openclaw/workspaces/{agent_id}/workspace/memory/L2"))


def get_insights_file(agent_id: str) -> Path:
    return get_l2_dir(agent_id) / "insights.md"


def ensure_l2_dir(agent_id: str):
    l2_dir = get_l2_dir(agent_id)
    l2_dir.mkdir(parents=True, exist_ok=True)
    return l2_dir


def add_insight(agent_id: str, title: str, principle: str, status: str = "pending", related_patterns: list = None):
    """
    添加新的洞察
    
    Args:
        agent_id: agent 标识
        title: 洞察标题
        principle: 原则/洞察内容
        status: pending | verified | abandoned
        related_patterns: 关联的 patterns
    """
    ensure_l2_dir(agent_id)
    insights_file = get_insights_file(agent_id)
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    if not insights_file.exists():
        header = """# Insights

顶层提炼 - 从 patterns 中提炼出的原则/洞察
状态：pending -> verified -> abandoned

"""
        insights_file.write_text(header)
    
    existing = insights_file.read_text() if insights_file.exists() else ""
    
    related_str = ""
    if related_patterns:
        for p in related_patterns:
            related_str += f"- {p}\n"
    
    new_insight = f"""## {title}

**Principle**: {principle}
**Status**: {status}
**Created**: {timestamp}
**Updated**: {timestamp}

**Related Patterns**:
{(related_str if related_str else "- (暂无关联)") + chr(10)}
"""
    
    insights_file.write_text(existing + new_insight)
    return True


def update_insight_status(agent_id: str, title: str, new_status: str):
    """
    更新洞察状态
    
    Args:
        agent_id: agent 标识
        title: 洞察标题
        new_status: pending | verified | abandoned
    """
    insights_file = get_insights_file(agent_id)
    if not insights_file.exists():
        return False
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    existing = insights_file.read_text()
    
    lines = existing.split("\n")
    new_lines = []
    in_target = False
    
    for line in lines:
        if f"## {title}" == line:
            new_lines.append(line)
            in_target = True
        elif in_target and line.startswith("**Status**:") and new_status:
            new_lines.append(f"**Status**: {new_status}")
        elif in_target and line.startswith("**Updated**:") and new_status:
            new_lines.append(f"**Updated**: {timestamp}")
        elif in_target and line.startswith("## "):
            in_target = False
            new_lines.append(line)
        else:
            new_lines.append(line)
    
    insights_file.write_text("\n".join(new_lines))
    return True


def get_insights(agent_id: str, status: str = None) -> list:
    """
    获取洞察列表
    
    Args:
        agent_id: agent 标识
        status: 可选过滤状态
    """
    insights_file = get_insights_file(agent_id)
    if not insights_file.exists():
        return []
    
    content = insights_file.read_text()
    results = []
    current = {}
    
    for line in content.split("\n"):
        if line.startswith("## "):
            if current:
                results.append(current)
            current = {"title": line.replace("## ", "").strip()}
        elif "**Principle**:" in line:
            current["principle"] = line.split("**Principle**:")[1].strip()
        elif "**Status**:" in line:
            current["status"] = line.split("**Status**:")[1].strip()
        elif "**Created**:" in line:
            current["created"] = line.split("**Created**:")[1].strip()
        elif "**Updated**:" in line:
            current["updated"] = line.split("**Updated**:")[1].strip()
    
    if current:
        results.append(current)
    
    if status:
        results = [r for r in results if r.get("status") == status]
    
    return results


def promote_to_verified(agent_id: str, title: str):
    """将洞察升级为 verified 状态"""
    return update_insight_status(agent_id, title, "verified")
