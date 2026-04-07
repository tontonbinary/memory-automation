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
    
    # 事件类型定义
    EVENT_TYPES = {
        "CoreWork": "本职核心业务与关键任务",
        "CollabResult": "接收其他 Agent 交付的成果",
        "AuxTask": "临时辅助、无重要成果的事务",
        "SelfEvolve": "知识、纠错、规则、红线",
        "EnvAwareness": "用户、系统、分工、规律"
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
    
    def _get_default_state_path(self) -> str:
        """获取默认状态文件路径"""
        return f"~/.openclaw/skills/memory-automation/memory/heartbeat-state.json"
    
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
        获取配置状态
        
        自动检查多个来源：
        1. 环境变量
        2. config.json
        3. OpenClaw 默认配置
        
        Returns:
            {"api_key": bool, "agent_types": bool, "api_key_source": str}
        """
        import os
        state = self._load_state()
        
        api_key = None
        api_key_source = None
        
        # 1. 检查环境变量
        env_key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("MINIMAX_API_TOKEN")
        if env_key:
            api_key = env_key
            api_key_source = "environment"
        
        # 2. 检查 config.json（优先级：config.local.json > config.json）
        if not api_key:
            skill_dir = Path("~/.openclaw/skills/memory-automation").expanduser()
            
            # 优先检查 config.local.json（本地配置，不提交到 Git）
            local_config_path = skill_dir / "config.local.json"
            if local_config_path.exists():
                try:
                    with open(local_config_path) as f:
                        config = json.load(f)
                        cfg_key = config.get("llm", {}).get("api_key", "")
                        if cfg_key and not cfg_key.startswith("YOUR_"):
                            api_key = cfg_key
                            api_key_source = "config.local.json"
                except:
                    pass
            
            # 然后检查 config.json（模板配置）
            if not api_key:
                config_path = skill_dir / "config.json"
                if config_path.exists():
                    try:
                        with open(config_path) as f:
                            config = json.load(f)
                            cfg_key = config.get("llm", {}).get("api_key", "")
                            if cfg_key and not cfg_key.startswith("YOUR_"):
                                api_key = cfg_key
                                api_key_source = "config.json"
                    except:
                        pass
        
        # 3. 尝试从 OpenClaw 配置提取
        if not api_key:
            api_key = self._try_extract_openclaw_api_key()
            if api_key:
                api_key_source = "openclaw_default"
        
        # agent_type: 从 heartbeat-state.json 读
        agent_types = bool(state.get("agent_types"))
        
        return {
            "api_key": bool(api_key),
            "api_key_value": api_key,  # 实际 key 值（可选）
            "api_key_source": api_key_source,
            "agent_types": agent_types
        }
    
    def _try_extract_openclaw_api_key(self) -> Optional[str]:
        """尝试从 OpenClaw 配置提取 API key"""
        try:
            home = Path.home()
            possible_agents = ["xiaoxian", "code", "main", "TS", self.agent_id]
            
            for agent in possible_agents:
                auth_file = home / ".openclaw" / "agents" / agent / "agent" / "auth-profiles.json"
                if auth_file.exists():
                    with open(auth_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    profiles = data.get("profiles", {})
                    for profile_name, profile in profiles.items():
                        if "minimax" in profile_name.lower():
                            token = profile.get("access") or profile.get("key")
                            if token:
                                return token
                    
                    # 尝试任何可用 key
                    for profile in profiles.values():
                        token = profile.get("access") or profile.get("key")
                        if token and len(token) > 20:
                            return token
        except:
            pass
        
        return None
    
    def is_complete(self) -> Tuple[bool, List[str]]:
        """
        检查配置是否完整
        
        现在 API key 可以自动提取，通常不需要用户手动配置
        
        Returns:
            (是否完整, 缺失项列表, 状态详情)
        """
        status = self.get_config_status()
        missing = []
        
        if not status["api_key"]:
            missing.append("api_key")
        # agent_types 不再作为必需项
        
        return len(missing) == 0, missing, status
    
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
            item_type: 7 类之一（Event/Decision/Preference/Improve/To-do/Output/Emotion）
            
        Returns:
            事件类型（CoreWork/CollabResult/AuxTask/SelfEvolve/EnvAwareness）
        """
        content_lower = content.lower()
        
        # Improve 类型 → SelfEvolve
        if item_type == "Improve":
            return "SelfEvolve"
        
        # Preference 类型 → EnvAwareness（用户偏好属于环境认知）
        if item_type == "Preference":
            return "EnvAwareness"
        
        # 关键词匹配
        if any(kw in content_lower for kw in ["skill", "代码", "coding", "实现", "修复", "bug"]):
            return "CoreWork"
        
        if any(kw in content_lower for kw in ["交付", "接收", "协作", "agent", "来自"]):
            return "CollabResult"
        
        if any(kw in content_lower for kw in ["临时", "辅助", "帮忙", "简单"]):
            return "AuxTask"
        
        if any(kw in content_lower for kw in ["规则", "规范", "红线", "纠正", "改进", "学习", "进化"]):
            return "SelfEvolve"
        
        if any(kw in content_lower for kw in ["用户", "系统", "分工", "环境", "习惯", "偏好"]):
            return "EnvAwareness"
        
        # 默认
        if item_type in ["Decision", "Event"]:
            return "CoreWork"
        
        return "AuxTask"


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