"""
会话蒸馏模块 - 从消息中提取关键信息
支持 LLM 智能蒸馏 + 正则匹配降级
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import urllib.request
import urllib.error


@dataclass
class DistilledItem:
    """蒸馏后的记忆项（5类：Event, Preference, To-do, Output, Emotion）"""
    item_type: str  # Event, Decision, Preference, Improve, To-do, Output, Emotion
    content: str
    emotion: Optional[str] = None  # 积极|负面|null
    tags: List[str] = None
    action: Optional[str] = None  # 后续行动（对应 To-do 类型）
    oput: Optional[str] = None  # 成果（对应 Output 类型）
    improve: Optional[str] = None  # 用户纠正/改进
    source_idx: int = 0  # 原始消息序号（从1开始）
    source_message: str = ""
    timestamp: str = ""  # 原始 timestamp 字符串（如 "2026-03-29T20:04:22.758Z"）

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class SessionDistiller:
    """会话蒸馏器 - 提取消息中的关键信息"""

    # 提取模式定义(正则匹配,作为 LLM 失败时的降级方案)
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
            r"(太棒了|很好|不错|完美|优秀|赞|厉害)(?:!|。|$)",
            r"(感谢|谢谢|感激)(?:!|。|$)",
            r"(好的|明白|了解|清楚|知道了)(?:!|。|$)",
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

    # LLM 蒸馏 Prompt 模板(使用 str.replace 格式化,避免 { } 占位符冲突)
    DISTILLATION_PROMPT = """## 角色
Session Distiller - 将对话历史提炼为结构化记忆

## 5类事件类型

- **CoreWork**：本职核心业务（结合agent_types判断）
  - ["开发型","系统管理型"] → coding + 运维
  - ["服装商品AI助理"] → 服装销售/商品管理
  
- **EventsOutside**：临时辅助、无重要成果
  - "临时帮忙"、"简单支持"、"顺便"
  
- **SelfEvolve**：知识/纠错/习惯养成
  
- **SocialEcology**：用户和相关人类关系和组织/agent组织分工/人类工作生活环境的运行规律
  
- **RuleDecision**：硬性规则、流程、约束
  - "必须"、"禁止"、"规范"、"标准"

## 5类记忆类型

### 1. Event - 客观事实、问题、需求（包括踩坑）
- "发现bug"、"今日token消耗"、"货物已发出"

### 2. Preference - 用户偏好、习惯、忌讳
- "我喜欢整洁的文件夹"、"不要用红色"

### 3. To-do - 待办、承诺、需记住 / 遵守的事项
- "明天测试"、"记得改配置"、"下次记住了"

### 4. Output - 产出物
- "代码提交了"、"记在corrections.md"、"修改了多维表"

### 0. Emotion - 只记 积极/负面
- 积极：满意、开心
- 负面：烦躁、失望

## 参考内容使用指南

**Agent类型（agent_types）**
- 判断CoreWork：结合类型确定核心业务
- 影响内容标签：选用该领域专业词汇
  - 开发型 → #coding #架构
  - 服装助理 → #款式 #库存

**昨日标签**
- 避免相近标签不同表述重复提取
- 例：已有"写代码"，"写脚本"视为同类

**自定义标签**
- 用户特别要求关注的领域，优先提取

## LLM 自动分类判断逻辑

### 第一步：先定「事件类型」
只看这件事属于哪个场景，二选一、三选一，不纠结：
- 是我的本职工作（写代码、改配置、运维、商品管理）？→ CoreWork
- 只是临时帮忙、不重要的杂事、游戏放松？→ EventsOutside
- 是在学习知识、纠正错误、养成新习惯？→ SelfEvolve
- 涉及用户偏好、人际关系、分工方法、自然规律？→ SocialEcology
- 是硬性规定、必须 / 禁止、标准流程？→ RuleDecision

### 第二步：再定「记忆类型」
- 只看这条信息本身是什么性质，一个内容只贴一个主标签：
客观发生了什么、事实、路径、问题、踩坑？→ Event
- 用户喜欢 / 不喜欢、习惯、忌讳、风格？→ Preference
- 接下来要做、还没做的事？→ To-do
- 已经完成的产出、结果、文件、成果？→ Output
- 只记录情绪好坏，不记内容？→ Emotion

###第三步：组合规则（非常重要）
- 事件类型 = 这件事的场景
- 记忆标签 = 这条信息的类型
- 一条记忆 = 1 个事件类型 + 1 个主记忆标签
- 禁止一条记忆同时挂多个记忆标签
- Emotion 可以附加在任何标签上，但不能单独当主标签

## 绝不提取

- 操作型Meta对话：询问如何使用脚本/系统（如"怎么跑"、"这个怎么用"）

## 去重规则

- 重复项只提取最终项，标注重复次数（如"决定用Vue" *3次）

## 蒸馏三原则

1. **聚合多条消息**：相关/相似内容合并成一条记忆
   - 同一主题的对话优先聚合成一条记忆点
   - 同一件事情，1个记忆类型不够，才考虑形成第二条记忆
   - 多件事情，内容相似合并记忆
       
2. **内容 = 精华总结**：不是复述，而是提炼后的精华
   - ❌ 不好："用户说了很多关于API设计的事情，包括RESTful规范和认证方式..."
   - ✅ 正确："确定采用RESTful API + JWT认证方案"

3. **标签 = 核心主题**：不是"话题标签"，而是"这条记忆最重要的事"
   - ❌ 不好："#会议 #讨论 #代码"
   - ✅ 正确："#架构决策 #技术选型"

## 输出格式
```json
{
  "items": [{
    "event_type": "SocialEcology|CoreWork|...",
    "type": "Event|To-do|...",
    "content": "提炼内容",
    "emotion": "积极|负面|null",
    "tags": ["标签1", "标签2"],
    "source_idx": 1  // 消息序号，对应会话内容中 [1]、[2] 等方括号中的数字
  }]
}
```

__REFERENCE_CONTENT__

## 会话内容（JSON 格式）

__SESSION_CONTENT__

## 注意事项
1. 只提取真正值得记忆的内容，过滤闲聊、重复、临时信息
2. 内容要简洁具体，不要泛泛而谈
3. 每个提取项必须指定 type，不允许其他 type 值
4. **source_idx 必填**：必须是消息在会话中的序号（对应 `[1]`、`[2]` 等方括号中的数字）
5. 如果没有值得提取的内容，返回 {"items": []}
6. **必须**返回合法的 JSON 格式，不要添加 markdown 代码块标记
"""

    def __init__(self, min_message_length: int = 10, config_path: Optional[str] = None,
                 reference_manager=None):
        """
        初始化蒸馏器

        Args:
            min_message_length: 最小消息长度,短于此值的消息被忽略
            config_path: 配置文件路径(用于读取 LLM API 配置)
            reference_manager: ReferenceManager 实例,用于注入参考内容
        """
        self.min_message_length = min_message_length
        self.config = self._load_config(config_path)
        self.llm_config = self._get_llm_config()
        self.reference_manager = reference_manager

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

        if config_path:
            config_path = os.path.expanduser(config_path)
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
                print(f"[SessionDistiller] 加载配置失败,使用默认配置: {e}")

        return default_config

    def _get_llm_config(self) -> Dict[str, Any]:
        """获取 LLM 配置，自动从多个来源提取 API Key"""
        llm_config = self.config.get("llm", {})

        # 优先级 1: 环境变量
        api_key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("MINIMAX_API_TOKEN")
        
        # 优先级 2: 配置文件
        if not api_key and "api_key" in llm_config:
            api_key = llm_config["api_key"]
            if api_key and not api_key.startswith("YOUR_"):
                llm_config["api_key"] = api_key
                return llm_config
        
        # 优先级 3: 自动从 OpenClaw 配置提取
        if not api_key or api_key.startswith("YOUR_"):
            api_key = self._extract_openclaw_api_key()
        
        llm_config["api_key"] = api_key
        return llm_config
    
    def _extract_openclaw_api_key(self) -> Optional[str]:
        """从 OpenClaw 配置自动提取 API key"""
        try:
            home = Path.home()
            
            # 注意：禁止硬编码 agent 名称，只尝试通过配置文件或环境变量获取
            # 从 config.json 中读取 agent_id（如果配置中有）
            agent_id = self.config.get("agent_id") or os.environ.get("OPENCLAW_AGENT_ID")
            
            if agent_id:
                auth_file = home / ".openclaw" / "agents" / agent_id / "agent" / "auth-profiles.json"
                if auth_file.exists():
                    with open(auth_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    profiles = data.get("profiles", {})
                    
                    # 优先查找 minimax
                    for profile_name, profile in profiles.items():
                        if "minimax" in profile_name.lower():
                            token = profile.get("access") or profile.get("key")
                            if token:
                                print(f"[SessionDistiller] 已从 OpenClaw ({agent_id}/{profile_name}) 提取 API key")
                                return token
                    
                    # 其次查找任何 API key
                    for profile_name, profile in profiles.items():
                        token = profile.get("access") or profile.get("key")
                        if token and len(token) > 20:
                            print(f"[SessionDistiller] 已从 OpenClaw ({agent_id}/{profile_name}) 提取 API key")
                            return token
            
            # 尝试 openclaw.json
            openclaw_config = home / ".openclaw" / "openclaw.json"
            if openclaw_config.exists():
                with open(openclaw_config, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # 尝试各种可能的路径
                llm_config = data.get("llm", {})
                if isinstance(llm_config, dict):
                    api_key = llm_config.get("api_key") or llm_config.get("apiKey")
                    if api_key:
                        print("[SessionDistiller] 已从 openclaw.json 提取 API key")
                        return api_key
                        
        except Exception as e:
            print(f"[SessionDistiller] 自动提取 API key 失败: {e}")
        
        return None

    def _clean_content(self, content: str) -> str:
        """
        清洗消息内容,去除工具调用结果等噪声

        Args:
            content: 原始消息内容

        Returns:
            清洗后的内容
        """
        if not content:
            return ""

        # 去掉 [HH:MM] toolResult: <frozen runpy...> 格式
        content = re.sub(r'\[\d{2}:\d{2}\]\s*toolResult:\s*<[^>]+>', '', content)
        # 去掉 <frozen runpy> 等 Python 内部表示
        content = re.sub(r'<frozen \w+[^>]*>', '', content)
        # 去掉 Exec result: 日志块
        content = re.sub(r'Exec\s+result:.*?(?=\n\n|\n[A-Z]|$)', '', content, flags=re.DOTALL)
        # 去掉 Markdown 文件内容dump(# 文件名 Template、## 标题 等片段)
        content = re.sub(r'^#{1,3}\s+[^\n]*Template[^\n]*\n', '', content, flags=re.MULTILINE)
        # 去掉明显的工具输出片段(行首有 [HH:MM] toolResult: 或类似格式)
        content = re.sub(r'\n?\[\d{2}:\d{2}\]\s*toolResult:[^\n]*', '', content)
        # 去掉 JSON/dict dump(大量 key: value 格式的行)
        lines = content.split('\n')
        cleaned_lines = []
        for line in lines:
            # 跳过全是 "key: value" 格式的行(工具配置dump)
            if re.match(r'^\s*"[^"]+"\s*:\s*("[^"]*"|\[|' r'\{|\d+|true|false|null)', line):
                continue
            cleaned_lines.append(line)
        content = '\n'.join(cleaned_lines)
        
        # 去掉各种 untrusted metadata 块
        content = re.sub(r'Conversation info \(untrusted metadata\):\s*```json\s*\{[\s\S]*?\}\s*```', '', content)
        content = re.sub(r'Sender \(untrusted metadata\):\s*```json\s*\{[\s\S]*?\}\s*```', '', content)
        content = re.sub(r'Thread starter \(untrusted, for context\):\s*```json\s*\{[\s\S]*?\}\s*```', '', content)
        content = re.sub(r'Replied message \(untrusted, for context\):\s*```json\s*\{[\s\S]*?\}\s*```', '', content)
        content = re.sub(r'Forwarded message context \(untrusted metadata\):\s*```json\s*\{[\s\S]*?\}\s*```', '', content)
        content = re.sub(r'Chat history since last reply \(untrusted, for context\):\s*```json\s*[\s\S]*?```', '', content)
        
        # 去掉 [message_id: xxx] 行
        content = re.sub(r'\[message_id:[^\]]+\]\s*\n?', '', content)
        
        # 保留 sender ID 前缀（ou_xxx: 开头的行），为群聊 session 做准备
        
        # 去掉空 ```json 块
        content = re.sub(r'```json\s*\{[\s\S]*?\}\s*```', '', content)

        return content.strip()

    def _format_messages_for_prompt(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        将消息列表格式化为 prompt 可用的文本（带1-based序号）
        使用 parentId 链筛选，只保留用户消息和给用户的回复，过滤内部思考

        Returns:
            {"text": str, "timestamps": {idx: timestamp}}  # timestamps 的 key 是 1-based 序号
        """
        # 1. 构建 id→message 映射，用于 parentId 链追溯
        id_map = {msg.get('id'): msg for msg in messages if msg.get('id')}
        
        # 2. 判断消息是否是给用户看的（不是内部思考）
        def is_user_facing(msg: Dict[str, Any]) -> bool:
            role = msg.get('role', '')
            
            # user 消息全部保留
            if role == 'user':
                return True
            
            # toolResult 直接丢弃
            if role == 'toolResult':
                return False
            
            # system 消息直接丢弃（内部系统事件，无用户价值）
            if role == 'system':
                return False
            
            # assistant 消息需要追溯 parentId 链
            if role == 'assistant':
                current_id = msg.get('parentId')
                depth = 0
                max_depth = 10  # 防止无限循环
                
                while current_id and depth < max_depth:
                    parent = id_map.get(current_id)
                    if not parent:
                        break
                    
                    parent_role = parent.get('role', '')
                    
                    # 如果追溯到 user，说明是给用户的回复
                    if parent_role == 'user':
                        return True
                    
                    # 如果追溯到 toolResult，说明是内部思考
                    if parent_role == 'toolResult':
                        return False
                    
                    # 继续向上追溯
                    current_id = parent.get('parentId')
                    depth += 1
                
                # 默认保留（无法确定时保守处理）
                return True
            
            # 其他角色默认保留
            return True
        
        # 3. 过滤消息
        filtered_messages = [m for m in messages if is_user_facing(m)]
        
        # 4. 格式化消息
        formatted_lines = []
        timestamps = {}  # {1-based-idx: timestamp}
        msg_idx = 0

        for msg in filtered_messages:
            msg_idx += 1
            timestamp = msg.get("timestamp", "")
            timestamps[msg_idx] = timestamp  # 记录每个 idx 对应的 timestamp
            
            role = msg.get("role", "unknown")
            
            # content 可能是 list(富文本格式)或 string,需要统一处理
            raw_content = msg.get("content", "")
            if isinstance(raw_content, list):
                # kimi 方式：每块单独清洗后再连接（不用空格拆散metadata块）
                cleaned_parts = []
                for item in raw_content:
                    if isinstance(item, dict):
                        item_type = item.get("type")
                        
                        # 显式过滤：thinking/toolCall/toolResult 等内部处理内容全部丢弃
                        if item_type in ("thinking", "toolCall", "toolResult"):
                            continue
                        
                        if item_type == "text":
                            text = item.get("text", "")
                            if text:
                                cleaned = self._clean_content(text)
                                cleaned = cleaned.strip()
                                if cleaned:
                                    cleaned_parts.append(cleaned)
                        elif item_type == "image":
                            cleaned_parts.append("[图片]")
                        elif item_type == "audio":
                            cleaned_parts.append("[语音]")
                        # 其他类型默认丢弃
                content = "\n".join(cleaned_parts)
            else:
                content = str(raw_content)
                content = self._clean_content(content)
            content = content.strip()
            # 提取 sender ID（保留，为群聊 session 做准备）
            sender = msg.get("sender") or msg.get("sender_id")
            
            # 跳过空消息和短消息
            if len(content) < self.min_message_length:
                continue

            # 过滤纯 heartbeat 系统轮询消息
            # user 消息：内容以 "Read HEARTBEAT" 开头
            # assistant 消息：内容仅含 "HEARTBEAT_OK"（后面跟换行或无内容）
            if role == "user" and content.startswith("Read HEARTBEAT"):
                continue
            if role == "assistant":
                content_first_line = content.split("\n")[0].strip()
                if content_first_line == "HEARTBEAT_OK":
                    continue

            # 过滤 System Exec completed/failed 系统执行结果消息
            if role == "user" and content.startswith("System (untrusted):"):
                continue

            # 角色显示名称
            if role == "user":
                role_display = "用户"
            elif role == "assistant":
                role_display = "助手"
            else:
                role_display = role
            
            # 群聊时显示发送者
            sender_info = f"[{sender}] " if sender else ""

            # 格式化时间（用于显示）- 转换为系统本地时区
            time_str = ""
            if timestamp:
                try:
                    if isinstance(timestamp, str):
                        if len(timestamp) >= 10:
                            time_str = f"[{timestamp[11:16]}] " if 'T' in timestamp else f"[{timestamp}] "
                    elif isinstance(timestamp, (int, float)):
                        # Unix 时间戳（毫秒）→ 转为系统本地时区
                        import datetime
                        dt = datetime.datetime.fromtimestamp(timestamp / 1000)
                        time_str = f"[{dt.strftime('%Y-%m-%dT%H:%M:%S')}] "
                except:
                    pass

            formatted_lines.append(f"[{msg_idx}] {time_str}{role_display}: {sender_info}{content}")

        # 直接构建精简 JSON 格式
        messages_list = []
        for msg_item in filtered_messages:
            ts = msg_item.get("timestamp", "")
            role = msg_item.get("role", "unknown")
            sender = msg_item.get("sender") or msg_item.get("sender_id") or ""
            
            raw_content = msg_item.get("content", "")
            if isinstance(raw_content, list):
                parts = []
                for c in raw_content:
                    if isinstance(c, dict):
                        t = c.get("type")
                        if t == "text":
                            text = c.get("text", "")
                            if text:
                                cleaned = self._clean_content(text)
                                parts.append(cleaned.strip())
                        elif t == "image":
                            parts.append("[图片]")
                        elif t == "audio":
                            parts.append("[语音]")
                content = "\n".join(parts)
            else:
                content = self._clean_content(str(raw_content))
            
            if len(content) >= self.min_message_length:
                messages_list.append({
                    "r": role[:1],  # u=user, a=assistant
                    "s": sender,
                    "t": str(ts),
                    "c": content[:300]  # 截断
                })
        
        return {
            "text": "\n\n".join(formatted_lines),  # 兼容旧代码
            "json": messages_list,  # 精简 JSON 格式
            "timestamps": timestamps
        }

    def _call_minimax_api(self, prompt: str) -> Optional[str]:
        """
        调用 Minimax LLM API

        Args:
            prompt: 完整的 prompt 文本

        Returns:
            API 返回的文本内容,失败时返回 None
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
                {"role": "system", "content": "你是一个专业的会话分析助手,擅长提取关键信息并返回结构化数据。"},
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
                if result.get("choices") and len(result["choices"]) > 0:
                    msg = result["choices"][0].get("message", {})
                    # MiniMax-M2.7 使用 reasoning_content
                    content = msg.get("content") or msg.get("reasoning_content", "")
                    if content:
                        print(f"[SessionDistiller] >>> LLM RAW RESPONSE ({len(content)} chars):\n{content[:500]}")
                        return content
                    print(f"[SessionDistiller] 响应 message 为空: {msg}")
                    return None
                elif "data" in result and "choices" in result["data"]:
                    content = result["data"]["choices"][0].get("message", {}).get("content", "")
                    print(f"[SessionDistiller] >>> LLM RAW RESPONSE ({len(content)} chars):\n{content[:500]}")
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
            print("[SessionDistiller] LLM 响应为空")
            return []

        # 快速检测是否是被工具输出污染的响应（不是合法 JSON）
        response_preview = response.strip()[:100]
        # 用更精确的 pattern：工具输出的特征格式（行首时间戳 + toolResult:）
        if re.search(r'\[\d{2}:\d{2}\]\s*toolResult:', response):
            full = response.strip()[:2000]
            print(f"[SessionDistiller] ⚠️ LLM 响应疑似被工具输出污染:\n{full}")
            return []
        # 检查是否以工具输出片段开头（非 JSON）
        if response.strip().startswith(('[', '{')):
            pass  # 可能是正常 JSON，继续解析
        elif re.match(r'^[A-Za-z#]+', response.strip()) and '"items"' not in response[:200]:
            # 看起来像文本而不是 JSON
            full = response.strip()[:2000]
            print(f"[SessionDistiller] ⚠️ LLM 响应不像 JSON:\n{full}")
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

            print(f"[SessionDistiller] LLM 响应格式不符合预期: {str(data)[:200]}")
            return []

        except json.JSONDecodeError as e:
            # JSON 不完整（LLM 生成被截断），尝试抢救
            print(f"[SessionDistiller] JSON 解析不完整: {e}")
            # 打印完整响应（截断到 2000 字符方便调试）
            full_response = response.strip()[:2000]
            print(f"[SessionDistiller] >>> FULL LLM RESPONSE ON FAILURE:\n{full_response}")
            # 尝试从截断位置截断后手动提取 items
            items = self._try_recover_partial_json(response)
            if items:
                print(f"[SessionDistiller] 从截断响应中抢救到 {len(items)} 项")
                return items
            return []
        except Exception as e:
            print(f"[SessionDistiller] 解析 LLM 响应时出错: {e}")
            return []

    def _try_recover_partial_json(self, response: str) -> List[Dict[str, Any]]:
        """
        尝试从截断的 LLM 响应中抢救 items

        当 LLM 响应被截断导致 JSON 不完整时，尝试从中间提取合法的 items 数组

        Args:
            response: 可能截断的响应文本

        Returns:
            抢救到的 items 列表
        """
        # 尝试找到 "items": [ 或 "items":[{ 开始的部分
        match = re.search(r'"items"\s*:\s*\[', response)
        if not match:
            return []

        # 从 items 数组开始位置截取
        items_start = match.start()
        partial = response[items_start:]

        # 尝试补全并解析
        # 如果结尾不完整，尝试补上 ]}
        if not partial.strip().endswith(']') and not partial.strip().endswith(']}'):
            # 找到最后一个完整的 item 对象
            last_brace = partial.rfind('},')
            if last_brace > 0:
                partial = partial[:last_brace + 1] + ']}'
            else:
                # 找不到完整 item，返回空
                return []

        try:
            data = json.loads(partial)
            if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
                return data["items"]
        except json.JSONDecodeError:
            pass

        return []

    def distill_with_llm(self, messages: List[Dict[str, Any]],
                          pre_cleaned: bool = False) -> List[DistilledItem]:
        """
        使用 LLM 进行智能蒸馏

        Args:
            messages: 消息列表
            pre_cleaned: 消息是否已经过预清洗
                         - False（默认）：走 _format_messages_for_prompt 获取 json 和 timestamps
                         - True：messages 已经是清洗后的格式，reconstruct json + timestamps from messages

        Returns:
            蒸馏后的记忆项列表
        """
        if not self.llm_config.get("enabled", True):
            print("[SessionDistiller] LLM 蒸馏已禁用")
            return []

        if pre_cleaned:
            # messages 已经是清洗后的消息列表（role/sender/timestamp/content）
            # 重建 json 格式和 timestamps_map
            timestamps_map = {}  # {1-based-idx: timestamp}
            msg_list = []
            for idx, msg in enumerate(messages):
                idx_1based = idx + 1
                ts = msg.get("timestamp", "")
                timestamps_map[idx_1based] = ts
                role_map = {"user": "u", "assistant": "a"}
                msg_list.append({
                    "r": role_map.get(msg.get("role", ""), msg.get("role", "")[:1]),
                    "s": msg.get("sender", ""),
                    "t": ts,
                    "c": msg.get("content", "")[:300]  # 截断
                })
            session_json = json.dumps(msg_list, ensure_ascii=False)
            session_content = session_json
            print(f"[SessionDistiller] 预清洗模式: {len(messages)} 条消息直接给 LLM")
        else:
            # 格式化会话内容（原始流程）
            formatted = self._format_messages_for_prompt(messages)
            timestamps_map = formatted["timestamps"]  # {1-based-idx: timestamp}
            session_json = json.dumps(formatted["json"], ensure_ascii=False)
            session_content = session_json

        if not session_content or session_content == "null":
            print("[SessionDistiller] 没有足够的内容进行 LLM 蒸馏")
            return []

        # 构建 prompt
        reference_content = ""
        if self.reference_manager:
            reference_content = self.reference_manager.build_reference_content()

        prompt = self.DISTILLATION_PROMPT.replace("__REFERENCE_CONTENT__", reference_content)
        prompt = prompt.replace("__SESSION_CONTENT__", session_content)

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
        VALID_TYPES = {"Event", "Preference", "To-do", "Output", "Emotion"}
        for item_data in items_data:
            try:
                # 验证必要字段（支持 type 或 item_type）
                type_val = item_data.get("type") or item_data.get("item_type")
                if not type_val or "content" not in item_data:
                    continue

                # 确保 item_type 有效（不区分大小写，兼容旧类型和带连字符类型）
                item_type = type_val.strip()
                type_lower = item_type.lower()
                if type_lower == "to-do" or type_lower == "todo" or type_lower == "action":
                    item_type = "To-do"
                elif type_lower == "output" or type_lower == "oput":
                    item_type = "Output"
                elif type_lower in ["event", "decision", "preference", "improve", "emotion"]:
                    item_type = type_lower.capitalize()
                elif item_type not in VALID_TYPES:
                    item_type = "Event"  # 默认类型

                # 构建 DistilledItem（新格式5类）
                source_idx_raw = item_data.get("source_idx", 0)
                try:
                    source_idx = int(source_idx_raw) if source_idx_raw else 0
                except (ValueError, TypeError):
                    source_idx = 0

                # 从 timestamps_map 获取 timestamp（source_idx 是 1-based）
                if source_idx in timestamps_map:
                    item_timestamp = timestamps_map[source_idx]
                else:
                    item_timestamp = ""

                item = DistilledItem(
                    item_type=item_type,
                    content=item_data.get("content", ""),
                    emotion=item_data.get("emotion") if item_data.get("emotion") != "null" else None,
                    tags=item_data.get("tags", []),
                    action=item_data.get("action") if item_data.get("action") != "null" else None,
                    oput=item_data.get("oput") if item_data.get("oput") != "null" else None,
                    improve=item_data.get("improve") if item_data.get("improve") != "null" else None,
                    source_idx=source_idx,
                    source_message="",
                    timestamp=item_timestamp
                )

                # 去重检查
                if not self._is_duplicate(item, distilled_items):
                    distilled_items.append(item)

            except Exception as e:
                print(f"[SessionDistiller] 处理 LLM 返回项时出错: {e}")
                continue

        print(f"[SessionDistiller] LLM 蒸馏完成,提取 {len(distilled_items)} 项")
        return distilled_items

    def pre_clean_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        预清洗消息列表：在切块之前完成完整清洗

        流程：parentId 链过滤 + 富文本提取 + _clean_content
        确保返回的消息都是"干净"的、可直接给 LLM 的内容

        Args:
            messages: 原始消息列表

        Returns:
            清洗后的消息列表（不含短消息）
        """
        formatted = self._format_messages_for_prompt(messages)
        timestamps_map = formatted["timestamps"]

        # 从 formatted["json"] 重建清洗后的消息列表
        # formatted["json"] 每条格式: {"r": role, "s": sender, "t": timestamp, "c": content}
        cleaned_messages = []
        for msg_json in formatted["json"]:
            role = msg_json.get("r", "")
            sender = msg_json.get("s", "")
            timestamp = msg_json.get("t", "")
            content = msg_json.get("c", "")

            if len(content) < self.min_message_length:
                continue

            cleaned_messages.append({
                "role": role,
                "sender": sender,
                "timestamp": timestamp,
                "content": content
            })

        print(f"[SessionDistiller] 预清洗: {len(messages)} 条 -> {len(cleaned_messages)} 条")
        return cleaned_messages

    def distill_messages(self, messages: List[Dict[str, Any]], use_llm: bool = True,
                        pre_cleaned: bool = False) -> List[DistilledItem]:
        """
        从消息列表中蒸馏关键信息（仅使用 LLM，失败则返回空）

        Args:
            messages: 消息列表,每个消息为字典,包含 role 和 content
            use_llm: 是否使用 LLM 蒸馏(默认 True)
            pre_cleaned: 消息是否已经过预清洗

        Returns:
            蒸馏后的记忆项列表，LLM 失败时返回空列表
        """
        if not use_llm or not self.llm_config.get("enabled", True):
            print("[SessionDistiller] LLM 蒸馏已禁用")
            return []
        
        # 检查 API key 是否配置
        if not self.llm_config.get("api_key"):
            print("[MEMORY-AUTOMATION] API_ERROR: API_KEY_NOT_CONFIGURED")
            print("[SessionDistiller] 请先配置 LLM API key")
            return []
        
        try:
            llm_items = self.distill_with_llm(messages, pre_cleaned=pre_cleaned)
            if llm_items:
                return llm_items
            # LLM 返回空结果（无有效内容可提取）
            print("[SessionDistiller] LLM 未提取到有效内容")
            return []
        except Exception as e:
            error_msg = str(e)
            if "API_KEY" in error_msg or "API_ERROR" in error_msg:
                pass  # 已打印格式化错误
            elif "401" in error_msg or "403" in error_msg:
                print("[MEMORY-AUTOMATION] API_ERROR: API_KEY_INVALID")
            elif "429" in error_msg:
                print("[MEMORY-AUTOMATION] API_ERROR: API_RATE_LIMITED")
            elif "JSON" in error_msg or "Parse" in error_msg:
                print("[MEMORY-AUTOMATION] API_ERROR: API_RESPONSE_PARSE_ERROR")
            elif "Connection" in error_msg or "network" in error_msg.lower():
                print("[MEMORY-AUTOMATION] API_ERROR: API_CONNECTION_ERROR")
            else:
                print(f"[MEMORY-AUTOMATION] API_ERROR: {type(e).__name__}")
            print(f"[SessionDistiller] LLM 蒸馏失败: {e}")
            return []

    def _distill_with_regex(self, messages: List[Dict[str, Any]]) -> List[DistilledItem]:
        """
        使用正则表达式进行蒸馏(原始方法,作为 fallback)

        Args:
            messages: 消息列表

        Returns:
            蒸馏后的记忆项列表
        """
        distilled_items = []

        for idx, msg in enumerate(messages):
            # 获取消息时间戳
            msg_timestamp = msg.get("timestamp", "")
            # content 可能是 list(富文本格式)或 string,需要统一处理
            raw_content = msg.get("content", "")
            if isinstance(raw_content, list):
                content = " ".join(
                    item.get("text", "") for item in raw_content
                    if isinstance(item, dict) and item.get("type") == "text"
                )
            else:
                content = str(raw_content)
            # 清洗工具输出噪声
            content = self._clean_content(content)
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

                        # 查找后续行动(通常在消息后半部分)
                        action = self._extract_follow_up(content)

                        # 提取成果(文件路径、URL 或"已输出"描述)
                        oput = self._extract_outcome(content, role)

                        item = DistilledItem(
                            item_type=item_type,
                            content=distilled_content,
                            emotion=emotion,
                            tags=tags,
                            action=action,
                            oput=oput,
                            source_message=content[:200],
                            timestamp=msg_timestamp,
                            source_idx=idx + 1,  # 1-based index
                        )

                        # 去重检查
                        if not self._is_duplicate(item, distilled_items):
                            distilled_items.append(item)

        return distilled_items

    def _detect_emotion(self, content: str) -> Optional[str]:
        """检测情绪关键词"""
        for word in self.EMOTION_POSITIVE:
            if word in content:
                return "积极"
        for word in self.EMOTION_NEGATIVE:
            if word in content:
                return "负面"
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
            role: 角色(user/assistant)

        Returns:
            成果描述,如果无则返回 None
        """
        # 只有 assistant(Agent)才会产生实际成果
        if role != "assistant":
            return None

        # 检测文件路径
        file_paths = re.findall(r'[\~\/\w]+\.[\w]+', content)
        if file_paths:
            # 返回找到的文件路径
            return f"文件:{'、'.join(file_paths[:3])}"  # 最多3个

        # 检测 URL
        urls = re.findall(r'https?://[^\s\)\]"\'<>]+', content)
        if urls:
            return f"链接:{'、'.join(urls[:2])}"

        # 检测"完成"类关键词,说明有实际输出
        if any(kw in content for kw in ["已完成", "已完成", "搞定了", "完成", "创建了", "更新了"]):
            # 检查是否提到了具体内容
            if any(kw in content for kw in ["文档", "文件", "代码", "脚本", "规则", "配置"]):
                return "已输出到对话框或文件"

        return None

    def format_l1_entry(self, item: DistilledItem, line_number: int = 0,
                        entry_time: str = None, session_date: str = None) -> str:
        """
        格式化为 L1 存储格式

        Args:
            item: 蒸馏项
            line_number: 行号
            entry_time: 条目时间戳(HH:MM)，None则使用当前时间
            session_date: session 日期(YYYY-MM-DD)

        Returns:
            Markdown 格式的记忆条目
        """
        if entry_time is None:
            entry_time = datetime.now().strftime("%H:%M")

        lines = [
            f"## {entry_time}",
            f"### {item.item_type.capitalize()}",
            f"- **内容**：{item.content}",
        ]

        if item.emotion:
            lines.append(f"- **情绪**：{item.emotion}")

        if item.action:
            lines.append(f"- **后续行动**：{item.action}")

        if item.oput:
            lines.append(f"- **成果**：{item.oput}")

        if item.improve:
            lines.append(f"- **纠正**：{item.improve}")

        if item.tags:
            tag_str = " ".join([f"#{tag}" for tag in item.tags])
            lines.append(f"- **标签**：`{tag_str}`")

        # 来源信息
        if session_date is None:
            session_date = datetime.now().strftime("%Y-%m-%d")
        lines.append(f"- **来源**：session/{session_date[5:]}#L{line_number}")

        lines.append("")
        return "\n".join(lines)
