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

from .session_manager import SessionManager
from .message_processor import MessageProcessor
from .pattern_detector import PatternDetector
from .session_distiller import SessionCleaner
from .l1_writer import L1Writer
from .l1_reader import L1Reader, L1Data
from .reference_manager import ReferenceManager
from .processed_sessions_tracker import ProcessedSessionsTracker
from .file_logger import FileLogger
from .setup_checker import run_setup


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

        # 初始化参考内容管理器（从 heartbeat-state.json 读取配置）
        # 注意：agent_id 必须在初始化时明确指定，不允许 fallback
        if not self.agent_id:
            raise ValueError("agent_id 是必需的，请通过 --agent 参数指定")
        self.reference_manager = ReferenceManager(agent_id=self.agent_id)

        # 初始化 session_manager（合并了 state_manager 功能）
        # 状态文件必须按 agent 隔离，使用 SessionManager 的默认路径
        self.session_manager = SessionManager(
            agent_id=self.agent_id
        )
        self.l1_writer = L1Writer(
            agent_id=self.agent_id,
            config=self.config
        )

        # 初始化消息清洗器
        self.cleaner = SessionCleaner(
            min_message_length=self.config.get("min_message_length", 10)
        )

        self.message_processor = MessageProcessor(
            agent_id=self.agent_id,
            config=self.config,
            session_manager=self.session_manager,
            cleaner=self.cleaner
        )
        self.pattern_detector = PatternDetector(
            agent_id=self.agent_id,
            config=self.config
        )

        # 初始化文件日志器
        self.logger = FileLogger(agent_id=self.agent_id)

        # 确保 L1 目录存在
        self._ensure_l1_directory()

    def _detect_agent_id(self) -> Optional[str]:
        """
        自动检测当前 agent_id

        优先级：环境变量 > workspace 路径推断 > 最近访问的 workspace

        Returns:
            检测到的 agent_id，如果无法检测则返回 None（不 fallback 到默认值）
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
        heartbeat_content = f"""## memory-automation
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
        检查配置状态（简化版 - 不再检查 API key）
        """
        return {
            "ready": True,
            "status": "ready",
            "message": "配置就绪（无需 API key）"
        }



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

    def _generate_summary(self, saved_count: int, paths: List[Path]) -> str:
        """
        生成处理完成的摘要信息（简化版）
        
        Args:
            saved_count: 保存的 clean_session 块数
            paths: clean_session 文件路径列表
            
        Returns:
            格式化的摘要字符串
        """
        if not paths:
            return ""
        
        lines = []
        lines.append("\n" + "="*50)
        lines.append("📋 Clean Session 保存完成")
        lines.append("="*50)
        lines.append(f"\n✓ 共保存 {saved_count} 个 clean_session 文件")
        
        lines.append("\n【文件位置】")
        for path in paths:
            lines.append(f"  📁 {path}")
        
        lines.append("\n" + "="*50)
        
        return "\n".join(lines)

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
            "saved_count": 0,
            "saved_paths": [],
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
                            # 包含 user/assistant/toolResult（toolResult 用于 parentId 链追溯）
                            if role in ["user", "assistant", "toolResult"]:
                                # 处理富文本格式
                                if isinstance(content, list):
                                    text = " ".join(
                                        item.get("text", "") for item in content
                                        if isinstance(item, dict) and item.get("type") == "text"
                                    )
                                else:
                                    text = str(content) if content else ""
                                if text.strip() or role == "toolResult":
                                    messages.append({
                                        "role": role,
                                        "content": text.strip() if text.strip() else "[toolResult]",
                                        "id": entry.get("id", ""),
                                        "parentId": entry.get("parentId", ""),
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

        # 保存消息
        saved_count, paths = self.process_session(messages, force=True)

        result["triggered"] = True
        result["reason"] = f"处理 session 文件: {os.path.basename(session_file)}"
        result["saved_count"] = saved_count
        result["paths"] = [str(p) for p in paths]
        
        # 生成摘要
        if paths:
            summary = self._generate_summary(saved_count, paths)
            result["summary"] = summary
            print(summary)

        return result

    # === 委托给 message_processor ===

    def process_session(self, messages: List[Dict[str, Any]],
                       force: bool = False) -> Tuple[int, List[Path]]:
        """
        处理会话消息，保存 clean_session

        Returns:
            (保存块数, clean_session 路径列表)
        """
        return self.message_processor.process_session(messages)

    def process_old_session(self, old_session_key: str,
                           last_processed_msg_id: Optional[str] = None) -> Tuple[int, List[Path]]:
        """
        处理旧 session 中未保存的消息

        Returns:
            (保存块数, clean_session 路径列表)
        """
        return self.message_processor.process_old_session(old_session_key, last_processed_msg_id)

    # === 委托给 l1_writer ===

    def _write_to_l1(self, items: List[Dict[str, Any]]) -> int:
        """写入 L1 存储文件（两段式格式）"""
        return self.l1_writer.write(items)

    def _format_l1_entry(self, item: Dict[str, Any], line_number: int = 0) -> str:
        """格式化为 L1 存储格式"""
        return self.l1_writer._format_l1_entry(item, line_number)

    def _auto_check_setup(self, result: Dict) -> None:
        """
        配置自检 — heartbeat 末尾自动检查 cron 是否就绪

        每天检查一次，未就绪则输出提醒。agent 看到提醒后可自行创建 cron job。
        不修改系统配置，只检查+输出。
        """
        if not self.agent_id:
            return

        from datetime import datetime

        # 读取 state，看今天是否已检查过
        state = self.session_manager._load_state()
        last_check = state.get("last_setup_check", "")
        today = datetime.now().strftime("%Y-%m-%d")
        if last_check == today:
            return

        # 执行 cron 检查
        from .setup_checker import SetupChecker
        checker = SetupChecker(self.agent_id)
        cron_result = checker.check_cron_job()

        if cron_result["status"] == "pass":
            state["last_setup_check"] = today
            self.session_manager._save_state(state)
            return

        # cron 未配置 → 输出提醒给 agent
        print("\n" + "!" * 50)
        print(f"⚠️ [Mauto 配置自检] agent '{self.agent_id}' 缺少凌晨蒸馏 cron job")
        print(f"   如需凌晨 L1 蒸馏，请在 3:00-4:00 时间段内选一个分钟级创建 cron job：")
        print(f"   openclaw cron add --name {self.agent_id}-l1-distill \\")
        print(f"       --cron '分 时 * * *' \\")
        print(f"       --agent {self.agent_id} \\")
        print(f"       --session isolated \\")
        print(f"       --light-context \\")
        print(f"       --message '现在是凌晨，请检查前一天的clean_session是否已写入L1。'")
        print(f"   示例：--cron '0 3 * * *' = 每天 3:00，--cron '30 3 * * *' = 每天 3:30")
        print("!" * 50 + "\n")

        result["setup_reminder"] = True
        state["last_setup_check"] = today
        self.session_manager._save_state(state)

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
        # 静默时段检查（简化 - 不再依赖 l3_consolidation）
        from datetime import datetime
        now = datetime.now()
        silent_hours = self.config.get("silent_hours", {})
        
        if silent_hours.get("enabled", False):
            sh_start_hour = silent_hours.get("start_hour", 3)
            sh_start_minute = silent_hours.get("start_minute", 55)
            sh_end_hour = silent_hours.get("end_hour", 4)
            sh_end_minute = silent_hours.get("end_minute", 10)
            
            current_minutes = now.hour * 60 + now.minute
            silent_start = sh_start_hour * 60 + sh_start_minute
            silent_end = sh_end_hour * 60 + sh_end_minute
            
            if silent_start <= current_minutes <= silent_end:
                return {
                    "triggered": False,
                    "reason": f"当前处于静默时段（{sh_start_hour:02d}:{sh_start_minute:02d}-{sh_end_hour:02d}:{sh_end_minute:02d}），建议稍后再试"
                }

        # 无 agent_id → 报错提示
        if not self.agent_id:
            detected = self._detect_agent_id()
            result = {
                "triggered": False,
                "reason": f"agent_id 未指定，请在调用时加 --agent 参数（例如 --agent {detected or 'your_agent_id'}）",
                "saved_count": 0,
                "saved_paths": [],
                "error": "agent_id_required"
            }
            print(f"[MemoryAutomation] 错误: agent_id 未指定")
            print(f"[MemoryAutomation] 请在调用时加 --agent 参数")
            return result

        result = {
            "triggered": False,
            "reason": "",
            "saved_count": 0,
            "saved_paths": [],
            "pattern_detected": None  # 实时模式检测结果
        }

        # 配置检查
        config_status = self._check_config_status()
        if not config_status["ready"]:
            result["status"] = "api_key_required"
            result["config_status"] = config_status["config_status"]
            result["reason"] = config_status["message"]
            return result
        
        print(f"[MemoryAutomation] {config_status['message']}")

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

        if user_message and not self.check_manual_trigger(user_message):
            result["reason"] = "未匹配触发关键词"
            return result

        # ===== Session 切换处理 =====
        # 检查是否需要先处理旧 session 的未保存消息
        current_session_key, _, _ = self.get_current_session()
        if current_session_key:
            last_state = self.session_manager._load_state()
            old_session_key = last_state.get("last_session_key")
            old_last_msg_id = last_state.get("last_processed_msg_id")

            if old_session_key and old_session_key != current_session_key:
                print(f"[MemoryAutomation] [Manual] 检测到 session 切换: {old_session_key} -> {current_session_key}")
                print(f"[MemoryAutomation] [Manual] 先处理旧 session 的未保存消息...")

                old_saved_count, old_paths = self.process_old_session(
                    old_session_key, old_last_msg_id
                )

                result["old_session_processed"] = True
                result["old_session_saved"] = old_saved_count
                
                # 生成并打印旧 session 摘要
                if old_paths:
                    old_summary = self._generate_summary(old_saved_count, old_paths)
                    print("\n【旧 Session 处理结果】")
                    print(old_summary)
        # ===== Session 切换处理结束 =====

        # 获取当前会话（只获取新消息）
        session_key, messages, last_msg_id = self.get_current_session()

        if not session_key:
            result["reason"] = "无法获取当前会话"
            return result

        if not messages:
            result["reason"] = "没有新消息需要处理"
            # 更新状态，避免重复检查
            self.session_manager.update_last(session_key, last_msg_id, 0)
            return result

        # 读取后立即标记（保存进度）
        self.session_manager.update_last(session_key, last_msg_id, len(messages))

        # 保存 clean_session
        saved_count, paths = self.message_processor.process_session(messages, force=True)

        # 检查处理结果
        if saved_count == 0:
            result.update({
                "triggered": False,
                "reason": "clean_session 保存完成（无有效消息）",
                "saved_count": 0,
                "saved_paths": [],
                "session_key": session_key
            })
        else:
            result.update({
                "triggered": True,
                "reason": "clean_session 保存完成",
                "saved_count": saved_count,
                "saved_paths": [str(p) for p in paths],
                "session_key": session_key
            })
            
            # 生成并打印摘要
            summary = self._generate_summary(saved_count, paths)
            result["summary"] = summary
            print(summary)

        return result

    def _check_daily_summary(self) -> Optional[str]:
        """
        检查前一日 L1 是否需要补写（安全网）

        次日后任意时间运行，检查规则：
        - 昨天 clean_session 缺失 → 无对话，跳过
        - 昨天 L1 已存在 → 已蒸馏，跳过
        - 有 clean_session + 缺 L1 → 返回提醒消息

        Returns:
            提醒消息，或 None（不需要提醒）
        """
        from datetime import datetime, timedelta

        now = datetime.now()
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

        # 检查前一天 clean_session 是否存在
        clean_dir_str = self.config.get("output", {}).get("clean_session_dir",
            f"~/.openclaw/agents/{self.agent_id}/clean_session")
        clean_dir = Path(clean_dir_str).expanduser()
        yesterday_clean_file = clean_dir / f"{yesterday}.json"
        if not yesterday_clean_file.exists():
            return None  # 昨天没对话，静默跳过

        # 检查前一天 L1 是否存在且有内容
        l1_path = self.l1_writer._get_l1_path(yesterday)
        if l1_path.exists():
            try:
                content = l1_path.read_text(encoding='utf-8')
                if len(content.strip()) > 50:
                    return None  # L1 已写，跳过
            except:
                pass

        # 有 clean_session 但缺 L1 → 提醒 agent 补写
        msg = f"""📅 [次日蒸馏提醒] {yesterday} L1 未生成
clean_session 已存在：{yesterday_clean_file}
目标 L1 文件：{l1_path}

请读取 clean_session，提取记忆条目，然后调用 L1Writer.write() 写入。

格式要求：
- 每个条目包含：event_type（分类）、content（内容）
- 分类用：CoreWork / EventsOutside / SocialEcology / SelfEvolve / RuleDecision / To-do / Output
- 示例：entries = [{{'event_type': 'CoreWork', 'content': '...'}}, ...]
- 增量写入，不覆盖已有内容

完成后输出【蒸馏完成】"""
        return msg


    def _check_session_inactivity(self) -> Optional[str]:
        """
        检查 session 是否超过指定时间无活动
        
        Returns:
            需要 reset 的提示消息，或 None
        """
        inactivity_minutes = self.config.get("session_inactivity_minutes", 30)
        
        # 获取当前 session 的最后消息时间
        session_key, messages, _ = self.get_current_session()
        if not messages:
            return None
        
        # 找到最后一条消息的时间
        last_msg_time = None
        for msg in reversed(messages):
            ts = msg.get('timestamp', '')
            if ts:
                try:
                    ts_clean = ts.replace('Z', '+00:00')
                    last_msg_time = datetime.fromisoformat(ts_clean)
                    break
                except:
                    pass
        
        if not last_msg_time:
            return None
        
        # 检查是否超过 inactivity 时间
        now = datetime.now(last_msg_time.tzinfo)
        diff_minutes = (now - last_msg_time).total_seconds() / 60
        
        if diff_minutes >= inactivity_minutes:
            return f"检测到 {diff_minutes:.0f} 分钟无活动，需要 reset session"
        
        return None

    def _reset_current_session(self) -> bool:
        """
        Reset 当前 session
        
        1. 保存当前 session 的 clean_session
        2. 重命名 session 文件为 .reset.*
        3. 清空状态，下次会创建新 session
        
        Returns:
            是否成功 reset
        """
        session_key, messages, _ = self.get_current_session()
        if not session_key:
            print(f"[MemoryAutomation] [Reset] 无法获取当前 session")
            return False
        
        # 先保存当前 session 的 clean_session
        if messages:
            print(f"[MemoryAutomation] [Reset] 先保存当前 session 的 clean_session")
            self.message_processor.process_session(messages, force=True)
        
        # 找到 session 文件并重命名
        sessions_dir = Path(f"~/.openclaw/agents/{self.agent_id}/sessions").expanduser()
        
        # 查找当前 session 对应的文件
        session_id = session_key.split(':')[-1] if ':' in session_key else session_key
        
        for session_file in sessions_dir.glob(f"{session_id}.jsonl*"):
            if session_file.is_file():
                # 重命名为 .reset.{timestamp}
                timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
                new_name = f"{session_file.name}.reset.{timestamp}"
                new_path = session_file.parent / new_name
                session_file.rename(new_path)
                print(f"[MemoryAutomation] [Reset] 重命名: {session_file.name} -> {new_name}")
        
        # 清空状态
        state = self.session_manager._load_state()
        state["last_session_key"] = None
        state["last_processed_msg_id"] = None
        self.session_manager._save_state(state)
        print(f"[MemoryAutomation] [Reset] 状态已清空，下次 heartbeat 会创建新 session")
        
        return True

    def run_heartbeat(self) -> Dict[str, Any]:
        """
        Heartbeat 触发入口

        流程：
        1. Session 切换处理（保存旧 session clean_session）
        2. 积压处理
        3. 凌晨总结提醒（03:00-04:00，提醒总结前一日）
        4. 活跃 session 处理（保存当前 session clean_session）
        """
        # 静默时段检查（简化 - 不再依赖 l3_consolidation）
        from datetime import datetime
        now = datetime.now()
        silent_hours = self.config.get("silent_hours", {})
        
        if silent_hours.get("enabled", False):
            sh_start_hour = silent_hours.get("start_hour", 3)
            sh_start_minute = silent_hours.get("start_minute", 55)
            sh_end_hour = silent_hours.get("end_hour", 4)
            sh_end_minute = silent_hours.get("end_minute", 10)
            
            current_minutes = now.hour * 60 + now.minute
            silent_start = sh_start_hour * 60 + sh_start_minute
            silent_end = sh_end_hour * 60 + sh_end_minute
            
            if silent_start <= current_minutes <= silent_end:
                return {
                    "triggered": False,
                    "reason": f"当前处于静默时段（{sh_start_hour:02d}:{sh_start_minute:02d}-{sh_end_hour:02d}:{sh_end_minute:02d}），建议稍后再试"
                }

        # 无 agent_id → 跳过执行
        if not self.agent_id:
            result = {
                "triggered": False,
                "reason": "agent_id 未指定，跳过执行",
                "pending_count": 0
            }
            print("[MemoryAutomation] Heartbeat 触发但无 agent_id，跳过执行")
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

        # 配置检查（简化 - 不再需要 API key）
        config_status = self._check_config_status()
        if not config_status["ready"]:
            result["status"] = "config_required"
            result["reason"] = config_status["message"]
            return result
        
        print(f"[MemoryAutomation] {config_status['message']}")

        # ===== 第零步贰：配置自检（每天一次，独立于 session 处理）=====
        self._auto_check_setup(result)

        # 获取当前会话（只获取新消息）
        session_key, messages, last_msg_id = self.get_current_session()

        if not session_key:
            result["reason"] = "无法获取当前会话"
            return result

        # ===== 第零步：Session 无活动检查（超过 30 分钟无活动则 reset）=====
        inactivity_msg = self._check_session_inactivity()
        if inactivity_msg:
            print(f"[MemoryAutomation] [Heartbeat] {inactivity_msg}")
            if self._reset_current_session():
                result["session_reset"] = True
                result["reason"] = "Session 已 reset，跳过本次处理"
                # Reset 后重新获取 session
                session_key, messages, last_msg_id = self.get_current_session()
                if not session_key or not messages:
                    return result

        # ===== 第一步：Session 切换处理（无条件执行）=====
        state = self.session_manager._load_state()
        last_session = state.get("last_session_key")
        last_msg = state.get("last_processed_msg_id")
        
        if last_session and last_session != session_key:
            print(f"[MemoryAutomation] [Heartbeat] 检测到 session 切换: {last_session} -> {session_key}")
            print(f"[MemoryAutomation] [Heartbeat] 先处理旧 session 的未保存消息...")

            old_saved_count, old_paths = self.process_old_session(last_session, last_msg)
            result["old_session_processed"] = True
            result["old_session_saved"] = old_saved_count
            
            if old_paths and old_saved_count > 0:
                print(f"[MemoryAutomation] [Heartbeat] 旧 session 处理完成: {old_saved_count} 个文件")
                old_summary = self._generate_summary(old_saved_count, old_paths)
                print("\n【旧 Session 处理结果】")
                print(old_summary)
            else:
                print(f"[MemoryAutomation] [Heartbeat] 旧 session 无遗漏消息或已全部处理")
        
        # ===== 第二步：积压处理（当前 session 无消息时）=====
        if not messages:
            print("[MemoryAutomation] [Heartbeat] 活跃 session 无新消息，检查积压...")
            backlog_result = self._check_and_process_backlog()
            if backlog_result:
                result["backlog_processed"] = backlog_result
            
            # 检查前一日 L1 是否需要补写（安全网）
            daily_summary = self._check_daily_summary()
            if daily_summary:
                print(daily_summary)
                result["daily_summary"] = daily_summary
                result["needs_attention"] = True
        
        # ===== 第三步：检查活跃 session 处理间隔 =====
        interval = self.config.get("heartbeat_interval_minutes", 360)
        should_process, reason = self.session_manager.check_should_process(
            session_key, interval
        )
        
        if not should_process:
            result["reason"] = f"间隔时间未到: {reason}"
            if result.get("backlog_processed"):
                result["reason"] += "（但已检查积压）"
            if result.get("old_session_processed"):
                result["reason"] += "（已处理旧 session）"
            return result

        print(f"[MemoryAutomation] {reason}")

        if not messages:
            result["reason"] = "没有新消息"
            self.session_manager.update_last(session_key, last_msg_id, 0)
            return result

        # 读取后立即标记
        update_msg_id = last_msg_id or (messages[-1].get("id") if messages else None)
        self.session_manager.update_last(session_key, update_msg_id, len(messages))

        # 保存 clean_session（不再蒸馏）
        saved_count, paths = self.message_processor.process_session(messages, force=True)

        # 检查结果
        if saved_count == 0:
            result.update({
                "triggered": False,
                "reason": "Heartbeat 处理完成，但未保存 clean_session",
                "pending_count": 0,
                "saved_count": 0,
                "session_key": session_key,
                "needs_attention": True
            })
        else:
            result.update({
                "triggered": True,
                "reason": f"Heartbeat 处理完成",
                "pending_count": 0,
                "saved_count": saved_count,
                "session_key": session_key
            })
            
            # 生成摘要
            if paths:
                summary = self._generate_summary(saved_count, paths)
                result["summary"] = summary
                print(summary)

        return result

    def run_process_backlog(self, max_sessions: int = 1, force: bool = False) -> Dict[str, Any]:
        """
        处理积压的历史 session
        
        策略：
        1. 扫描 sessions 目录
        2. 筛选未处理且符合策略的 session
        3. 逐个处理
        
        Args:
            max_sessions: 本次最多处理几个 session（默认 1，避免一次处理太多）
            force: 是否忽略时间/大小限制强制处理
        
        Returns:
            处理结果
        """
        result = {
            "processed": [],
            "skipped": [],
            "errors": [],
            "total_found": 0
        }
        
        if not self.agent_id:
            result["errors"].append("agent_id 未指定")
            return result
        
        # 检查配置
        config_status = self._check_config_status()
        if not config_status["ready"]:
            result["errors"].append(f"配置未就绪: {config_status['message']}")
            return result
        
        # 获取策略配置
        backlog_config = self.config.get("session_processing", {})
        policy = {
            "max_age_days": backlog_config.get("max_age_days", 3),
            "min_message_count": backlog_config.get("min_message_count", 50),
            "process_order": backlog_config.get("process_order", "newest_first")
        }
        
        if force:
            # 强制模式：放宽限制
            policy["max_age_days"] = 365  # 一年
            policy["min_message_count"] = 1  # 任何大小
        
        # 初始化 tracker
        tracker = ProcessedSessionsTracker(self.agent_id, self.config)
        
        # 获取 sessions 目录
        sessions_dir = self.session_manager._get_sessions_dir()
        
        print(f"[MemoryAutomation] [Backlog] 扫描目录: {sessions_dir}")
        print(f"[MemoryAutomation] [Backlog] 策略: 最大{policy['max_age_days']}天, 最少{policy['min_message_count']}条消息")
        
        # 获取未处理的 session
        unprocessed = tracker.get_unprocessed_sessions(sessions_dir)
        result["total_found"] = len(unprocessed)
        
        print(f"[MemoryAutomation] [Backlog] 发现 {len(unprocessed)} 个未处理文件")
        
        if not unprocessed:
            print("[MemoryAutomation] [Backlog] 没有需要处理的 session")
            return result
        
        # 应用策略筛选
        filtered = tracker.filter_sessions_by_policy(unprocessed, policy)
        
        # 处理应该跳过的
        for file_path, file_info, decision in filtered:
            if decision != "process":
                session_key = str(file_path)
                skip_reason = {
                    "skip_too_old": "文件太旧",
                    "skip_too_small": "消息太少",
                    "skip_other": "其他原因"
                }.get(decision, "未知原因")
                
                tracker.mark_skipped(session_key, file_path, skip_reason, file_info)
                result["skipped"].append({
                    "file": str(file_path),
                    "reason": skip_reason,
                    "lines": file_info.get("line_count", 0)
                })
                print(f"[MemoryAutomation] [Backlog] 跳过: {file_path.name} ({skip_reason})")
        
        # 处理应该处理的
        processed_count = 0
        for file_path, file_info, decision in filtered:
            if decision != "process":
                continue
            
            if processed_count >= max_sessions:
                print(f"[MemoryAutomation] [Backlog] 已达到最大处理数量 ({max_sessions})，剩余待下次处理")
                break
            
            session_key = str(file_path)
            print(f"[MemoryAutomation] [Backlog] 处理: {file_path.name} ({file_info.get('line_count', 0)} 条消息)")
            
            try:
                # 调用 process_session_file 处理
                process_result = self._process_session_file(file_path)
                
                if process_result.get("triggered"):
                    tracker.mark_processed(
                        session_key, 
                        file_path,
                        process_result.get("saved_count", 0),
                        process_result.get("saved_count", 0)
                    )
                    result["processed"].append({
                        "file": str(file_path),
                        "saved_count": process_result.get("saved_count", 0),
                        "saved_paths": process_result.get("paths", [])
                    })
                    processed_count += 1
                    print(f"[MemoryAutomation] [Backlog] ✓ 完成: {process_result.get('saved_count', 0)} 个文件")
                else:
                    error_msg = process_result.get("reason", "未知错误")
                    tracker.mark_skipped(session_key, file_path, f"处理失败: {error_msg}")
                    result["errors"].append({
                        "file": str(file_path),
                        "error": error_msg
                    })
                    
            except Exception as e:
                tracker.mark_skipped(session_key, file_path, f"异常: {str(e)}")
                result["errors"].append({
                    "file": str(file_path),
                    "error": str(e)
                })
                print(f"[MemoryAutomation] [Backlog] ✗ 错误: {e}")
        
        # 输出统计
        stats = tracker.get_stats()
        print(f"[MemoryAutomation] [Backlog] 统计: 已处理 {stats['processed_count']}, 已跳过 {stats['skipped_count']}")
        
        return result

    def _check_and_process_backlog(self) -> Dict[str, Any]:
        """
        Heartbeat 中检查并处理积压 session（处理 1 个）
        
        Returns:
            处理结果，如果没有处理则返回空 dict
        """
        # 检查配置是否启用
        backlog_config = self.config.get("session_processing", {})
        if not backlog_config.get("process_inactive", True):
            return {}
        
        # 只在活跃 session 没有新消息时处理积压
        # 这里直接调用 run_process_backlog 处理 1 个
        return self.run_process_backlog(max_sessions=1, force=False)


def _handle_distill_l1(automation: MemoryAutomation, date_str: Optional[str] = None) -> Dict:
    """
    distill-l1 命令：输出昨日 clean_session 的结构化内容供 agent 写 L1

    流程：
    1. 默认昨天，支持 --date 指定
    2. 检查 clean_session 是否存在 → 缺则静默退出
    3. 检查 L1 是否已写 → 已写则跳过
    4. 输出 clean_session 内容 + 分类模板
    """
    from datetime import datetime, timedelta

    if not date_str:
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    agent_id = automation.agent_id

    # 检查 clean_session 是否存在
    clean_dir_str = automation.config.get("output", {}).get("clean_session_dir",
        f"~/.openclaw/agents/{agent_id}/clean_session")
    clean_dir = Path(clean_dir_str).expanduser()
    clean_file = clean_dir / f"{date_str}.json"

    if not clean_file.exists():
        print(f"[distill-l1] {date_str} clean_session 不存在（当天无对话），跳过")
        return {"status": "skipped", "reason": "no_clean_session", "date": date_str}

    # 检查 L1 是否已写
    l1_path = automation.l1_writer._get_l1_path(date_str)
    if l1_path.exists():
        try:
            content = l1_path.read_text(encoding='utf-8')
            if len(content.strip()) > 50:
                print(f"[distill-l1] {date_str} L1 已存在，跳过")
                return {"status": "skipped", "reason": "l1_exists", "date": date_str}
        except:
            pass

    # 读 clean_session
    try:
        with open(clean_file, 'r', encoding='utf-8') as f:
            messages = json.load(f)
    except Exception as e:
        print(f"[distill-l1] 读 clean_session 失败: {e}")
        return {"status": "error", "reason": str(e), "date": date_str}

    if not messages:
        print(f"[distill-l1] {date_str} clean_session 为空，跳过")
        return {"status": "skipped", "reason": "empty_clean_session", "date": date_str}

    # 输出结构化内容
    user_msgs = [m for m in messages if m.get("r") == "u"]
    asst_msgs = [m for m in messages if m.get("r") == "a"]

    print(f"\n📋 [distill-l1] agent '{agent_id}' — {date_str}")
    print("━" * 50)
    print(f"昨日对话: {len(user_msgs)} 条用户消息, {len(asst_msgs)} 条助手回复")
    print(f"目标 L1 文件: {l1_path}")
    print()
    print("【对话摘要】")
    for i, msg in enumerate(messages, 1):
        role = "用户" if msg.get("r") == "u" else "助手"
        content = msg.get("c", "")
        # 从时间戳提取 HH:MM（保留原时间方便核对）
        ts = msg.get("t", "")
        hhmm = ""
        if "T" in ts:
            try:
                hhmm = ts[11:16]
            except:
                pass
        time_tag = f"[{hhmm}] " if hhmm else ""
        # 内容过长时截断显示，但标注总长度
        display = content[:600]
        print(f"[{i}] {time_tag}{role}: {display}")
        if len(content) > 600:
            print(f"     ...（共 {len(content)} 字符，已截断显示）")

    print()
    print("【蒸馏规则】")
    print("关键规则（必须遵守）：")
    print("  1. SelfEvolve 是所有纠正和知识的入口 — 用户反馈/知识先写这里")
    print("  2. 纠正升级（7天计数制）：先读近7天L1的SelfEvolve+RuleDecision查次数")
    print("     第1次→SelfEvolve(完整)｜第2次→RuleDecision(完整)+SelfEvolve(摘要+次数)")
    print("     第3+次→如果纠正内容进化，更新RuleDecision为新版本+SelfEvolve记'规则更新'")
    print("  3. 知识分流：系统/工具/组织→SocialEcology｜个人/通用→SelfEvolve")
    print("  4. 只记一次原则：同一内容只出现一个分类")
    print()
    print("读取近7天L1示例：")
    print("  from pathlib import Path")
    print(f"  l1_dir = Path('{l1_path.parent}')")
    print("  for f in sorted(l1_dir.glob('*-*-*.md'))[-7:]:")
    print("      content = f.read_text()")
    print("      # 检查 SelfEvolve/RuleDecision 段落中是否有匹配的纠正主题")
    print()
    print("【6 分类速查】")
    print("  RuleDecision — 经≥2次纠正升级的硬性规范")
    print("  SelfEvolve — 纠正/知识/偏好的入口（第1次纠正写这里）")
    print("  SocialEcology — 客观环境：角色/渠道/协作/系统功能")
    print("  To-do — 承诺/搁置/备忘")
    print("  Output — 已完成有明确结果的事项")
    print("  Event — 兜底：以上都不符的事实")
    print()
    print("【写入前自检】")
    print("  □ 近7天L1查了纠正次数？")
    print("  □ 纠正够2次要升RuleDecision？")
    print("  □ SocialEcology有漏？（角色/渠道/系统知识）")
    print("  □ To-do/Output有漏？（搁置/完成事项）")
    print("  □ 近3天L1有重复？（有则引用不写全文）")
    print("  □ 每条≤100字，带source")
    print()
    print("写入方法：")
    print(f"  from memory.l1_writer import L1Writer")
    print(f"  writer = L1Writer(\"{agent_id}\")")
    print(f"  writer.write(entries, \"{date_str}\")")
    print(f"  # entries = [{{'event_type': 'Event', 'content': '...'}}, ...]")
    print(f"  # 分类: RuleDecision / SelfEvolve / SocialEcology / To-do / Output / Event")
    print()
    print("写入后请回复【蒸馏完成】")
    print()

    return {
        "status": "ok",
        "date": date_str,
        "message_count": len(messages),
        "user_count": len(user_msgs),
        "asst_count": len(asst_msgs),
    }


def _handle_l2_command(args: list) -> dict:
    """
    处理 L2 相关子命令
    
    命令：
      l2 correct --agent <id> --content "..." [--source binary] [--context "..."]
      l2 process --agent <id>
      l2 status --agent <id>
    """
    from .l2_extraction import (
        add_correction, get_corrections,
        get_patterns, process_patterns_from_corrections,
        get_insights, add_correction_legacy
    )
    
    # args[0] = 'memory.automation', args[1] = 'l2', args[2] = 子命令
    if len(args) < 3:
        print("L2 自我改进层命令：")
        print("  l2 correct --agent <id> --topic <T> --wrong <W> --correct <C> [--source binary|self] [--context \"...\"]")
        print("  l2 process --agent <id> [--min <N>] [--dry-run]")
        print("  l2 status --agent <id>")
        print("")
        print("示例：")
        print("  python -m memory.automation l2 correct --agent xiaoxian --topic \"代码风格\" --wrong \"双引号\" --correct \"单引号\"")
        print("  python -m memory.automation l2 process --agent xiaoxian --min 3")
        return {"error": "缺少子命令"}
    
    subcmd = args[2].lower()
    
    # 解析参数 (从 args[3] 开始，因为 args[0]=模块名, args[1]=l2, args[2]=子命令)
    agent_id = None
    topic = None
    wrong = None
    correct = None
    content = None  # 兼容旧接口
    source = "self"
    context = ""
    min_count = 3
    dry_run = False
    
    i = 3
    while i < len(args):
        if args[i] == "--agent" and i + 1 < len(args):
            agent_id = args[i + 1]
            i += 2
        elif args[i] == "--topic" and i + 1 < len(args):
            topic = args[i + 1]
            i += 2
        elif args[i] == "--wrong" and i + 1 < len(args):
            wrong = args[i + 1]
            i += 2
        elif args[i] == "--correct" and i + 1 < len(args):
            correct = args[i + 1]
            i += 2
        elif args[i] == "--content" and i + 1 < len(args):
            content = args[i + 1]
            i += 2
        elif args[i] == "--source" and i + 1 < len(args):
            source = args[i + 1]
            i += 2
        elif args[i] == "--context" and i + 1 < len(args):
            context = args[i + 1]
            i += 2
        elif args[i] == "--min" and i + 1 < len(args):
            try:
                min_count = int(args[i + 1])
            except ValueError:
                min_count = 3
            i += 2
        elif args[i] == "--dry-run":
            dry_run = True
            i += 1
        else:
            i += 1
    
    if not agent_id:
        return {"error": "缺少 --agent 参数"}
    
    if subcmd == "correct":
        # 新格式：使用 --topic --wrong --correct
        if topic and wrong and correct:
            add_correction(agent_id, topic, wrong, correct, source, context)
            return {"success": True, "action": "add_correction", "format": "structured", "agent": agent_id}
        # 旧格式：使用 --content（自动解析）
        elif content:
            add_correction_legacy(agent_id, content, source, context)
            return {"success": True, "action": "add_correction", "format": "legacy", "agent": agent_id}
        else:
            return {"error": "correct 命令需要 --topic/--wrong/--correct 或 --content 参数"}
    
    elif subcmd == "process":
        # 从 corrections 生成 patterns
        result = process_patterns_from_corrections(agent_id, min_count=min_count, dry_run=dry_run)
        return {
            "success": True, 
            "action": "process_patterns", 
            "corrections_processed": result.get("processed", 0),
            "patterns_created": result.get("created", 0),
            "patterns_updated": result.get("updated", 0)
        }
    
    elif subcmd == "status":
        corrections = get_corrections(agent_id)
        patterns = get_patterns(agent_id)
        insights = get_insights(agent_id)
        print(f"\n[L2 Status] Agent: {agent_id}")
        print(f"  Corrections: {len(corrections)}")
        print(f"  Patterns: {len(patterns)}")
        print(f"  Insights: {len(insights)} (Agent 手动维护)")
        return {
            "success": True,
            "corrections_count": len(corrections),
            "patterns_count": len(patterns),
            "insights_count": len(insights)
        }
    
    else:
        return {"error": f"未知 L2 子命令: {subcmd}"}




def main():
    """主入口函数"""
    if len(sys.argv) < 2:
        print("用法: python -m memory.automation <命令> [选项]")
        print("")
        print("L1 记忆管理：")
        print("  manual    - 手动触发 session 清洗")
        print("  heartbeat - Heartbeat 触发 session 清洗")
        print("  distill-l1 --agent <id> [--date YYYY-MM-DD] - 输出昨日对话供 agent 写 L1")
        print("  setup     - per-agent 运行环境检查")
        print("  old-session <key> - 处理已 reset 的旧 session")
        print("")
        print("L2 自我改进层：")
        print("  l2 correct --agent <id> --content \"...\" - 添加纠正记录")
        print("  l2 process --agent <id> - 从 corrections 生成 patterns")
        print("  l2 status --agent <id> - 查看 L2 状态")
        print("")
        print("L3 长期记忆（新增）：")
        print("  l3 promote --agent <id> [--dry-run] - 将 L2 提升到 L3")
        print("  l3 status --agent <id> - 查看 L3 状态")
        print("")
        print("通用选项：")
        print("  --agent <id> - 指定 agent ID（必需）")
        print("  --session <file> - 指定 session 文件路径（仅 manual 模式）")
        print("")
        print("示例:")
        print("  python -m memory.automation manual --agent code")
        print("  python -m memory.automation heartbeat --agent xiaoxian")
        print("  python -m memory.automation setup --agent mautoer")
        print("  python -m memory.automation l2 correct --agent code --content \"纠正内容\" --source binary")
        print("  python -m memory.automation l3 promote --agent code --dry-run")
        sys.exit(1)

    mode = sys.argv[1].lower()
    
    # L2 子命令处理
    if mode == "l2":
        result = _handle_l2_command(sys.argv)
        print("\n" + json.dumps(result, ensure_ascii=False))
        sys.exit(0 if result.get("success") else 1)

    # 解析可选参数
    session_file = None
    agent_id = None
    config_path = None
    for i in range(2, len(sys.argv)):
        if sys.argv[i] == "--session" and i + 1 < len(sys.argv):
            session_file = sys.argv[i + 1]
        elif sys.argv[i] == "--agent" and i + 1 < len(sys.argv):
            agent_id = sys.argv[i + 1]
        elif sys.argv[i] == "--config" and i + 1 < len(sys.argv):
            config_path = sys.argv[i + 1]

    # 创建自动化实例
    automation = MemoryAutomation(agent_id=agent_id, config_path=config_path)

    if mode == "manual":
        # 手动模式 - 可以尝试从环境变量获取用户消息
        user_message = os.environ.get("USER_MESSAGE", "")
        result = automation.run_manual(user_message, session_file=session_file)

        print(f"\n[结果] {result['reason']}")
        if result.get('error') == 'agent_id_required':
            print(f"[错误] 请在调用时添加 --agent 参数")
            automation.logger.log("manual", "error", "缺少 --agent 参数")
            sys.exit(1)
        if result['triggered']:
            print(f"  - 保存文件: {result['saved_count']}")
            if result.get('saved_paths'):
                for p in result['saved_paths']:
                    print(f"    📁 {p}")
            if result.get('session_key'):
                print(f"  - Session: {result['session_key']}")
            automation.logger.log("manual", "ok", f"保存 {result['saved_count']} 个文件, session={result.get('session_key', 'N/A')}")
        else:
            automation.logger.log("manual", "ok", result['reason'])

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
        print(f"\n[结果] 保存文件数: {result[0]}, paths: {result[1]}")

    elif mode == "heartbeat":
        # Heartbeat 模式 - 只读取新消息，写入队列，不蒸馏
        result = automation.run_heartbeat()

        # 输出结果（Agent 会解析这个输出）
        if result.get('activation_needed'):
            print(f"\n[MemoryAutomation] {result['reason']}")
            print(f"[MemoryAutomation] 请在 HEARTBEAT.md 中添加 --agent 参数")
            automation.logger.log("heartbeat", "error", result['reason'])
        elif result['triggered'] and result.get('saved_count', 0) > 0:
            print(f"\n[MemoryAutomation] 保存 {result['saved_count']} 个 clean_session 文件")
            automation.logger.log("heartbeat", "ok", f"保存 {result['saved_count']} 个 clean_session 文件")
        else:
            print(f"\n[结果] {result['reason']}")
            status = "ok" if not result.get('error') else "error"
            automation.logger.log("heartbeat", status, result['reason'])
    
    elif mode == "process-backlog":
        # 处理积压的历史 session
        max_sessions = 1
        force = False
        
        # 解析参数
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--max" and i + 1 < len(sys.argv):
                max_sessions = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--force":
                force = True
                i += 1
            elif sys.argv[i] == "--agent" and i + 1 < len(sys.argv):
                i += 2
            else:
                i += 1
        
        print(f"[MemoryAutomation] [Backlog] 批量处理积压 session (max={max_sessions}, force={force})")
        result = automation.run_process_backlog(max_sessions=max_sessions, force=force)
        
        processed = len(result.get("processed", []))
        skipped = len(result.get("skipped", []))
        errors = len(result.get("errors", []))
        
        print(f"\n[结果] 处理完成: {processed} 成功, {skipped} 跳过, {errors} 错误")
        if result.get("processed"):
            print("已处理文件:")
            for item in result["processed"]:
                print(f"  ✓ {item['file']} ({item['saved_count']} 个文件)")
        
        # 记录日志
        detail = f"处理完成: {processed} 成功, {skipped} 跳过, {errors} 错误"
        status = "ok" if errors == 0 else "warning"
        automation.logger.log("process-backlog", status, detail)
    
    elif mode == "distill-l1" or mode == "distill":
        # distill-l1 模式：输出昨日 clean_session 供 agent 写 L1
        date_str = None
        for i in range(2, len(sys.argv)):
            if sys.argv[i] == "--date" and i + 1 < len(sys.argv):
                date_str = sys.argv[i + 1]
        distill_result = _handle_distill_l1(automation, date_str)
        if distill_result.get("status") == "ok":
            report_date = date_str or "昨天"
            automation.logger.log("distill-l1", "ok", f"{report_date}: {distill_result.get('message_count', 0)} 条对话")
        elif distill_result.get("status") == "skipped":
            report_date = date_str or "昨天"
            automation.logger.log("distill-l1", "skipped", f"{report_date}: {distill_result.get('reason', '')}")
        else:
            automation.logger.log("distill-l1", "error", str(distill_result.get("reason", "")))
        result = distill_result
    
    elif mode == "setup":
        # per-agent 配置检查
        setup_result = run_setup(agent_id)
        # setup_checker 内部已打印报告，这里只记录日志
        if automation and hasattr(automation, 'logger'):
            detail = f"{setup_result['passed']}/{setup_result['total']} 项就绪"
            status = "ok" if setup_result['failed'] == 0 else "warning"
            automation.logger.log("setup", status, detail)
        result = setup_result

    else:
        print(f"错误: 未知模式 '{mode}'")
        print("用法: python -m memory.automation [manual|heartbeat|distill-l1|setup|l2|process-backlog]")
        sys.exit(1)

    # 输出 JSON 结果（供调用方解析）
    print("\n" + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
