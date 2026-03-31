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
from .reference_manager import ReferenceManager


class MemoryAutomation:
    """记忆自动化主类"""

    def __init__(self, agent_id: Optional[str] = None, config_path: Optional[str] = None):
        """
        初始化自动化模块

        Args:
            agent_id: Agent ID（可选，未传入时自动检测）
            config_path: 配置文件路径（可选）
        """
        # 不自动 fallback，保留 None 表示未检测到
        self.agent_id = agent_id or self._detect_agent_id()
        self.config = self._load_config(config_path)

        # 初始化组件
        self.state_manager = StateManager(self.config.get("state_file", "memory/heartbeat-state.json"))

        # 初始化参考内容管理器（从 heartbeat-state.json 读取配置）
        self.reference_manager = ReferenceManager(agent_id=self.agent_id or "code")

        # 初始化新模块
        self.session_manager = SessionManager(
            agent_id=self.agent_id,
            state_manager=self.state_manager
        )
        self.l1_writer = L1Writer(
            agent_id=self.agent_id,
            config=self.config
        )

        # 从 heartbeat-state 读取 api_key 注入 distiller
        state = self.reference_manager._load_state()
        api_key = state.get("api_key", "")
        self.distiller = SessionDistiller(
            min_message_length=self.config.get("distillation", {}).get("min_message_length", 10),
            reference_manager=self.reference_manager
        )
        if api_key:
            self.distiller.llm_config["api_key"] = api_key

        self.message_processor = MessageProcessor(
            agent_id=self.agent_id,
            config=self.config,
            session_manager=self.session_manager,
            l1_writer=self.l1_writer,
            distiller=self.distiller,
            reference_manager=self.reference_manager
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
        # 检查 HOME 环境变量对应的 workspace
        try:
            home = Path.home()
            # 检查 ~/.openclaw/workspaces/{agent}/workspace/memory/ 是否存在（当前 agent 的 memory 目录）
            memory_base = home / ".openclaw" / "workspaces"
            if memory_base.exists():
                for agent_dir in memory_base.iterdir():
                    memory_dir = agent_dir / "workspace" / "memory"
                    if memory_dir.exists() and memory_dir.is_dir():
                        # 检查是否有最新的 pending_queue 或 session 文件
                        # 这个 agent 可能是当前的
                        pass
        except Exception:
            pass

        # 3. 从当前工作目录推断
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

        # 4. 从 HEARTBEAT 所在的 workspace 目录推断
        # heartbeat 运行时的 cwd 可能是 skill 目录
        # 但可以尝试从 HOME 推断
        try:
            home = Path.home()
            # 检查哪个 workspace 的 HEARTBEAT.md 最近被读取了
            # 或者直接检查所有 workspace 的 memory 目录的修改时间
            memory_base = home / ".openclaw" / "workspaces"
            latest_agent = None
            latest_time = 0
            for agent_dir in memory_base.iterdir():
                if agent_dir.is_dir():
                    memory_dir = agent_dir / "workspace" / "memory"
                    if memory_dir.exists():
                        # 检查 memory 目录的修改时间
                        mtime = memory_dir.stat().st_mtime
                        if mtime > latest_time:
                            latest_time = mtime
                            latest_agent = agent_dir.name
            if latest_agent:
                print(f"[MemoryAutomation] 从最近访问的 workspace/memory 获取 agent_id: {latest_agent}")
                return latest_agent
        except Exception:
            pass

        # 5. 无法检测，返回 None（不 fallback）
        print("[MemoryAutomation] 无法检测 agent_id")
        return None

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

    def _ensure_heartbeat_file(self) -> bool:
        """
        确保 heartbeat 文件存在于 agent workspace

        首次运行时自动创建，后续跳过。

        Returns:
            True if heartbeat file exists or was created, False on error
        """
        if not self.agent_id:
            return False

        heartbeat_path = Path.home() / ".openclaw" / "workspaces" / self.agent_id / "workspace" / "HEARTBEAT.md"

        # 如果已存在，跳过
        if heartbeat_path.exists():
            return True

        # 创建 heartbeat 文件
        heartbeat_content = f"""# HEARTBEAT.md

# Keep this file empty (or with only comments) to skip heartbeat API calls.

# Memory Automation - 自动将会话蒸馏到 L1 记忆层
cd ~/.openclaw/skills/memory-automation && python3 -m memory.automation heartbeat --agent {self.agent_id}
"""
        try:
            heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            heartbeat_path.write_text(heartbeat_content, encoding='utf-8')
            print(f"[MemoryAutomation] ✅ Heartbeat 文件已创建: {heartbeat_path}")
            return True
        except Exception as e:
            print(f"[MemoryAutomation] ⚠️ 无法创建 heartbeat 文件: {e}")
            return False

    def _check_config_status(self) -> Dict[str, Any]:
        """
        检查配置状态，返回是否就绪或 awaiting_confirmation

        Returns:
            {"ready": bool, "fallback": bool, "status": str, ...}
        """
        is_complete, missing = self.reference_manager.is_complete()
        if is_complete:
            return {"ready": True, "fallback": False}

        # 检查是否已接受降级
        state = self.reference_manager._load_state()
        if state.get("fallback_accepted"):
            return {"ready": True, "fallback": True}

        missing_str = ", ".join(missing)
        return {
            "ready": False,
            "fallback": False,
            "status": "awaiting_confirmation",
            "config_status": self.reference_manager.get_config_status(),
            "message": f"配置不完整（缺失: {missing_str}），蒸馏质量将下降，是否继续？"
        }

    def write_activation_flag(self, message: str = "Mauto 需要激活，请运行 'mauto activate' 或让用户触发一次 Mauto") -> Path:
        """
        写入激活标记文件，供 agent 检测并通知用户

        Args:
            message: 激活提示信息
        """
        if not self.agent_id:
            return None

        flag_dir = Path.home() / ".openclaw" / "workspaces" / self.agent_id / "workspace" / "memory"
        flag_dir.mkdir(parents=True, exist_ok=True)
        flag_path = flag_dir / ".mauto_activation_needed"

        with open(flag_path, 'w', encoding='utf-8') as f:
            f.write(f"{message}\n")
            f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        print(f"[MemoryAutomation] 激活标记已写入: {flag_path}")
        return flag_path

    def clear_activation_flag(self) -> bool:
        """清除激活标记"""
        if not self.agent_id:
            return False

        flag_path = Path.home() / ".openclaw" / "workspaces" / self.agent_id / "workspace" / "memory" / ".mauto_activation_needed"
        if flag_path.exists():
            flag_path.unlink()
            return True
        return False

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

    def _process_session_file(self, session_file: str) -> Dict[str, Any]:
        """
        处理指定的 session 文件

        Args:
            session_file: session 文件的绝对路径

        Returns:
            处理结果
        """
        import json as json_module

        result = {
            "triggered": False,
            "reason": "",
            "items_distilled": 0,
            "lines_written": 0,
            "pattern_detected": None,
            "session_key": session_file
        }

        if not os.path.exists(session_file):
            result["reason"] = f"session 文件不存在: {session_file}"
            return result

        # 读取 session 文件
        try:
            messages = []
            with open(session_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json_module.loads(line)
                        if entry.get("type") == "message":
                            msg_data = entry.get("message", {})
                            content = msg_data.get("content", "")
                            role = msg_data.get("role", "")
                            if role in ["user", "assistant"] and content:
                                # 处理富文本格式
                                if isinstance(content, list):
                                    text = " ".join(
                                        item.get("text", "") for item in content
                                        if isinstance(item, dict) and item.get("type") == "text"
                                    )
                                else:
                                    text = str(content)
                                if text.strip():
                                    messages.append({
                                        "role": role,
                                        "content": text.strip(),
                                        "msg_id": entry.get("id", ""),
                                        "timestamp": entry.get("timestamp")
                                    })
                    except json_module.JSONDecodeError:
                        continue
        except Exception as e:
            result["reason"] = f"读取 session 文件失败: {e}"
            return result

        if not messages:
            result["reason"] = "session 文件中没有有效消息"
            return result

        print(f"[MemoryAutomation] 从 session 文件读取 {len(messages)} 条消息")

        # 蒸馏消息
        lines_written, items, _ = self.process_session(messages, force=True)

        result["triggered"] = True
        result["reason"] = f"处理 session 文件: {os.path.basename(session_file)}"
        result["items_distilled"] = len(items)
        result["lines_written"] = lines_written

        return result

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

    def run_manual(self, user_message: Optional[str] = None, session_file: Optional[str] = None) -> Dict[str, Any]:
        """
        手动触发入口

        Args:
            user_message: 用户消息（用于检查关键词）
            session_file: 指定要处理的 session 文件路径（绝对路径）

        Returns:
            处理结果
        """
        # 无 agent_id → 报错提示
        if not self.agent_id:
            detected = self._detect_agent_id()
            result = {
                "triggered": False,
                "reason": f"agent_id 未指定，请在调用时加 --agent 参数（例如 --agent {detected or 'your_agent_id'}）",
                "items_distilled": 0,
                "lines_written": 0,
                "error": "agent_id_required"
            }
            print(f"[MemoryAutomation] 错误: agent_id 未指定")
            print(f"[MemoryAutomation] 请在调用时加 --agent 参数")
            return result

        result = {
            "triggered": False,
            "reason": "",
            "items_distilled": 0,
            "lines_written": 0,
            "pattern_detected": None  # 实时模式检测结果
        }

        # 配置检查（新模式：等待确认）
        config_status = self._check_config_status()
        if not config_status["ready"]:
            result["status"] = "awaiting_confirmation"
            result["config_status"] = config_status["config_status"]
            result["reason"] = config_status["message"]
            return result

        # 如果接受降级，关闭 LLM 蒸馏
        if config_status.get("fallback"):
            print("[MemoryAutomation] 配置不完整，使用 regex 降级蒸馏")
            self.distiller.llm_config["enabled"] = False

        # 如果指定了 session_file，直接处理该文件
        if session_file:
            print(f"[MemoryAutomation] 处理指定 session 文件: {session_file}")
            return self._process_session_file(session_file)

        # 首先检查是否触发实时模式检测
        if user_message:
            pattern_result = self.detect_pattern_realtime(user_message)
            if pattern_result:
                # 输出格式化的提示
                output = f"\n🔔 检测到重复模式：{pattern_result['tag']}\n   历史出现 {pattern_result['count']} 次，要提升为 L2 吗？"
                print(output)
                result["pattern_detected"] = pattern_result
                # 模式检测不阻断正常触发，继续执行

        # 检查关键词触发（如果有 session_file 参数则跳过关键词检查）
        if session_file:
            # 直接处理指定的 session 文件
            return self._process_session_file(session_file)

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

        # 切块处理：避免单次 Prompt 过长
        # 每块处理完后更新状态，确保进度不丢失
        total_lines = 0
        total_items = 0
        chunks = self.session_manager.get_session_chunks(max_messages_per_chunk=200)

        for chunk_idx, (chunk_messages, chunk_last_msg_id) in enumerate(chunks):
            print(f"[Heartbeat] 处理块 {chunk_idx+1}/{len(chunks)}, {len(chunk_messages)} 条消息")
            lines_written, items, final_msg_id = self.process_session(chunk_messages, force=True)
            total_lines += lines_written
            total_items += len(items)

            # 每块处理完后立即更新状态
            self.state_manager.update_after_process(session_key, len(items), chunk_last_msg_id)

        result.update({
            "triggered": True,
            "reason": "手动触发成功",
            "items_distilled": total_items,
            "lines_written": total_lines,
            "session_key": session_key,
            "chunks_processed": len(chunks)
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

        无 agent_id 时：
        - 写入激活标记，跳过主逻辑
        - 由 agent 通知用户激活

        Returns:
            处理结果
        """
        # 无 agent_id → 跳过执行，写入激活标记
        if not self.agent_id:
            result = {
                "triggered": False,
                "reason": "agent_id 未指定，跳过执行",
                "pending_count": 0,
                "activation_needed": True
            }
            print("[MemoryAutomation] Heartbeat 触发但无 agent_id，写入激活标记")
            self.write_activation_flag()
            return result

        result = {
            "triggered": False,
            "reason": "",
            "pending_count": 0,
            "queue_file": None,
            "old_session_processed": False,
            "old_session_items": 0
        }

        # 首次运行检查：确保 heartbeat 文件存在
        self._ensure_heartbeat_file()

        # 配置检查（新模式：等待确认）
        config_status = self._check_config_status()
        if not config_status["ready"]:
            result["status"] = "awaiting_confirmation"
            result["config_status"] = config_status["config_status"]
            result["reason"] = config_status["message"]
            return result

        # 如果接受降级，关闭 LLM 蒸馏
        if config_status.get("fallback"):
            print("[MemoryAutomation] 配置不完整，使用 regex 降级蒸馏")
            self.distiller.llm_config["enabled"] = False

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
        print("用法: python -m memory.automation [manual|heartbeat|old-session] [--agent <agent_id>] [--session <session_file>]")
        print("  manual    - 手动触发记忆蒸馏")
        print("  heartbeat - Heartbeat 触发记忆蒸馏")
        print("  old-session <key> - 处理已 reset 的旧 session")
        print("  --agent <id> - 指定 agent ID（必需）")
        print("  --session <file> - 指定要处理的 session 文件（绝对路径）")
        print("  示例: python -m memory.automation manual --agent code")
        print("  示例: python -m memory.automation heartbeat --agent xiaoxian")
        print("  示例: python -m memory.automation old-session 'agent:xiaoxian:feishu:direct:ou_xxx' --agent code")
        sys.exit(1)

    mode = sys.argv[1].lower()

    # 解析可选参数
    session_file = None
    agent_id = None
    for i in range(2, len(sys.argv)):
        if sys.argv[i] == "--session" and i + 1 < len(sys.argv):
            session_file = sys.argv[i + 1]
        elif sys.argv[i] == "--agent" and i + 1 < len(sys.argv):
            agent_id = sys.argv[i + 1]

    # 创建自动化实例
    automation = MemoryAutomation(agent_id=agent_id)

    if mode == "manual":
        # 手动模式 - 可以尝试从环境变量获取用户消息
        user_message = os.environ.get("USER_MESSAGE", "")
        result = automation.run_manual(user_message, session_file=session_file)

        print(f"\n[结果] {result['reason']}")
        if result.get('error') == 'agent_id_required':
            print(f"[错误] 请在调用时添加 --agent 参数")
            sys.exit(1)
        if result['triggered']:
            print(f"  - 蒸馏项: {result['items_distilled']}")
            print(f"  - 写入行: {result['lines_written']}")
            if result.get('session_key'):
                print(f"  - Session: {result['session_key']}")

    elif mode == "old-session":
        # 处理已 reset 的旧 session
        if len(sys.argv) < 3:
            print("用法: python -m memory.automation old-session <session_key> [--agent <agent_id>]")
            print("  session_key - 要处理的旧 session key")
            print("  示例: python -m memory.automation old-session 'agent:xiaoxian:feishu:direct:ou_xxx'")
            sys.exit(1)
        old_session_key = sys.argv[2]
        print(f"[MemoryAutomation] 处理旧 session: {old_session_key}")
        result = automation.process_old_session(old_session_key)
        print(f"\n[结果] 蒸馏项: {result[0]}, items: {len(result[1]) if result[1] else 0}")

    elif mode == "heartbeat":
        # Heartbeat 模式 - 只读取新消息，写入队列，不蒸馏
        result = automation.run_heartbeat()

        # 输出结果（Agent 会解析这个输出）
        if result.get('activation_needed'):
            print(f"\n[MemoryAutomation] {result['reason']}")
            print(f"[MemoryAutomation] 请在 HEARTBEAT.md 中添加 --agent 参数")
        elif result['triggered'] and result['pending_count'] > 0:
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
