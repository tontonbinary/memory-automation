"""
Corrections Module - 底层原始记录 (JSON Lines 格式)
被纠正的内容、错误做法、正确做法、场景、时间戳

格式兼容 self-improving-agent，支持自动 count 累加
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


def get_l2_dir(agent_id: str) -> Path:
    return Path(os.path.expanduser(f"~/.openclaw/workspaces/{agent_id}/workspace/memory/L2"))


def get_corrections_file(agent_id: str) -> Path:
    return get_l2_dir(agent_id) / "corrections.jsonl"


def ensure_l2_dir(agent_id: str) -> Path:
    """确保 L2 目录存在"""
    l2_dir = get_l2_dir(agent_id)
    l2_dir.mkdir(parents=True, exist_ok=True)
    return l2_dir


def _load_all_corrections(agent_id: str) -> List[Dict]:
    """加载所有纠正记录（用于 count 累加）"""
    corrections_file = get_corrections_file(agent_id)
    if not corrections_file.exists():
        return []
    
    entries = []
    try:
        with open(corrections_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except IOError:
        pass
    return entries


def add_correction(agent_id: str, 
                   topic: str, 
                   wrong: str, 
                   correct: str, 
                   source: str = "self", 
                   context: str = "") -> bool:
    """
    添加纠正记录到 corrections.jsonl (JSON Lines 格式)
    
    Args:
        agent_id: agent 标识
        topic: 纠正主题（如"代码风格"、"沟通方式"）
        wrong: 错误做法
        correct: 正确做法
        source: 来源 (binary/self)
        context: 场景上下文（可选）
    
    Returns:
        是否成功写入
    """
    ensure_l2_dir(agent_id)
    corrections_file = get_corrections_file(agent_id)
    
    # 检查是否已存在相同 topic + wrong 的纠正，累加 count
    existing_entries = _load_all_corrections(agent_id)
    count = 1
    max_count = 0
    
    for entry in existing_entries:
        if entry.get("topic") == topic and entry.get("wrong") == wrong:
            max_count = max(max_count, entry.get("count", 1))
    
    if max_count > 0:
        count = max_count + 1
    
    # 构建 JSON 条目（兼容 self-improving-agent 格式）
    entry = {
        "type": "correction",
        "timestamp": datetime.now().isoformat(),
        "topic": topic,
        "wrong": wrong,
        "correct": correct,
        "context": context if context else "",
        "source": source,
        "count": count
    }
    
    # 追加写入 JSONL 文件
    try:
        with open(corrections_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        
        print(f"✅ 已记录纠正 [{topic}]:")
        print(f"   ❌ 错误: {wrong[:50]}...")
        print(f"   ✅ 正确: {correct[:50]}...")
        if count > 1:
            print(f"   📝 累计次数: {count}")
        return True
    except IOError as e:
        print(f"❌ 保存纠正记录失败: {e}")
        return False


def get_corrections(agent_id: str, 
                   topic: str = None, 
                   limit: int = 50) -> List[Dict]:
    """
    获取纠正记录列表
    
    Args:
        agent_id: agent 标识
        topic: 可选，按主题过滤
        limit: 最多返回条数（默认50，最近N条）
    
    Returns:
        纠正记录列表，按时间倒序
    """
    corrections_file = get_corrections_file(agent_id)
    if not corrections_file.exists():
        return []
    
    entries = []
    try:
        with open(corrections_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    # 按 topic 过滤
                    if topic and entry.get("topic") != topic:
                        continue
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue
    except IOError:
        return []
    
    # 按时间倒序，取最近 limit 条
    entries.reverse()
    return entries[:limit]


def get_correction_topics(agent_id: str) -> List[str]:
    """
    获取所有纠正主题列表（去重）
    
    Args:
        agent_id: agent 标识
    
    Returns:
        主题列表
    """
    corrections = get_corrections(agent_id, limit=1000)
    topics = set()
    for entry in corrections:
        topic = entry.get("topic")
        if topic:
            topics.add(topic)
    return sorted(list(topics))


def search_corrections(agent_id: str, keyword: str) -> List[Dict]:
    """
    搜索纠正记录（在 wrong/correct/topic 中搜索关键词）
    
    Args:
        agent_id: agent 标识
        keyword: 搜索关键词
    
    Returns:
        匹配的纠正记录列表
    """
    corrections = get_corrections(agent_id, limit=1000)
    keyword_lower = keyword.lower()
    results = []
    
    for entry in corrections:
        searchable = " ".join([
            entry.get("topic", ""),
            entry.get("wrong", ""),
            entry.get("correct", ""),
            entry.get("context", "")
        ]).lower()
        
        if keyword_lower in searchable:
            results.append(entry)
    
    return results


def get_high_frequency_corrections(agent_id: str, min_count: int = 3) -> List[Dict]:
    """
    获取高频纠正记录（count >= min_count）
    
    Args:
        agent_id: agent 标识
        min_count: 最小次数阈值
    
    Returns:
        高频纠正记录列表
    """
    corrections = get_corrections(agent_id, limit=1000)
    # 按 topic+wrong 去重，保留 count 最高的
    seen = {}
    for entry in corrections:
        key = (entry.get("topic"), entry.get("wrong"))
        if key not in seen or entry.get("count", 1) > seen[key].get("count", 1):
            seen[key] = entry
    
    # 筛选高频
    high_freq = [e for e in seen.values() if e.get("count", 1) >= min_count]
    # 按 count 倒序
    high_freq.sort(key=lambda x: x.get("count", 1), reverse=True)
    return high_freq


# 兼容旧接口（用于逐步迁移）
def add_correction_legacy(agent_id: str, content: str, source: str = "self", context: str = "") -> bool:
    """
    [兼容旧接口] 使用旧格式（单一 content 字段）写入
    
    将 content 解析为 wrong/correct，或作为整体存储
    """
    # 尝试解析 "X → Y" 或 "X 应该 Y" 格式
    topic = "general"
    wrong = content
    correct = ""
    
    # 常见分隔符尝试解析
    for sep in [" → ", " 应该 ", " 改成 ", " 改为 ", "->", "=>"]:
        if sep in content:
            parts = content.split(sep, 1)
            wrong = parts[0].strip()
            correct = parts[1].strip()
            break
    
    return add_correction(agent_id, topic, wrong, correct, source, context)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "add":
        # CLI: python -m l2_extraction.corrections add --agent xiaoxian --topic "代码风格" --wrong "双引号" --correct "单引号"
        import argparse
        parser = argparse.ArgumentParser(description="添加纠正记录")
        parser.add_argument("--agent", required=True, help="agent 标识")
        parser.add_argument("--topic", required=True, help="纠正主题")
        parser.add_argument("--wrong", required=True, help="错误做法")
        parser.add_argument("--correct", required=True, help="正确做法")
        parser.add_argument("--source", default="binary", help="来源 (binary/self)")
        parser.add_argument("--context", default="", help="上下文")
        args = parser.parse_args()
        
        success = add_correction(args.agent, args.topic, args.wrong, args.correct, args.source, args.context)
        sys.exit(0 if success else 1)
    
    elif len(sys.argv) > 1 and sys.argv[1] == "list":
        # CLI: python -m l2_extraction.corrections list --agent xiaoxian [--topic XXX]
        import argparse
        parser = argparse.ArgumentParser(description="列出纠正记录")
        parser.add_argument("--agent", required=True, help="agent 标识")
        parser.add_argument("--topic", default=None, help="按主题过滤")
        parser.add_argument("--limit", type=int, default=10, help="最多显示条数")
        args = parser.parse_args()
        
        corrections = get_corrections(args.agent, args.topic, args.limit)
        print(f"\n找到 {len(corrections)} 条纠正记录:\n")
        for c in corrections:
            print(f"[{c.get('timestamp', '')[:16]}] {c.get('topic', '')} (count: {c.get('count', 1)})")
            print(f"  ❌ {c.get('wrong', '')[:60]}...")
            print(f"  ✅ {c.get('correct', '')[:60]}...")
            print()
    
    else:
        print("用法:")
        print("  python -m l2_extraction.corrections add --agent <id> --topic <T> --wrong <W> --correct <C>")
        print("  python -m l2_extraction.corrections list --agent <id> [--topic <T>] [--limit <N>]")
