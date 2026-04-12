"""
Patterns Module - 中层聚合
从多次 corrections 中发现重复模式
关联 confidence 置信度（count 次数）
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


def get_l2_dir(agent_id: str) -> Path:
    return Path(os.path.expanduser(f"~/.openclaw/workspaces/{agent_id}/workspace/memory/L2"))


def get_patterns_file(agent_id: str) -> Path:
    return get_l2_dir(agent_id) / "patterns.md"


def ensure_l2_dir(agent_id: str) -> Path:
    l2_dir = get_l2_dir(agent_id)
    l2_dir.mkdir(parents=True, exist_ok=True)
    return l2_dir


def add_or_update_pattern(agent_id: str, 
                          pattern_key: str, 
                          description: str, 
                          examples: list = None,
                          confidence: int = 1):
    """
    添加或更新 pattern
    
    Args:
        agent_id: agent 标识
        pattern_key: 模式标识（如 "code-style-quotes"）
        description: 模式描述
        examples: 示例列表
        confidence: 置信度（基于 count 次数）
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
        # 更新现有 pattern，增加 count 和 confidence
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
            elif in_target and line.startswith("**Confidence**:") and not count_updated:
                # 更新 confidence（取现有值和新值的平均）
                conf_str = line.split("**Confidence**:")[1].strip()
                try:
                    old_conf = int(conf_str)
                    new_conf = min(10, max(old_conf, confidence))  # 取较大值，上限10
                except:
                    new_conf = confidence
                new_lines.append(f"**Confidence**: {new_conf}/10")
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
        examples_str = ""
        if examples:
            for ex in examples:
                examples_str += f"- {ex}\n"
        
        new_pattern = f"""## {pattern_key}

**Description**: {description}
**Count**: 1
**Confidence**: {confidence}/10
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
        if line.startswith("## "):
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
        elif "**Confidence**:" in line:
            try:
                conf_str = line.split("**Confidence**:")[1].strip().replace("/10", "")
                current["confidence"] = int(conf_str)
            except:
                current["confidence"] = 1
        elif "**Created**:" in line:
            current["created"] = line.split("**Created**:")[1].strip()
        elif "**Updated**:" in line:
            current["updated"] = line.split("**Updated**:")[1].strip()
    
    if current:
        results.append(current)
    
    return results


def get_high_confidence_patterns(agent_id: str, min_confidence: int = 7) -> List[Dict]:
    """
    获取高置信度 patterns（可用于 Agent 主动提炼到 L3 MEMORY.md）
    
    Args:
        agent_id: agent 标识
        min_confidence: 最小置信度（1-10）
    
    Returns:
        高置信度 pattern 列表
    """
    patterns = get_patterns(agent_id)
    return [p for p in patterns if p.get("confidence", 0) >= min_confidence]


def _group_corrections_by_topic(corrections: List[Dict]) -> Dict[str, List[Dict]]:
    """
    将 corrections 按 topic 分组
    
    Returns:
        {topic: [correction1, correction2, ...]}
    """
    groups = {}
    for c in corrections:
        topic = c.get("topic", "general")
        if topic not in groups:
            groups[topic] = []
        groups[topic].append(c)
    return groups


def _generate_pattern_key(topic: str, wrong: str, correct: str) -> str:
    """
    生成 pattern_key
    
    规则：topic + 简化后的 wrong/correct
    示例："code-style-quotes", "communication-formality"
    """
    # 简化处理
    key_parts = [topic.lower().replace(" ", "-")]
    
    # 从 wrong/correct 中提取关键词
    keywords = []
    for text in [wrong, correct]:
        # 取前3个中文字符或前5个英文字符作为标识
        text = text.strip()[:10]
        if text:
            keywords.append(text.lower().replace(" ", "-"))
    
    if keywords:
        key_parts.append("-".join(keywords))
    
    # 限制长度
    key = "-".join(key_parts)[:50]
    return key


def _calculate_confidence(count: int, occurrences: List[Dict]) -> int:
    """
    计算 pattern 的置信度
    
    规则：
    - count 3-4: confidence 5-6 (初步模式)
    - count 5-7: confidence 7-8 (稳定模式)
    - count 8+: confidence 9-10 (强模式)
    
    Returns:
        1-10 的整数
    """
    if count >= 8:
        return min(10, 8 + count // 10)
    elif count >= 5:
        return 7
    elif count >= 3:
        return 5
    else:
        return min(4, count)


def process_patterns_from_corrections(agent_id: str, 
                                       min_count: int = 3,
                                       dry_run: bool = False) -> Dict:
    """
    从 corrections 定期处理生成 patterns
    
    工作流程：
    1. 读取所有 corrections（利用 JSONL 格式的 count 字段）
    2. 按 topic + wrong/correct 相似度分组
    3. 对高频组（count >= min_count）生成或更新 pattern
    4. 计算 confidence 置信度
    
    Args:
        agent_id: agent 标识
        min_count: 最小次数阈值（默认3次）
        dry_run: 是否仅模拟，不实际写入
    
    Returns:
        处理结果统计
    """
    from .corrections import get_corrections, get_high_frequency_corrections
    
    print(f"\n[Patterns] 开始处理 agent: {agent_id}")
    print(f"  最小次数阈值: {min_count}")
    print(f"  模拟模式: {dry_run}\n")
    
    # 1. 获取高频纠正记录（已经按 count 排序）
    high_freq_corrections = get_high_frequency_corrections(agent_id, min_count)
    
    if not high_freq_corrections:
        print(f"[Patterns] 未找到 count >= {min_count} 的纠正记录")
        return {
            "processed": 0,
            "created": 0,
            "updated": 0,
            "patterns": []
        }
    
    print(f"[Patterns] 找到 {len(high_freq_corrections)} 条高频纠正记录\n")
    
    # 2. 按 topic 分组处理
    grouped = _group_corrections_by_topic(high_freq_corrections)
    
    created = 0
    updated = 0
    pattern_keys = []
    
    for topic, corrections_list in grouped.items():
        print(f"  Topic: {topic} ({len(corrections_list)} 条)")
        
        for correction in corrections_list:
            wrong = correction.get("wrong", "")
            correct = correction.get("correct", "")
            count = correction.get("count", 1)
            context = correction.get("context", "")
            
            # 生成 pattern_key
            pattern_key = _generate_pattern_key(topic, wrong, correct)
            
            # 生成描述
            description = f"用户在 {topic} 方面倾向于：{correct} 而非 {wrong}"
            
            # 准备示例
            examples = [
                f"纠正 #{count}: {wrong} → {correct}",
                f"上下文: {context[:50]}..." if len(context) > 50 else f"上下文: {context}"
            ]
            
            # 计算置信度
            confidence = _calculate_confidence(count, [correction])
            
            if dry_run:
                print(f"    [模拟] Pattern: {pattern_key}")
                print(f"           Count: {count}, Confidence: {confidence}/10")
                print(f"           Description: {description[:60]}...")
            else:
                # 检查是否已存在
                existing_patterns = get_patterns(agent_id)
                exists = any(p.get("key") == pattern_key for p in existing_patterns)
                
                # 添加或更新 pattern
                add_or_update_pattern(
                    agent_id=agent_id,
                    pattern_key=pattern_key,
                    description=description,
                    examples=examples,
                    confidence=confidence
                )
                
                if exists:
                    updated += 1
                    print(f"    [更新] {pattern_key} (count: {count})")
                else:
                    created += 1
                    print(f"    [新建] {pattern_key} (count: {count}, confidence: {confidence}/10)")
            
            pattern_keys.append(pattern_key)
    
    result = {
        "processed": len(high_freq_corrections),
        "created": created,
        "updated": updated,
        "patterns": pattern_keys,
        "dry_run": dry_run
    }
    
    print(f"\n[Patterns] 处理完成")
    print(f"  处理纠正: {result['processed']} 条")
    print(f"  新建 pattern: {created} 个")
    print(f"  更新 pattern: {updated} 个")
    
    return result


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "process":
            # CLI: python -m l2_extraction.patterns process --agent xiaoxian [--min 3] [--dry-run]
            import argparse
            parser = argparse.ArgumentParser(description="从 corrections 生成 patterns")
            parser.add_argument("--agent", required=True, help="agent 标识")
            parser.add_argument("--min", type=int, default=3, dest="min_count", help="最小次数阈值")
            parser.add_argument("--dry-run", action="store_true", help="模拟模式")
            args = parser.parse_args()
            
            result = process_patterns_from_corrections(
                args.agent, 
                min_count=args.min_count,
                dry_run=args.dry_run
            )
            sys.exit(0 if result["processed"] >= 0 else 1)
        
        elif cmd == "list":
            # CLI: python -m l2_extraction.patterns list --agent xiaoxian
            import argparse
            parser = argparse.ArgumentParser(description="列出 patterns")
            parser.add_argument("--agent", required=True, help="agent 标识")
            parser.add_argument("--min-confidence", type=int, default=0, help="最小置信度过滤")
            args = parser.parse_args()
            
            patterns = get_patterns(args.agent)
            if args.min_confidence > 0:
                patterns = [p for p in patterns if p.get("confidence", 0) >= args.min_confidence]
            
            print(f"\n找到 {len(patterns)} 个 patterns:\n")
            for p in patterns:
                print(f"  [{p.get('key')}]")
                print(f"    Description: {p.get('description', '')[:60]}...")
                print(f"    Count: {p.get('count', 1)}, Confidence: {p.get('confidence', 1)}/10")
                print()
        
        else:
            print("用法:")
            print("  python -m l2_extraction.patterns process --agent <id> [--min 3] [--dry-run]")
            print("  python -m l2_extraction.patterns list --agent <id> [--min-confidence 7]")
    else:
        print("用法:")
        print("  python -m l2_extraction.patterns process --agent <id> [--min 3] [--dry-run]")
        print("  python -m l2_extraction.patterns list --agent <id> [--min-confidence 7]")
