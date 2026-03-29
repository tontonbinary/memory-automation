#!/usr/bin/env python3
"""
Memory Automation - 主逻辑模块
处理手动触发和 Heartbeat 触发的记忆蒸馏

用法:
    python -m memory.automation manual     # 手动触发
    python -m memory.automation heartbeat  # Heartbeat 触发
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from .state_manager import StateManager
from .session_manager import SessionManager
from .message_processor import MessageProcessor
from .pattern_detector import PatternDetector
from .session_distiller import SessionDistiller
from .l1_writer import L1Writer


class MemoryAutomation:
    """记忆自动化主类"""

    def __init__(self, agent_id: Optional[str] = None, config_path: Optional[str] = None):
        """
        初始化自动化模块

        Args:
            agent_id: Agent ID（可选，未传入时自动检测）
            config_path: 配置文件路径（可选）
        """
        self.agent_id = agent_id or self._detect_agent_id()
        self.config = self._load_config(config_path)

        # 初始化组件
        self.state_manager = StateManager(self.config.get("state_file", "memory/heartbeat-state.json"))

        # 初始化新模块
        self.session_manager = SessionManager(
            agent_id=self.agent_id,
            state_manager=self.state_manager
        )
        self.l1_writer = L1Writer(
            agent_id=self.agent_id,
            config=self.config
        )
        self.distiller = SessionDistiller(
            min_message_length=self.config.get("distillation", {}).get("min_message_length", 10)
        )
        self.message_processor = MessageProcessor(
            agent_id=self.agent_id,
            config=self.config,
            session_manager=self.session_manager,
            l1_writer=self.l1_writer,
            distiller=self.distiller
        )
        self.pattern_detector = PatternDetector(
            agent_id=self.agent_id,
            config=self.config
        )

        # 确保 L1 目录存在
        self._ensure_l1_directory()

    def _detect_agent_id(self) -> str:
        """
        自动检测当前 agent_id

        优先级：环境变量 > workspace 路径推断 > config 默认 > fallback "code"

        Returns:
            检测到的 agent_id
        """
        # 1. 检查环境变量
        env_agent = os.environ.get("OPENCLAW_AGENT_ID")
        if env_agent:
            print(f"[MemoryAutomation] 从环境变量获取 agent_id: {env_agent}")
            return env_agent

        # 2. 从 workspace 路径推断
        try:
            cwd = os.getcwd()
            # 匹配路径模式: ~/.openclaw/workspaces/{agent}/workspace/
            match = re.search(r'\.openclaw[/\\]workspaces[/\\]([^/\\]+)[/\\]workspace', cwd)
            if match:
                detected = match.group(1)
                print(f"[MemoryAutomation] 从 workspace 路径获取 agent_id: {detected}")
                return detected
        except Exception:
            pass

        # 3. 从 OpenClaw 配置读取默认 agent
        try:
            config_file = Path("~/.openclaw/config.json").expanduser()
            if config_file.exists():
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    default_agent = config.get("defaultAgent") or config.get("agent")
                    if default_agent:
                        print(f"[MemoryAutomation] 从 config 获取 agent_id: {default_agent}")
                        return default_agent
        except Exception:
            pass

        # 4. fallback 默认值
        print("[MemoryAutomation] 使用默认 agent_id: code")
        return "code"

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """加载配置"""
        # 默认配置
        default_config = {
            "trigger_keywords": ["记住", "记忆", "distill", "distillation"],
            # 实时模式检测关键词：当用户说这些时触发模式检测
            "pattern_keywords": ["我喜欢", "我希望", "我觉得", "以后都", "我想要", "忘了吗"],
            "heartbeat_interval_minutes": 30,
            "state_file": "memory/heartbeat-state.json",
            "memory_rules": "~/.openclaw/memory-rules.md",
            "min_message_length": 10,
            # L1 历史搜索配置
            "l1_history_days": 7,  # 搜索最近7天的历史
            "pattern_threshold": 3,  # 出现次数阈值
        }

        # 尝试加载配置文件
        if config_path:
            config_file = Path(config_path).expanduser()
        else:
            # 默认配置文件位置
            skill_dir = Path(__file__).parent.parent
            config_file = skill_dir / "config.json"

        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    default_config.update(loaded)
                    # 合并 paths 配置
                    if "paths" in loaded:
                        for key, value in loaded["paths"].items():
                            default_config[key] = value
            except (json.JSONDecodeError, IOError) as e:
                print(f"[MemoryAutomation] 加载配置失败，使用默认配置: {e}")

        return default_config

    def _save_config(self) -> None:
        """保存配置到文件"""
        skill_dir = Path(__file__).parent.parent
        config_file = skill_dir / "config.json"
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"[MemoryAutomation] 保存配置失败: {e}")

    def _get_l1_path(self) -> Path:
        """获取当前 L1 文件路径（委托给 l1_writer）"""
        return self.l1_writer._get_l1_path()

    def _ensure_l1_directory(self) -> None:
        """确保 L1 存储目录存在"""
        l1_path = self._get_l1_path()
        l1_path.parent.mkdir(parents=True, exist_ok=True)

    # === 委托给 session_manager ===

    def get_current_session(self) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
        """
        获取当前会话信息，只返回上次处理后新增的消息

        Returns:
            (session_key, messages, last_msg_id)
        """
        return self.session_manager.get_current_session()

    def _get_sessions_dir(self) -> Path:
        """获取当前 agent 的 sessions 目录"""
        return self.session_manager._get_sessions_dir()

    def find_old_session_files(self, old_session_key: str) -> List[Path]:
        """查找旧 session 的文件"""
        return self.session_manager.find_old_session_files(old_session_key)

    def _read_messages_from_session_file(self, session_file: Path,
                                          after_msg_id: Optional[str] = None
                                          ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """从 session 文件中读取消息"""
        return self.session_manager._read_messages_from_session_file(session_file, after_msg_id)

    # === 委托给 pattern_detector ===

    def _get_l1_history_files(self) -> List[Path]:
        """获取 L1 历史文件列表"""
        return self.pattern_detector._get_l1_history_files()

    def _extract_keywords_from_message(self, user_message: str) -> List[str]:
        """从用户消息中提取关键内容"""
        return self.pattern_detector._extract_keywords_from_message(user_message)

    def detect_pattern_realtime(self, user_message: str) -> Optional[Dict[str, Any]]:
        """
        实时检测用户偏好/行为模式

        当用户表达偏好时，搜索 L1 历史中是否已有相同标签 ≥3 次

        Args:
            user_message: 用户消息

        Returns:
            检测结果字典，无模式时返回 None
            {
                "tag": str,  # 检测到的标签
                "count": int,  # 历史出现次数
                "suggestion": str  # 建议信息
            }
        """
        return self.pattern_detector.detect_pattern_realtime(user_message)

    # === 委托给 distiller ===

    def distill_by_agent(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Agent 自己处理蒸馏 - 无需 LLM API

        Args:
            messages: 消息列表

        Returns:
            蒸馏后的记忆项列表
        """
        return self.distiller.distill(messages)

    # === 委托给 message_processor ===

    def process_session(self, messages: List[Dict[str, Any]],
                       force: bool = False) -> Tuple[int, List[Dict[str, Any]], Optional[str]]:
        """
        处理会话消息，蒸馏并写入 L1

        Args:
            messages: 消息列表
            force: 是否强制处理（忽略状态检查）

        Returns:
            (写入行数, 蒸馏项列表, 最后消息ID)
        """
        return self.message_processor.process_session(messages, force=force)

    def process_old_session(self, old_session_key: str,
                           last_processed_msg_id: Optional[str] = None) -> Tuple[int, List[Dict[str, Any]]]:
        """
        处理旧 session 中未蒸馏的消息

        Args:
            old_session_key: 旧 session 的 session_key
            last_processed_msg_id: 上次处理到的消息ID

        Returns:
            (distilled_count, items)
        """
        return self.message_processor.process_old_session(old_session_key, last_processed_msg_id)

    # === 委托给 l1_writer ===

    def _write_to_l1(self, items: List[Dict[str, Any]]) -> int:
        """写入 L1 存储文件（两段式格式）"""
        return self.l1_writer.write(items)

    def _format_l1_entry(self, item: Dict[str, Any], line_number: int = 0) -> str:
        """格式化为 L1 存储格式"""
        return self.l1_writer._format_l1_entry(item, line_number)

    def _write_pending_queue(self, messages: List[Dict[str, Any]]) -> Path:
        """将新消息写入待处理队列文件"""
        return self.l1_writer.write_pending_queue(messages)

    # === 自动化逻辑 ===

    def check_manual_trigger(self, user_message: str) -> bool:
        """
        检查是否触发手动记忆

        Args:
            user_message: 用户消息

        Returns:
            是否触发
        """
        keywords = self.config.get("trigger_keywords",
            ["记住", "记忆", "distill", "distillation"])

        message_lower = user_message.lower()
        for keyword in keywords:
            if keyword.lower() in message_lower:
                return True

        return False

    def run_manual(self, user_message: Optional[str] = None) -> Dict[str, Any]:
        """
        手动触发入口

        Args:
            user_message: 用户消息（用于检查关键词）

        Returns:
            处理结果
        """
        result = {
            "triggered": False,
            "reason": "",
            "items_distilled": 0,
            "lines_written": 0,
            "pattern_detected": None  # 实时模式检测结果
        }

        # 首先检查是否触发实时模式检测
        if user_message:
            pattern_result = self.detect_pattern_realtime(user_message)
            if pattern_result:
                # 输出格式化的提示
                output = f"\n🔔 检测到重复模式：{pattern_result['tag']}\n   历史出现 {pattern_result['count']} 次，要提升为 L2 吗？"
                print(output)
                result["pattern_detected"] = pattern_result
                # 模式检测不阻断正常触发，继续执行

        # 检查关键词触发
        if user_message and not self.check_manual_trigger(user_message):
            result["reason"] = "未匹配触发关键词"
            return result

        # ===== Session 切换处理 =====
        # 检查是否需要先处理旧 session 的未蒸馏消息
        current_session_key, _, _ = self.get_current_session()
        if current_session_key:
            last_session_info = self.state_manager.get_last_session_info()
            old_session_key = last_session_info.get("last_session_key")
            old_last_msg_id = last_session_info.get("last_processed_msg_id")

            if old_session_key and old_session_key != current_session_key:
                # 检查是否正在处理这个旧 session（防止重复处理）
                if self.state_manager.is_old_session_processing(old_session_key):
                    print(f"[MemoryAutomation] [Manual] 旧 session 正在处理中，跳过: {old_session_key}")
                else:
                    print(f"[MemoryAutomation] [Manual] 检测到 session 切换: {old_session_key} -> {current_session_key}")
                    print(f"[MemoryAutomation] [Manual] 先处理旧 session 的未蒸馏消息...")
                    
                    # 标记开始处理
                    self.state_manager.mark_old_session_processing(old_session_key)
                    
                    old_items_count, _ = self.process_old_session(
                        old_session_key, old_last_msg_id
                    )
                    
                    # 处理完成，取消标记
                    self.state_manager.unmark_old_session_processing()

                    result["old_session_processed"] = True
                    result["old_session_items"] = old_items_count
        # ===== Session 切换处理结束 =====

        # 获取当前会话（只获取新消息）
        session_key, messages, last_msg_id = self.get_current_session()

        if not session_key:
            result["reason"] = "无法获取当前会话"
            return result

        if not messages:
            result["reason"] = "没有新消息需要处理"
            # 仍然更新状态，避免重复检查
            self.state_manager.update_after_process(session_key, 0, last_msg_id)
            return result

        # ===== API Key 检查 =====
        llm_config = self.config.get("llm", {})
        api_key = llm_config.get("api_key")
        api_key_asked = llm_config.get("api_key_asked", False)

        if not api_key and not api_key_asked:
            # 首次询问用户关于 API key
            print("\n[MEMORY-AUTOMATION] API_KEY: not_configured")
            print("memory-automation 需要配置以下信息：")
            print("1. API key（从哪里获取？）")
            print("2. 供应商（默认 minimax）")
            print("3. 模型（默认 MiniMax-M2.7）")
            print("如暂不提供，将使用 regex 蒸馏（效果较差）。")
            # 更新状态
            self.config["llm"]["api_key_asked"] = True
            self._save_config()

        # 处理会话
        lines_written, items, final_msg_id = self.process_session(messages, force=True)

        # ===== Regex 计数检查 =====
        regex_config = self.config.get("regex", {})
        regex_count = regex_config.get("count", 0)
        regex_count_asked = regex_config.get("count_asked", False)

        # 更新 regex 计数（每次 regex 蒸馏都计数）
        self.config["regex"]["count"] = regex_count + 1
        regex_count = regex_count + 1

        # 检查是否达到询问阈值
        if regex_count >= 30 and not regex_count_asked:
            print("\n[MEMORY-AUTOMATION] REGEX_LIMIT_REACHED")
            print("你已经使用 regex 蒸馏 30 次了，效果如何？")
            print("是否要：")
            print("1）提供 API key 升级到 LLM 蒸馏")
            print("2）提供更好的蒸馏关键词/标签")
            self.config["regex"]["count_asked"] = True

        if regex_count >= 30 or regex_count_asked:
            self.config["regex"]["count"] = 0  # 重置计数

        self._save_config()

        # 使用最后处理的消息ID更新状态
        update_msg_id = final_msg_id or last_msg_id
        self.state_manager.update_after_process(session_key, len(items), update_msg_id)

        result.update({
            "triggered": True,
            "reason": "手动触发成功",
            "items_distilled": len(items),
            "lines_written": lines_written,
            "session_key": session_key
        })

        return result

    def run_heartbeat(self) -> Dict[str, Any]:
        """
        Heartbeat 触发入口

        架构：
        1. Heartbeat 读取新消息 → 写入 pending_queue
        2. 打印提示 → Agent 在自己上下文蒸馏
        3. 关键词触发 → 同样流程

        Session 切换处理：
        - 检测到 session_key 变化时，先处理旧 session 的未蒸馏消息
        - 避免因 session 切换导致消息遗漏

        Returns:
            处理结果
        """
        result = {
            "triggered": False,
            "reason": "",
            "pending_count": 0,
            "queue_file": None,
            "old_session_processed": False,
            "old_session_items": 0
        }

        # 获取当前会话（只获取新消息）
        session_key, messages, last_msg_id = self.get_current_session()

        if not session_key:
            result["reason"] = "无法获取当前会话"
            return result

        # 检查是否需要处理
        interval = self.config.get("heartbeat_interval_minutes", 30)
        should_process, reason = self.state_manager.check_should_process(
            session_key, interval
        )

        # ===== Session 切换处理 =====
        # 如果是 session_key 变化，先处理旧 session 的未蒸馏消息
        if reason and "session_key 变化" in reason:
            old_session_info = self.state_manager.get_last_session_info()
            old_session_key = old_session_info.get("last_session_key")
            old_last_msg_id = old_session_info.get("last_processed_msg_id")

            if old_session_key and old_session_key != session_key:
                # 检查是否正在处理这个旧 session（防止重复处理）
                if self.state_manager.is_old_session_processing(old_session_key):
                    print(f"[MemoryAutomation] [Heartbeat] 旧 session 正在处理中，跳过: {old_session_key}")
                else:
                    print(f"[MemoryAutomation] [Heartbeat] 检测到 session 切换: {old_session_key} -> {session_key}")
                    print(f"[MemoryAutomation] [Heartbeat] 先处理旧 session 的未蒸馏消息...")
                    
                    # 标记开始处理
                    self.state_manager.mark_old_session_processing(old_session_key)
                    
                    # 处理旧 session
                    old_items_count, old_items = self.process_old_session(
                        old_session_key, old_last_msg_id
                    )
                    
                    # 处理完成，取消标记
                    self.state_manager.unmark_old_session_processing()

                    result["old_session_processed"] = True
                    result["old_session_items"] = old_items_count

                    if old_items_count > 0:
                        print(f"[MemoryAutomation] [Heartbeat] 旧 session 处理完成: {old_items_count} 项已蒸馏")
                    else:
                        print(f"[MemoryAutomation] [Heartbeat] 旧 session 无遗漏消息或已全部处理")
        # ===== Session 切换处理结束 =====

        if not should_process:
            result["reason"] = f"无需处理: {reason}"
            return result

        print(f"[MemoryAutomation] {reason}")

        if not messages:
            result["reason"] = "没有新消息"
            self.state_manager.update_after_process(session_key, 0, last_msg_id)
            return result

        # 写入 pending_queue，让 Agent 自己蒸馏
        queue_path = self._write_pending_queue(messages)

        update_msg_id = last_msg_id or (messages[-1].get("msg_id") if messages else None)
        self.state_manager.update_after_process(session_key, 0, update_msg_id)

        result.update({
            "triggered": True,
            "reason": f"发现 {len(messages)} 条新消息待蒸馏",
            "pending_count": len(messages),
            "queue_file": str(queue_path),
            "session_key": session_key
        })

        # Agent 会在自己的上下文看到这条消息并执行蒸馏
        print(f"\n[MEMORY] 发现 {len(messages)} 条新消息待蒸馏，Agent 请执行记忆蒸馏")

        return result


def main():
    """主入口函数"""
    if len(sys.argv) < 2:
        print("用法: python -m memory.automation [manual|heartbeat]")
        print("  manual    - 手动触发记忆蒸馏")
        print("  heartbeat - Heartbeat 触发记忆蒸馏")
        sys.exit(1)

    mode = sys.argv[1].lower()

    # 创建自动化实例（agent_id 会自动检测）
    automation = MemoryAutomation()

    if mode == "manual":
        # 手动模式 - 可以尝试从环境变量获取用户消息
        user_message = os.environ.get("USER_MESSAGE", "")
        result = automation.run_manual(user_message)

        print(f"\n[结果] {result['reason']}")
        if result['triggered']:
            print(f"  - 蒸馏项: {result['items_distilled']}")
            print(f"  - 写入行: {result['lines_written']}")

    elif mode == "heartbeat":
        # Heartbeat 模式 - 只读取新消息，写入队列，不蒸馏
        result = automation.run_heartbeat()

        # 输出结果（Agent 会解析这个输出）
        if result['triggered'] and result['pending_count'] > 0:
            print(f"\n[MemoryAutomation] 发现 {result['pending_count']} 条新消息待蒸馏")
            print(f"请检查 memory/pending_queue.json 并进行 LLM 蒸馏")
        else:
            print(f"\n[结果] {result['reason']}")
    else:
        print(f"错误: 未知模式 '{mode}'")
        print("用法: python -m memory.automation [manual|heartbeat]")
        sys.exit(1)

    # 输出 JSON 结果（供调用方解析）
    print("\n" + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
