"""
Insights Writer Module - Agent 手动维护的 insights 写入层

insights.md 不再由代码自动生成，改由 Agent 主动调用 LLM 从 patterns 提炼后写入。
本模块仅提供基础读写接口。
"""

import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


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
    添加新的洞察到 insights.md（由 Agent 手动调用）
    
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

Agent 手动维护 - 从 patterns 中提炼出的原则/洞察
由 Agent 主动调用 LLM 从 L2 patterns 提炼后写入

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
