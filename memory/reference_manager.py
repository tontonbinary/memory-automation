"""
ReferenceManager - 参考内容管理器

负责：
- 获取昨日标签（解析昨日 L1）
- 管理自定义标签（读 heartbeat-state.json）
- 组装参考内容注入蒸馏 prompt
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class ReferenceManager:
    """参考内容管理器"""
    
    # 事件类型定义（5类）
    EVENT_TYPES = {
        "CoreWork": "本职核心业务与关键任务",
        "EventsOutside": "临时辅助、无重要成果的事务、游戏放松",
        "SelfEvolve": "知识、纠错、习惯养成",
        "SocialEcology": "用户关系、组织分工、环境规律",
        "RuleDecision": "硬性规则、流程、约束"
    }
    
    def __init__(self, agent_id: str, state_file: Optional[str] = None):
        """
        初始化 ReferenceManager
        
        Args:
            agent_id: Agent ID（必需）
            state_file: heartbeat-state.json 路径
        
        Raises:
            ValueError: 如果 agent_id 为空
        """
        if not agent_id:
            raise ValueError("agent_id 是必需的，不能为空")
        
        self.agent_id = agent_id
        self.state_file = Path(state_file or self._get_default_state_path()).expanduser()
        self.memory_dir = Path(f"~/.openclaw/workspaces/{agent_id}/workspace/memory").expanduser()
        
        # 确保 state 文件目录存在（per-agent 隔离）
        self._ensure_directory()
    
    def _ensure_directory(self) -> None:
        """确保状态文件所在目录存在"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
    
    def _get_default_state_path(self) -> str:
        """获取默认状态文件路径（per-agent 隔离）"""
        return f"~/.openclaw/workspaces/{self.agent_id}/workspace/memory/heartbeat-state.json"
    
    def _load_state(self) -> Dict:
        """加载 heartbeat-state.json"""
        if not self.state_file.exists():
            return {}
        
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except (json.JSONDecodeError, IOError):
            return {}
    
    def get_config_status(self) -> Dict[str, bool]:
        """
        获取配置状态（简化版 - 无需 API key）
        
        Returns:
            {"ready": bool, "message": str}
        """
        return {
            "ready": True,
            "message": "配置就绪"
        }
    
    def is_complete(self) -> Tuple[bool, List[str]]:
        """
        检查配置是否完整（简化版）
        
        Returns:
            (是否完整, 缺失项列表, 状态详情)
        """
        return True, [], {"ready": True}
    
    def get_agent_type(self) -> Optional[str]:
        """获取 agent 类型"""
        state = self._load_state()
        return state.get("agent_types")
    
    def get_custom_tags(self) -> List[str]:
        """获取用户自定义标签"""
        state = self._load_state()
        return state.get("custom_tags", [])
    
    def get_yesterday_tags(self) -> List[str]:
        """
        获取昨日 L1 文件中的所有标签
        
        Returns:
            标签列表（去重）
        """
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_file = self.memory_dir / f"{yesterday}.md"
        
        if not yesterday_file.exists():
            return []
        
        tags = set()
        try:
            with open(yesterday_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # 匹配 `#标签` 格式
                found_tags = re.findall(r'`?(#[\w\-]+)`?', content)
                # 过滤掉行号标签 (#L108) 和纯数字标签 (#18)
                filtered_tags = [t for t in found_tags if not t.startswith('#L') and not t[1:].isdigit()]
                tags.update(filtered_tags)
        except IOError:
            pass
        
        return sorted(list(tags))
    
    def build_reference_content(self, agent_type: Optional[str] = None) -> str:
        """
        组装参考内容
        
        Args:
            agent_type: 如果提供，优先使用；否则从 state 读取
            
        Returns:
            参考内容字符串，用于注入 prompt
        """
        # 获取 agent 类型
        _agent_type = agent_type or self.get_agent_type() or "未设置"
        
        # 获取昨日标签
        yesterday_tags = self.get_yesterday_tags()
        
        # 获取自定义标签
        custom_tags = self.get_custom_tags()
        
        # 组装参考内容
        lines = ["# 参考信息"]
        lines.append(f"\n## Agent 类型（可多选）\n{_agent_type}")
        
        if yesterday_tags:
            lines.append(f"\n## 昨日标签\n" + " ".join(yesterday_tags))
        else:
            lines.append("\n## 昨日标签\n（无）")
        
        if custom_tags:
            lines.append(f"\n## 自定义标签\n" + " ".join(custom_tags))
        
        return "\n".join(lines)
    
    def add_custom_tag(self, tag: str) -> bool:
        """
        添加自定义标签
        
        Args:
            tag: 标签名（如 "#urgent"）
            
        Returns:
            是否成功
        """
        state = self._load_state()
        custom_tags = state.get("custom_tags", [])
        
        # 标准化标签格式
        if not tag.startswith("#"):
            tag = f"#{tag}"
        
        if tag not in custom_tags:
            custom_tags.append(tag)
            state["custom_tags"] = custom_tags
            
            try:
                self.state_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.state_file, 'w', encoding='utf-8') as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
                return True
            except IOError:
                return False
        
        return True  # 已存在也算成功
    
    def classify_event_type(self, content: str, item_type: str) -> str:
        """
        根据内容判断事件类型（5 选 1）
        
        Args:
            content: 蒸馏内容
            item_type: 5 类之一（Event/Preference/To-do/Output/Emotion）
            
        Returns:
            事件类型（CoreWork/EventsOutside/SelfEvolve/SocialEcology/RuleDecision）
        """
        content_lower = content.lower()
        
        # 关键词匹配（按优先级排序）
        
        # 1. RuleDecision - 硬性规则、流程
        if any(kw in content_lower for kw in ["必须", "禁止", "规范", "标准", "规则", "流程", "约束"]):
            return "RuleDecision"
        
        # 2. SelfEvolve - 知识、纠错、习惯养成
        if item_type in ["Improve", "SelfEvolve"] or \
           any(kw in content_lower for kw in ["纠正", "改进", "学习", "进化", "习惯养成", "知识"]):
            return "SelfEvolve"
        
        # 3. SocialEcology - 用户关系、组织分工、环境规律
        if item_type == "Preference" or \
           any(kw in content_lower for kw in ["用户关系", "组织", "分工", "人际", "环境规律", "偏好", "习惯"]):
            return "SocialEcology"
        
        # 4. CoreWork - 本职核心业务
        if any(kw in content_lower for kw in ["skill", "代码", "coding", "实现", "修复", "bug", "开发", "架构", "设计", "核心工作"]):
            return "CoreWork"
        
        # 5. EventsOutside - 临时辅助、无重要成果
        if any(kw in content_lower for kw in ["临时", "辅助", "帮忙", "简单", "游戏", "放松", "娱乐"]):
            return "EventsOutside"
        
        # 默认：Event/To-do/Output 等核心工作相关 → CoreWork
        if item_type in ["Event", "To-do", "Output"]:
            return "CoreWork"
        
        # 其他默认 EventsOutside
        return "EventsOutside"


# 便捷函数
def get_reference_manager(agent_id: str) -> ReferenceManager:
    """获取 ReferenceManager 实例
    
    Args:
        agent_id: Agent ID（必需）
    
    Raises:
        ValueError: 如果 agent_id 为空
    """
    if not agent_id:
        raise ValueError("agent_id 是必需的，不能为空")
    return ReferenceManager(agent_id=agent_id)