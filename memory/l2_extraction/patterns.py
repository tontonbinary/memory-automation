"""
Patterns Module - 中层聚合
从多次 corrections 中发现重复模式
关联 confidence 置信度（count 次数）
"""

import os
from pathlib import Path
from datetime import datetime


def get_l2_dir(agent_id: str) -> Path:
    return Path(os.path.expanduser(f"~/.openclaw/workspaces/{agent_id}/workspace/memory/L2"))


def get_patterns_file(agent_id: str) -> Path:
    return get_l2_dir(agent_id) / "patterns.md"


def ensure_l2_dir(agent_id: str):
    l2_dir = get_l2_dir(agent_id)
    l2_dir.mkdir(parents=True, exist_ok=True)
    return l2_dir


def add_or_update_pattern(agent_id: str, pattern_key: str, description: str, examples: list = None):
    """
    添加或更新 pattern
    
    Args:
        agent_id: agent 标识
        pattern_key: 模式标识（如 "discussion-order"）
        description: 模式描述
        examples: 示例列表
    """
    ensure_l2_dir(agent_id)
    patterns_file = get_patterns_file(agent_id)
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    if not patterns_file.exists():
        header = """# Patterns

中层聚合 - 从 corrections 中发现的重复模式

"""
        patterns_file.write_text(header)
    
    existing = patterns_file.read_text() if patterns_file.exists() else ""
    
    # 检查是否已存在该 pattern
    if f"## {pattern_key}" in existing:
        # 更新现有 pattern，增加 count
        lines = existing.split("\n")
        new_lines = []
        in_target = False
        count_updated = False
        
        for line in lines:
            if f"## {pattern_key}" == line:
                new_lines.append(line)
                in_target = True
            elif in_target and line.startswith("**Count**:") and not count_updated:
                count_str = line.split("**Count**:")[1].strip()
                try:
                    count = int(count_str) + 1
                except:
                    count = 2
                new_lines.append(f"**Count**: {count}")
                count_updated = True
            elif in_target and line.startswith("**Updated**:") and not count_updated:
                new_lines.append(f"**Updated**: {timestamp}")
            elif in_target and "**Examples**:" in line:
                new_lines.append(line)
                if examples:
                    for ex in examples:
                        new_lines.append(f"- {ex}")
            elif in_target and line.startswith("## "):
                in_target = False
                new_lines.append(line)
            else:
                new_lines.append(line)
        
        patterns_file.write_text("\n".join(new_lines))
    else:
        # 新增 pattern
        count_str = "1"
        examples_str = ""
        if examples:
            for ex in examples:
                examples_str += f"- {ex}\n"
        
        new_pattern = f"""## {pattern_key}

**Description**: {description}
**Count**: {count_str}
**Created**: {timestamp}
**Updated**: {timestamp}

**Examples**:
{(examples_str if examples_str else "- (暂无示例)") + chr(10)}
"""
        
        patterns_file.write_text(existing + new_pattern)
    
    return True


def get_patterns(agent_id: str) -> list:
    """获取所有 patterns"""
    patterns_file = get_patterns_file(agent_id)
    if not patterns_file.exists():
        return []
    
    content = patterns_file.read_text()
    results = []
    current = {}
    
    for line in content.split("\n"):
        if line.startswith("## ") and not line.startswith("## "):
            if current:
                results.append(current)
            current = {"key": line.replace("## ", "").strip()}
        elif "**Description**:" in line:
            current["description"] = line.split("**Description**:")[1].strip()
        elif "**Count**:" in line:
            try:
                current["count"] = int(line.split("**Count**:")[1].strip())
            except:
                current["count"] = 1
        elif "**Created**:" in line:
            current["created"] = line.split("**Created**:")[1].strip()
        elif "**Updated**:" in line:
            current["updated"] = line.split("**Updated**:")[1].strip()
    
    if current:
        results.append(current)
    
    return results


def process_patterns_from_corrections(agent_id: str):
    """
    从 corrections 定期处理生成 patterns
    这是定期 extraction 的入口（被 automation.py 调用）
    """
    from .corrections import get_corrections
    
    corrections = get_corrections(agent_id)
    # TODO: 使用 LLM 聚合相似的 corrections 为 patterns
    # 简化版：只统计高频关键词
    return len(corrections)
