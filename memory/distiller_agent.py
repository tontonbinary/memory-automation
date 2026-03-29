#!/usr/bin/env python3
"""
Distiller Agent - 蒸馏模块
基于规则提取关键信息
"""

import re
from typing import List, Dict, Any


class DistillerAgent:
    """Agent 蒸馏器 - 无需 LLM API"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def distill(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Agent 自己处理蒸馏 - 无需 LLM API

        基于规则提取关键信息：
        - event: 完成/创建/修复/更新等动作
        - decision: 决定/选择/使用/设置为等
        - preference: 我喜欢/我想要/我希望等
        - emotion: 情绪表达
        - action: 后续行动/计划

        Args:
            messages: 消息列表

        Returns:
            蒸馏后的记忆项列表
        """
        distilled_items = []

        # 定义提取模式
        PATTERNS = {
            "event": [
                (r"(创建了|完成了|修复了|解决了|删除了|更新了|添加了|修改了|实现了|发布了|部署了|提交了|合并了|推送了)(.+?)(?:。|；|$)", "动作完成"),
                (r"(发现|遇到|出现)(.+?)(?:问题|错误|bug|异常)(?:。|；|$)", "发现问题"),
            ],
            "decision": [
                (r"(决定|确认|采用|选择|使用|设置为)(.+?)(?:。|；|$)", "做出决策"),
                (r"(不|没)(?:需要|要|准备|打算)(.+?)(?:。|；|$)", "否定决策"),
                (r"(同意|拒绝|接受|放弃)(.+?)(?:。|；|$)", "决策态度"),
            ],
            "preference": [
                (r"(我喜欢|我偏好|我想要|我希望|我倾向于|我更)(.+?)(?:。|；|$)", "表达偏好"),
                (r"(不喜欢|不想要|不希望)(.+?)(?:。|；|$)", "负面偏好"),
            ],
            "action": [
                (r"(下一步|接下来|之后|稍后|等会|明天|下周)(.+?)(?:。|；|$)", "后续行动"),
                (r"(记得|别忘了|注意|确保|检查)(.+?)(?:。|；|$)", "提醒事项"),
            ],
        }

        # 情绪关键词
        EMOTION_POSITIVE = ["太棒了", "很好", "不错", "完美", "优秀", "赞", "厉害", "感谢", "谢谢", "太好了"]
        EMOTION_NEGATIVE = ["着急", "焦虑", "担心", "困惑", "麻烦", "头痛", "糟糕", "错误", "失败", "烦"]

        for msg in messages:
            # content 可能是 list（富文本格式）或 string，需要统一处理
            raw_content = msg.get("content", "")
            if isinstance(raw_content, list):
                # 富文本格式：提取所有 text 字段
                content = " ".join(
                    item.get("text", "") for item in raw_content
                    if isinstance(item, dict) and item.get("type") == "text"
                )
            else:
                content = str(raw_content)
            content = content.strip()
            role = msg.get("role", "unknown")
            timestamp = msg.get("timestamp", "")
            msg_id = msg.get("msg_id", "")

            # 跳过短消息
            if len(content) < self.config.get("min_message_length", 10):
                continue

            # 只处理用户消息（agent 的消息通常是对用户请求的响应）
            if role != "user":
                continue

            # 尝试匹配各种模式
            for item_type, patterns in PATTERNS.items():
                for pattern, desc in patterns:
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for match in matches:
                        # 提取匹配内容
                        if len(match.groups()) >= 2:
                            distilled_content = match.group(1) + match.group(2)
                        else:
                            distilled_content = match.group(0)

                        # 限制内容长度
                        distilled_content = distilled_content[:200]

                        # 检测情绪
                        emotion = None
                        for word in EMOTION_POSITIVE:
                            if word in content:
                                emotion = "positive"
                                break
                        if not emotion:
                            for word in EMOTION_NEGATIVE:
                                if word in content:
                                    emotion = "negative"
                                    break

                        # 生成标签
                        tags = [item_type]
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

                        item = {
                            "item_type": item_type,
                            "content": distilled_content,
                            "emotion": emotion,
                            "follow_up": None,
                            "tags": tags,
                            "source_message": content[:300],
                            "outcome": None,
                            "timestamp": timestamp,
                            "msg_id": msg_id
                        }

                        # 去重检查
                        is_duplicate = False
                        for existing in distilled_items:
                            if existing["item_type"] == item["item_type"] and existing["content"] == item["content"]:
                                is_duplicate = True
                                break

                        if not is_duplicate:
                            distilled_items.append(item)

        return distilled_items
