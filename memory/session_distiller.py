"""
会话蒸馏模块 - 从消息中提取关键信息
支持 LLM 智能蒸馏 + 正则匹配降级
"""

import json
import os
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import urllib.request
import urllib.error


@dataclass
class DistilledItem:
    """蒸馏后的记忆项"""
    item_type: str  # event, decision, preference, emotion, action
    content: str
    emotion: Optional[str] = None
    follow_up: Optional[str] = None
    tags: List[str] = None
    source_message: str = ""
    outcome: Optional[str] = None  # 成果：文件路径、URL 或对话框内容描述
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class SessionDistiller:
    """会话蒸馏器 - 提取消息中的关键信息"""
    
    # 提取模式定义（正则匹配，作为 LLM 失败时的降级方案）
    PATTERNS = {
        "event": [
            r"(创建了|完成了|修复了|解决了|删除了|更新了|添加了|修改了|实现了)(.+?)(?:。|$)",
            r"(发布|部署|提交|合并|推送)(.+?)(?:。|$)",
            r"(发现|遇到|出现)(.+?)(?:问题|错误|bug|异常)(?:。|$)",
        ],
        "decision": [
            r"(决定|确认|采用|选择|使用|设置为)(.+?)(?:。|$)",
            r"(不|没)(?:需要|要|准备|打算)(.+?)(?:。|$)",
            r"(同意|拒绝|接受|放弃)(.+?)(?:。|$)",
            r"(应该|需要|最好|建议)(.+?)(?:。|$)",
        ],
        "preference": [
            r"(我喜欢|我偏好|我想要|我倾向于|我更|我希望)(.+?)(?:。|$)",
            r"(偏好|倾向|喜欢)(.+?)(?:风格|方式|模式|类型|颜色|布局)(?:。|$)",
            r"(不要|不想|不喜欢)(.+?)(?:。|$)",
        ],
        "emotion": [
            r"(太棒了|很好|不错|完美|优秀|赞|厉害)(?:！|。|$)",
            r"(感谢|谢谢|感激)(?:！|。|$)",
            r"(好的|明白|了解|清楚|知道了)(?:！|。|$)",
            r"(着急|焦虑|担心|困惑|麻烦|头痛)(?:。|$)",
        ],
        "action": [
            r"(去做|开始|启动|准备|着手|尝试|研究)(.+?)(?:。|$)",
            r"(下一步|接下来|之后|稍后|等会)(.+?)(?:。|$)",
            r"(记得|别忘了|注意|确保|检查)(.+?)(?:。|$)",
        ],
    }
    
    # 情绪关键词
    EMOTION_POSITIVE = ["太棒了", "很好", "不错", "完美", "优秀", "赞", "厉害", "感谢", "谢谢"]
    EMOTION_NEGATIVE = ["着急", "焦虑", "担心", "困惑", "麻烦", "头痛", "糟糕", "错误", "失败"]
    
    # LLM 蒸馏 Prompt 模板（使用 str.replace 格式化，避免 { } 占位符冲突）
    DISTILLATION_PROMPT = """你是一名智能会话分析助手，负责从对话记录中提取关键信息。

## 任务说明
请分析以下对话内容，提取值得长期记忆的**关键信息**。

## L1 蒸馏规则（5种类型）

### 1. event（事件）
- 用户或助手完成的具体事项
- 格式：【主体】+【动作】+【对象】
- 示例："创建了项目文档"、"修复了登录Bug"、"部署了新版网站"

### 2. decision（决策）
- 明确的决定、选择或判断
- 格式：【决定】+【内容】+【依据/原因】（如有）
- 示例："决定使用 React 框架"、"确认下周三开会"、"放弃该方案"

### 3. preference（偏好）
- 用户的喜好、倾向、习惯
- 格式：【主体】+【偏好类型】+【具体内容】
- 示例："偏好暗色主题"、"喜欢简洁的代码风格"、"倾向于早上开会"

### 4. emotion（情绪）
- 对话中表达的情感状态
- 格式：【情绪类型】+【触发原因/对象】
- 示例："对进度满意"、"担心截止日期"、"感谢帮助"

### 5. action（行动）
- 计划要做的、建议的后续行动
- 格式：【行动】+【时间/条件】+【目标】
- 示例："明天整理文档"、"需要调研竞品"、"记得测试边界情况"

## 输出格式要求

请严格按照以下 JSON 格式输出（不要有任何额外文字）：

```json
{
  "items": [
    {
      "item_type": "event|decision|preference|emotion|action",
      "content": "提取的核心内容（简洁，20-100字）",
      "emotion": "positive|negative|null",
      "follow_up": "后续行动建议（如有，否则null）",
      "tags": ["标签1", "标签2", "标签3"],
      "outcome": "成果描述（文件路径、URL等，否则null）"
    }
  ]
}
```

## 标签建议
请从以下类别中选择 2-4 个标签：
- 技术相关：coding, devops, frontend, backend, database, api, security
- 业务相关：meeting, planning, decision, requirement, design, review
- 状态相关：completed, in-progress, blocked, urgent, important
- 角色相关：user, assistant
- 内容相关：document, code, config, data, bug, feature

## 会话内容

__SESSION_CONTENT__

## 注意事项
1. 只提取**真正值得记忆**的内容，过滤闲聊、重复、临时信息
2. 内容要**简洁具体**，不要泛泛而谈
3. 每个提取项必须是独立的 JSON 对象
4. 如果没有值得提取的内容，返回 {"items": []}
5. **必须**返回合法的 JSON 格式，不要添加 markdown 代码块标记
"""
    
    def __init__(self, min_message_length: int = 10, config_path: Optional[str] = None):
        """
        初始化蒸馏器
        
        Args:
            min_message_length: 最小消息长度，短于此值的消息被忽略
            config_path: 配置文件路径（用于读取 LLM API 配置）
        """
        self.min_message_length = min_message_length
        self.config = self._load_config(config_path)
        self.llm_config = self._get_llm_config()
    
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """加载配置文件"""
        default_config = {
            "llm": {
                "enabled": True,
                "provider": "minimax",
                "model": "MiniMax-Text-01",
                "api_endpoint": "https://api.minimax.chat/v1/text/chatcompletion_v2",
                "temperature": 0.3,
                "max_tokens": 4000,
                "timeout": 60,
                "stream": False
            },
            "fallback_to_regex": True
        }
        
        # 尝试加载配置文件
        if not config_path:
            # 默认配置文件位置
            skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(skill_dir, "config.json")
        
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # 递归合并配置
                    if "llm" in loaded:
                        default_config["llm"].update(loaded["llm"])
                    if "fallback_to_regex" in loaded:
                        default_config["fallback_to_regex"] = loaded["fallback_to_regex"]
            except (json.JSONDecodeError, IOError) as e:
                print(f"[SessionDistiller] 加载配置失败，使用默认配置: {e}")
        
        return default_config
    
    def _get_llm_config(self) -> Dict[str, Any]:
        """获取 LLM 配置，优先从环境变量读取 API Key"""
        llm_config = self.config.get("llm", {})
        
        # 从环境变量读取 API Key（优先级最高）
        api_key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("MINIMAX_API_TOKEN")
        
        # 如果环境变量没有，尝试从配置读取
        if not api_key and "api_key" in llm_config:
            api_key = llm_config["api_key"]
        
        llm_config["api_key"] = api_key
        return llm_config
    
    def _format_messages_for_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """将消息列表格式化为 prompt 可用的文本"""
        formatted_lines = []
        
        for msg in messages:
            role = msg.get("role", "unknown")
            # content 可能是 list（富文本格式）或 string，需要统一处理
            raw_content = msg.get("content", "")
            if isinstance(raw_content, list):
                content = " ".join(
                    item.get("text", "") for item in raw_content
                    if isinstance(item, dict) and item.get("type") == "text"
                )
            else:
                content = str(raw_content)
            content = content.strip()
            timestamp = msg.get("timestamp", "")
            
            # 跳过空消息和短消息
            if len(content) < self.min_message_length:
                continue
            
            # 角色显示名称
            role_display = "用户" if role == "user" else ("助手" if role == "assistant" else role)
            
            # 格式化时间
            time_str = ""
            if timestamp:
                try:
                    # 尝试解析 ISO 格式时间
                    if isinstance(timestamp, str) and len(timestamp) >= 10:
                        time_str = f"[{timestamp[11:16]}] " if 'T' in timestamp else f"[{timestamp}] "
                except:
                    pass
            
            formatted_lines.append(f"{time_str}{role_display}: {content}")
        
        return "\n\n".join(formatted_lines)
    
    def _call_minimax_api(self, prompt: str) -> Optional[str]:
        """
        调用 Minimax LLM API
        
        Args:
            prompt: 完整的 prompt 文本
            
        Returns:
            API 返回的文本内容，失败时返回 None
        """
        if not self.llm_config.get("api_key"):
            print("[SessionDistiller] LLM API Key 未配置")
            return None
        
        api_endpoint = self.llm_config.get("api_endpoint", "https://api.minimax.chat/v1/text/chatcompletion_v2")
        model = self.llm_config.get("model", "MiniMax-Text-01")
        temperature = self.llm_config.get("temperature", 0.3)
        max_tokens = self.llm_config.get("max_tokens", 4000)
        timeout = self.llm_config.get("timeout", 60)
        stream = self.llm_config.get("stream", False)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.llm_config['api_key']}"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是一个专业的会话分析助手，擅长提取关键信息并返回结构化数据。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }
        
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                api_endpoint,
                data=data,
                headers=headers,
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = json.loads(response.read().decode('utf-8'))
                
                # 解析响应
                if "choices" in result and len(result["choices"]) > 0:
                    msg = result["choices"][0].get("message", {})
                    # MiniMax-M2.7 使用 reasoning_content
                    content = msg.get("content") or msg.get("reasoning_content", "")
                    if content:
                        return content
                    print(f"[SessionDistiller] 响应 message 为空: {msg}")
                    return None
                elif "data" in result and "choices" in result["data"]:
                    content = result["data"]["choices"][0].get("message", {}).get("content", "")
                    return content
                else:
                    print(f"[SessionDistiller] 意外的 API 响应格式: {str(result)[:200]}")
                    return None
                    
        except urllib.error.HTTPError as e:
            error_code = e.code
            if error_code in [401, 403]:
                print("[MEMORY-AUTOMATION] API_ERROR: API_KEY_INVALID")
            elif error_code == 429:
                print("[MEMORY-AUTOMATION] API_ERROR: API_RATE_LIMITED")
            else:
                print(f"[MEMORY-AUTOMATION] API_ERROR: HTTP_{error_code}")
            try:
                error_body = e.read().decode('utf-8')
                print(f"[SessionDistiller] 错误详情: {error_body[:200]}")
            except:
                pass
            return None
        except urllib.error.URLError as e:
            print("[MEMORY-AUTOMATION] API_ERROR: API_CONNECTION_ERROR")
            print(f"[SessionDistiller] 错误详情: {e.reason}")
            return None
        except json.JSONDecodeError as e:
            print(f"[MEMORY-AUTOMATION] API_ERROR: API_RESPONSE_PARSE_ERROR")
            print(f"[SessionDistiller] 错误详情: {e}")
            return None
        except Exception as e:
            print(f"[MEMORY-AUTOMATION] API_ERROR: {type(e).__name__}")
            print(f"[SessionDistiller] 错误详情: {e}")
            return None
    
    def _parse_llm_response(self, response: str) -> List[Dict[str, Any]]:
        """
        解析 LLM 返回的 JSON 响应
        
        Args:
            response: LLM 返回的原始文本
            
        Returns:
            解析后的 items 列表
        """
        if not response:
            return []
        
        try:
            # 清理可能的 markdown 代码块标记
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            
            # 解析 JSON
            data = json.loads(cleaned)
            
            if isinstance(data, dict) and "items" in data:
                items = data["items"]
                if isinstance(items, list):
                    return items
            elif isinstance(data, list):
                # 有些模型可能直接返回数组
                return data
            
            print(f"[SessionDistiller] LLM 响应格式不符合预期: {data}")
            return []
            
        except json.JSONDecodeError as e:
            print(f"[SessionDistiller] 无法解析 LLM 响应为 JSON: {e}")
            print(f"[SessionDistiller] 原始响应: {response[:200]}...")
            return []
        except Exception as e:
            print(f"[SessionDistiller] 解析 LLM 响应时出错: {e}")
            return []
    
    def distill_with_llm(self, messages: List[Dict[str, Any]]) -> List[DistilledItem]:
        """
        使用 LLM 进行智能蒸馏
        
        Args:
            messages: 消息列表
            
        Returns:
            蒸馏后的记忆项列表
        """
        if not self.llm_config.get("enabled", True):
            print("[SessionDistiller] LLM 蒸馏已禁用")
            return []
        
        # 格式化会话内容
        session_content = self._format_messages_for_prompt(messages)
        
        if not session_content:
            print("[SessionDistiller] 没有足够的内容进行 LLM 蒸馏")
            return []
        
        # 构建 prompt
        prompt = self.DISTILLATION_PROMPT.replace("__SESSION_CONTENT__", session_content)
        
        # 调用 LLM API
        print("[SessionDistiller] 正在调用 LLM 进行智能蒸馏...")
        response = self._call_minimax_api(prompt)
        
        if not response:
            print("[SessionDistiller] LLM API 调用失败")
            return []
        
        # 解析响应
        items_data = self._parse_llm_response(response)
        
        if not items_data:
            print("[SessionDistiller] LLM 未返回有效提取项")
            return []
        
        # 转换为 DistilledItem 对象
        distilled_items = []
        for item_data in items_data:
            try:
                # 验证必要字段
                if "item_type" not in item_data or "content" not in item_data:
                    continue
                
                # 确保 item_type 有效
                item_type = item_data["item_type"]
                if item_type not in ["event", "decision", "preference", "emotion", "action"]:
                    item_type = "event"  # 默认类型
                
                # 构建 DistilledItem
                item = DistilledItem(
                    item_type=item_type,
                    content=item_data.get("content", ""),
                    emotion=item_data.get("emotion") if item_data.get("emotion") != "null" else None,
                    follow_up=item_data.get("follow_up") if item_data.get("follow_up") != "null" else None,
                    tags=item_data.get("tags", []),
                    source_message="",  # LLM 版本不保留原始消息引用
                    outcome=item_data.get("outcome") if item_data.get("outcome") != "null" else None
                )
                
                # 去重检查
                if not self._is_duplicate(item, distilled_items):
                    distilled_items.append(item)
                    
            except Exception as e:
                print(f"[SessionDistiller] 处理 LLM 返回项时出错: {e}")
                continue
        
        print(f"[SessionDistiller] LLM 蒸馏完成，提取 {len(distilled_items)} 项")
        return distilled_items
    
    def distill_messages(self, messages: List[Dict[str, Any]], use_llm: bool = True) -> List[DistilledItem]:
        """
        从消息列表中蒸馏关键信息
        
        Args:
            messages: 消息列表，每个消息为字典，包含 role 和 content
            use_llm: 是否优先使用 LLM 蒸馏（默认 True）
            
        Returns:
            蒸馏后的记忆项列表
        """
        # 优先尝试 LLM 蒸馏
        if use_llm and self.llm_config.get("enabled", True):
            try:
                llm_items = self.distill_with_llm(messages)
                if llm_items:
                    return llm_items
                # LLM 返回空结果，检查是否启用降级
                if not self.config.get("fallback_to_regex", True):
                    return []
                print("[SessionDistiller] LLM 未提取到内容，降级到正则匹配...")
            except Exception as e:
                error_msg = str(e)
                if "API_KEY" in error_msg or "API_ERROR" in error_msg:
                    # 已经是 [MEMORY-AUTOMATION] 格式的错误消息，直接打印
                    pass
                elif "401" in error_msg or "403" in error_msg:
                    print("[MEMORY-AUTOMATION] API_ERROR: API_KEY_INVALID")
                elif "429" in error_msg:
                    print("[MEMORY-AUTOMATION] API_ERROR: API_RATE_LIMITED")
                elif "JSON" in error_msg or "Parse" in error_msg:
                    print(f"[MEMORY-AUTOMATION] API_ERROR: API_RESPONSE_PARSE_ERROR")
                elif "Connection" in error_msg or "network" in error_msg.lower():
                    print("[MEMORY-AUTOMATION] API_ERROR: API_CONNECTION_ERROR")
                else:
                    print(f"[MEMORY-AUTOMATION] API_ERROR: {type(e).__name__}")
                print(f"[SessionDistiller] LLM 蒸馏异常，降级到正则匹配: {e}")
                if not self.config.get("fallback_to_regex", True):
                    return []
        
        # 正则匹配（作为 fallback）
        return self._distill_with_regex(messages)
    
    def _distill_with_regex(self, messages: List[Dict[str, Any]]) -> List[DistilledItem]:
        """
        使用正则表达式进行蒸馏（原始方法，作为 fallback）
        
        Args:
            messages: 消息列表
            
        Returns:
            蒸馏后的记忆项列表
        """
        distilled_items = []
        
        for idx, msg in enumerate(messages):
            # content 可能是 list（富文本格式）或 string，需要统一处理
            raw_content = msg.get("content", "")
            if isinstance(raw_content, list):
                content = " ".join(
                    item.get("text", "") for item in raw_content
                    if isinstance(item, dict) and item.get("type") == "text"
                )
            else:
                content = str(raw_content)
            content = content.strip()
            role = msg.get("role", "unknown")
            
            # 跳过短消息
            if len(content) < self.min_message_length:
                continue
            
            # 尝试提取各类型信息
            for item_type, patterns in self.PATTERNS.items():
                for pattern in patterns:
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for match in matches:
                        distilled_content = match.group(0)
                        
                        # 检测情绪
                        emotion = self._detect_emotion(content)
                        
                        # 生成标签
                        tags = self._generate_tags(item_type, content, role)
                        
                        # 查找后续行动（通常在消息后半部分）
                        follow_up = self._extract_follow_up(content)
                        
                        # 提取成果（文件路径、URL 或"已输出"描述）
                        outcome = self._extract_outcome(content, role)
                        
                        item = DistilledItem(
                            item_type=item_type,
                            content=distilled_content,
                            emotion=emotion,
                            follow_up=follow_up,
                            tags=tags,
                            source_message=content[:200],  # 限制长度
                            outcome=outcome
                        )
                        
                        # 去重检查
                        if not self._is_duplicate(item, distilled_items):
                            distilled_items.append(item)
        
        return distilled_items
    
    def _detect_emotion(self, content: str) -> Optional[str]:
        """检测情绪关键词"""
        for word in self.EMOTION_POSITIVE:
            if word in content:
                return "positive"
        for word in self.EMOTION_NEGATIVE:
            if word in content:
                return "negative"
        return None
    
    def _generate_tags(self, item_type: str, content: str, role: str) -> List[str]:
        """生成标签"""
        tags = [item_type]
        
        # 根据内容添加标签
        if "代码" in content or "编程" in content or "bug" in content.lower():
            tags.append("coding")
        if "会议" in content or "讨论" in content:
            tags.append("meeting")
        if "问题" in content or "疑问" in content:
            tags.append("question")
        if "完成" in content or "搞定" in content:
            tags.append("completed")
        if "计划" in content or "安排" in content:
            tags.append("planning")
        
        # 根据角色添加标签
        if role == "user":
            tags.append("user")
        elif role == "assistant":
            tags.append("assistant")
        
        return tags
    
    def _extract_follow_up(self, content: str) -> Optional[str]:
        """提取后续行动"""
        # 查找后续行动的关键词
        follow_patterns = [
            r"(下一步|接下来|之后|稍后)(.+?)(?:。|$)",
            r"(记得|别忘了|注意|确保|检查)(.+?)(?:。|$)",
        ]
        
        for pattern in follow_patterns:
            match = re.search(pattern, content)
            if match:
                return match.group(0)
        
        return None
    
    def _is_duplicate(self, item: DistilledItem, existing_items: List[DistilledItem]) -> bool:
        """检查是否重复"""
        for existing in existing_items:
            if (existing.item_type == item.item_type and 
                existing.content == item.content):
                return True
        return False
    
    def _extract_outcome(self, content: str, role: str) -> Optional[str]:
        """
        提取成果信息
        
        Args:
            content: 消息内容
            role: 角色（user/assistant）
            
        Returns:
            成果描述，如果无则返回 None
        """
        # 只有 assistant（Agent）才会产生实际成果
        if role != "assistant":
            return None
        
        # 检测文件路径
        file_paths = re.findall(r'[\~\/\w]+\.[\w]+', content)
        if file_paths:
            # 返回找到的文件路径
            return f"文件：{'、'.join(file_paths[:3])}"  # 最多3个
        
        # 检测 URL
        urls = re.findall(r'https?://[^\s\)\]"\'<>]+', content)
        if urls:
            return f"链接：{'、'.join(urls[:2])}"
        
        # 检测"完成"类关键词，说明有实际输出
        if any(kw in content for kw in ["已完成", "已完成", "搞定了", "完成", "创建了", "更新了"]):
            # 检查是否提到了具体内容
            if any(kw in content for kw in ["文档", "文件", "代码", "脚本", "规则", "配置"]):
                return "已输出到对话框或文件"
        
        return None
    
    def format_l1_entry(self, item: DistilledItem, line_number: int = 0, outcome: str = None) -> str:
        """
        格式化为 L1 存储格式
        
        Args:
            item: 蒸馏项
            line_number: 行号
            outcome: 成果（可选），可以是文件路径、URL 或对话框内容描述
            
        Returns:
            Markdown 格式的记忆条目
        """
        timestamp = datetime.now().strftime("%H:%M")
        
        lines = [
            f"## {timestamp}",
            f"### {item.item_type.capitalize()}",
            f"- **内容**：{item.content}",
        ]
        
        if item.emotion:
            lines.append(f"- **情绪**：{item.emotion}")
        
        # 新增：成果字段
        if outcome:
            lines.append(f"- **成果**：{outcome}")
        
        if item.follow_up:
            lines.append(f"- **后续行动**：{item.follow_up}")
        
        if item.tags:
            tag_str = " ".join([f"#{tag}" for tag in item.tags])
            lines.append(f"- **标签**：`{tag_str}`")
        
        # 添加来源信息
        date_str = datetime.now().strftime("%Y-%m-%d")
        lines.append(f"- **来源**：memory/{date_str}.md#L{line_number}")
        
        lines.append("")  # 空行分隔
        
        return "\n".join(lines)
