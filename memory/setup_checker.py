#!/usr/bin/env python3
"""
Setup Checker - per-agent 运行环境检查

用法:
    python -m memory.automation setup --agent {agent_id}

检查 Mauto 自身文件是否就绪（不碰 openclaw.json 等系统配置）：
- heartbeat-state.json 是否存在（Mauto 初始化状态）
- HEARTBEAT.md 是否存在且内容完整
- 凌晨 L1 蒸馏 cron job 是否存在（可选）
- 日志文件是否可写

原则：只检查+输出指导，不做自动修复
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


class SetupChecker:
    """per-agent 配置检查器"""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.workspace = Path.home() / ".openclaw" / "workspaces" / agent_id / "workspace"
        self.agents_dir = Path.home() / ".openclaw" / "agents" / agent_id
        self.results = []
        self.passed = 0
        self.failed = 0

    def _run_command(self, cmd: List[str]) -> tuple:
        """执行命令并返回 (stdout, stderr, returncode)"""
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30,
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return "", "命令超时", 1
        except FileNotFoundError:
            return "", f"命令未找到: {cmd[0]}", 127
        except Exception as e:
            return "", str(e), 1

    def check_heartbeat_state(self) -> Dict[str, Any]:
        """
        检查项 A：heartbeat-state.json

        Mauto 自己的状态文件，记录上次处理到的 session 和消息位置。
        存在 = Mauto 已为此 agent 初始化过。
        """
        state_path = self.workspace / "memory" / "heartbeat-state.json"

        if not state_path.exists():
            return {
                "name": "heartbeat-state.json",
                "status": "fail",
                "label": "不存在",
                "message": f"文件不存在: {state_path}",
                "fix": f"Mauto 尚未为此 agent 初始化。\n"
                       f"请先在 HEARTBEAT.md 中添加 heartbeat 命令，Mauto 首次运行时会自动创建此文件。\n"
                       f"或手动运行一次：cd ~/.openclaw/skills/memory-automation && python3 -m memory.automation heartbeat --agent {self.agent_id}",
            }

        # 检查文件内容是否有效
        try:
            content = state_path.read_text(encoding="utf-8").strip()
            if not content:
                return {
                    "name": "heartbeat-state.json",
                    "status": "fail",
                    "label": "内容为空",
                    "message": f"文件存在但内容为空: {state_path}",
                    "fix": "删除此文件后重新运行 heartbeat 会重新生成",
                }
            state = json.loads(content)
            version = state.get("version", "未知")
            last_processed = state.get("last_processed_time", "从未")
        except (json.JSONDecodeError, IOError) as e:
            return {
                "name": "heartbeat-state.json",
                "status": "fail",
                "label": "损坏",
                "message": f"文件存在但读取失败: {e}",
                "fix": f"删除 {state_path} 后重新运行 heartbeat 会重新生成",
            }

        return {
            "name": "heartbeat-state.json",
            "status": "pass",
            "label": "就绪",
            "message": f"版本: {version}，上次处理: {last_processed}",
            "fix": None,
        }

    def check_heartbeat_md(self) -> Dict[str, Any]:
        """
        检查项 B：HEARTBEAT.md 完整性

        检查 workspace 的 HEARTBEAT.md 是否存在且包含 memory-automation 命令。
        """
        hb_path = self.workspace / "HEARTBEAT.md"

        if not hb_path.exists():
            return {
                "name": "HEARTBEAT.md",
                "status": "fail",
                "label": "不存在",
                "message": f"文件不存在: {hb_path}",
                "fix": f"请创建 {hb_path}，内容示例：\n"
                       f"## memory-automation\n"
                       f"cd ~/.openclaw/skills/memory-automation && python3 -m memory.automation heartbeat --agent {self.agent_id}\n",
            }

        try:
            content = hb_path.read_text(encoding="utf-8")
        except IOError as e:
            return {
                "name": "HEARTBEAT.md",
                "status": "fail",
                "label": "无法读取",
                "message": f"读取失败: {e}",
                "fix": f"请检查文件权限: {hb_path}",
            }

        # 检查是否包含 memory-automation 相关命令
        has_memory_cmd = "memory.automation" in content or "memory-automation" in content

        if not has_memory_cmd:
            return {
                "name": "HEARTBEAT.md",
                "status": "fail",
                "label": "缺少命令",
                "message": f"文件存在但未包含 memory-automation 命令",
                "fix": f"在 {hb_path} 中添加：\n"
                       f"## memory-automation\n"
                       f"cd ~/.openclaw/skills/memory-automation && python3 -m memory.automation heartbeat --agent {self.agent_id}\n",
            }

        return {
            "name": "HEARTBEAT.md",
            "status": "pass",
            "label": "完整",
            "message": f"已包含 memory-automation 命令",
            "fix": None,
        }

    def check_cron_job(self) -> Dict[str, Any]:
        """
        检查项 C：凌晨 L1 蒸馏 cron job

        检查 openclaw cron 中是否有相关的定时任务。
        这是可选功能，用于凌晨 3-4 点强制检查 L1。
        """
        stdout, stderr, rc = self._run_command(["openclaw", "cron", "list"])

        if rc != 0:
            return {
                "name": "凌晨蒸馏 cron",
                "status": "note",
                "label": "无法检查",
                "message": f"openclaw cron list 执行失败 (rc={rc}): {stderr or stdout.strip()}",
                "fix": None,
            }

        lines = stdout.strip().split("\n")
        found_jobs = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if self.agent_id in line or "l1-distill" in line.lower() or "memory-auto" in line.lower():
                found_jobs.append(line)

        if found_jobs:
            return {
                "name": "凌晨蒸馏 cron",
                "status": "pass",
                "label": "已存在",
                "message": f"找到 {len(found_jobs)} 个相关 cron job",
                "fix": None,
            }

        return {
            "name": "凌晨蒸馏 cron",
            "status": "info",
            "label": "未配置（可选）",
            "message": "凌晨 3-4 点强制 L1 蒸馏需要依赖 cron job。"
                       "建议在 3:00-4:00 之间选任意分钟，各 agent 错开即可。",
            "fix": None,
        }

    def check_log_file(self) -> Dict[str, Any]:
        """
        检查项 D：日志文件是否可写

        检查 memory-automation.log 是否存在并可追加。
        """
        log_path = self.agents_dir / "memory-automation.log"

        if not log_path.parent.exists():
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
            except IOError as e:
                return {
                    "name": "运行日志",
                    "status": "fail",
                    "label": "目录不可写",
                    "message": f"无法创建日志目录: {log_path.parent}",
                    "fix": f"请确认目录权限: {log_path.parent}",
                }

        if not log_path.exists():
            return {
                "name": "运行日志",
                "status": "info",
                "label": "尚未生成",
                "message": f"日志文件尚未生成，首次 heartbeat 执行后会自动创建: {log_path}",
                "fix": None,
            }

        try:
            # 尝试追加一行测试写入
            with open(log_path, "a", encoding="utf-8") as f:
                pass

            # 统计行数
            with open(log_path, "r", encoding="utf-8") as f:
                line_count = sum(1 for _ in f)

            # 读取最后一条记录的时间戳
            last_ts = "未知"
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                entry = json.loads(line)
                                last_ts = entry.get("ts", "未知")
                            except json.JSONDecodeError:
                                pass
            except IOError:
                pass

        except IOError as e:
            return {
                "name": "运行日志",
                "status": "fail",
                "label": "不可写入",
                "message": f"日志文件无法写入: {e}",
                "fix": f"请检查文件权限: {log_path}",
            }

        return {
            "name": "运行日志",
            "status": "pass",
            "label": "就绪",
            "message": f"共 {line_count} 条记录，最近记录时间: {last_ts}",
            "fix": None,
        }

    def run_all(self) -> Dict[str, Any]:
        """运行所有检查并返回结果"""
        checks = [
            self.check_heartbeat_state(),
            self.check_heartbeat_md(),
            self.check_cron_job(),
            self.check_log_file(),
        ]

        self.passed = sum(1 for c in checks if c["status"] == "pass")
        self.failed = sum(1 for c in checks if c["status"] == "fail")

        return {
            "agent_id": self.agent_id,
            "passed": self.passed,
            "failed": self.failed,
            "total": len(checks),
            "checks": checks,
        }

    def print_report(self, result: Dict[str, Any]) -> None:
        """打印标准化检查报告"""
        print(f"\n📋 Mauto per-agent 检查报告 — {result['agent_id']}")
        print("━" * 40)

        for check in result["checks"]:
            icon_map = {"pass": "✅", "fail": "❌", "info": "ℹ️", "note": "⚠️"}
            icon = icon_map.get(check["status"], "❓")
            print(f"\n{icon} [{check['name']}] {check['label']}")
            if check["message"]:
                for line in check["message"].split("\n"):
                    print(f"    {line}")
            if check.get("fix"):
                print(f"    修复指引:")
                for line in check["fix"].split("\n"):
                    print(f"      {line}")

        print(f"\n📊 摘要: {result['passed']}/{result['total']} 项就绪")
        if result["failed"] > 0:
            print(f"   有 {result['failed']} 项需要修复")
        print()


def run_setup(agent_id: str) -> Dict[str, Any]:
    """
    运行 setup 检查并返回结果

    Args:
        agent_id: Agent ID

    Returns:
        检查结果字典
    """
    checker = SetupChecker(agent_id)
    result = checker.run_all()
    checker.print_report(result)
    return result


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "--agent":
        print("用法: python -m memory.setup_checker --agent {agent_id}")
        sys.exit(1)

    agent_id = sys.argv[2]
    result = run_setup(agent_id)
    sys.exit(0 if result["failed"] == 0 else 1)
