# Memory-Automation 更新文档
**日期**: 2026-03-29 / 2026-03-30
**状态**: 部分实施

---

## 2026-03-30 更新（已完成）

### 问题：agent_id 硬编码导致数据污染

**现象**：
- config.json 里 `agent_id: "code"` 是硬编码的 fallback 值
- xiaoxian、TS 调用 Mauto 时，数据会写到 code 的 memory 目录
- 所有 agent 共用 skill，但 heartbeat 运行时 cwd 是 skill 目录，检测不到正确的 agent_id

### 解决方案

**1. automation.py 修改**

```python
# main() 添加 --agent 参数
def main():
    # 解析 --agent 参数
    for i in range(2, len(sys.argv)):
        if sys.argv[i] == "--agent" and i + 1 < len(sys.argv):
            agent_id = sys.argv[i + 1]
    automation = MemoryAutomation(agent_id=agent_id)
```

**2. 无 agent_id 时行为**

```python
# heartbeat 无 agent_id → 写激活标记，跳过执行
if not self.agent_id:
    result = {
        "triggered": False,
        "reason": "agent_id 未指定，跳过执行",
        "activation_needed": True
    }
    self.write_activation_flag()  # 写入 .mauto_activation_needed
    return result

# manual 无 agent_id → 报错退出
if not self.agent_id:
    result = {
        "error": "agent_id_required",
        "reason": f"agent_id 未指定，请在调用时加 --agent 参数"
    }
    return result
```

**3. HEARTBEAT.md 更新**

所有 agent 的 HEARTBEAT.md 必须包含 `--agent` 参数：

```bash
# code
cd ~/.openclaw/skills/memory-automation && python3 -m memory.automation heartbeat --agent code

# xiaoxian
cd ~/.openclaw/skills/memory-automation && python3 -m memory.automation heartbeat --agent xiaoxian

# TS
cd ~/.openclaw/skills/memory-automation && python3 -m memory.automation heartbeat --agent TS
```

**4. 新增方法**

```python
def write_activation_flag(self, message):
    """写入激活标记文件"""
    flag_path = Path.home() / ".openclaw/workspaces/{agent_id}/workspace/memory/.mauto_activation_needed"
    # 写入提示信息

def clear_activation_flag(self):
    """清除激活标记"""
```

### 涉及文件

| 文件 | 改动 |
|------|------|
| `memory/automation.py` | 添加 --agent 参数、无 agent_id 时报错/写 flag |
| `SKILL.md` | 更新调用说明、agent_id 表格 |
| `HEARTBEAT.md` (code) | 添加 --agent code |
| `HEARTBEAT.md` (xiaoxian) | 添加 --agent xiaoxian |
| `HEARTBEAT.md` (TS) | 添加 --agent TS |

---

## 更新内容汇总（2026-03-29 原内容）

### 一、SKILL.md 新增内容

**1. 首次激活流程**
```markdown
## 首次激活流程
当用户说"请使用 memory-automation"时：
1. Agent 执行 run_manual()
2. 如果输出 "API_KEY: not_configured"，
   Agent 询问用户是否提供 API key 和供应商
3. 用户提供了 → Agent 将 key 写入 config.json
4. 用户没有 → 使用 regex 蒸馏
```

**2. 配置管理**
```markdown
## 配置管理

用户可以随时：
- 提供/更新 API key → Agent 写入 config.json
- 更换供应商/模型 → Agent 更新 config.json

Agent 发现以下情况时主动询问用户：
- API key 未配置
- API key 失效
- Regex 蒸馏超过 30 次

当用户询问时：
- Agent 检查 config.json 当前配置
- 告知用户当前状态
- 根据用户需求更新
```

**3. 蒸馏模式说明**
```markdown
## 蒸馏模式

| 模式 | 触发条件 | 需要 API key |
|------|----------|-------------|
| LLM 蒸馏 | config.json 有 api_key | ✅ |
| Regex 蒸馏 | 无 api_key 或 LLM 失败 | ❌ |

- 每次 heartbeat 检查 api_key，有则用 LLM
- API 失败时 fallback 到 regex，并通知用户
- Regex 蒸馏超过 30 次时，Agent 主动询问用户是否满意
```

**4. Regex 升级询问**
```markdown
## Regex 升级机制

当 regex 蒸馏次数达到 30 次时：
- Agent 输出 "REGEX_LIMIT_REACHED"
- Agent 主动询问用户：
  "你已经使用 regex 蒸馏 30 次了，效果如何？
   是否要：1）提供 API key 升级到 LLM 蒸馏
          2）提供更好的蒸馏关键词/标签"
```

---

### 二、config.json 新增字段

```json
{
  "llm": {
    "enabled": true,
    "api_key": null,
    "provider": "minimax",
    "model": "MiniMax-M2.7",
    "api_endpoint": "https://api.minimax.chat",
    "api_key_asked": false
  },
  "regex": {
    "count": 0,
    "count_asked": false
  }
}
```

---

### 三、automation.py 改动

**run_manual() 逻辑：**
```
1. 读取 config.json 的 llm.api_key
2. 检测 llm.api_key_asked
   - 无 key 且 api_key_asked == false
     → 输出 "[MEMORY-AUTOMATION] API_KEY: not_configured"
     → 设置 api_key_asked = true
   - 有 key → 正常执行 LLM 蒸馏
3. LLM 蒸馏失败 → fallback 到 regex
4. 检测 regex.count
   - count >= 30 且 count_asked == false
     → 输出 "[MEMORY-AUTOMATION] REGEX_LIMIT_REACHED"
     → 设置 count_asked = true
```

**run_heartbeat() 保持现状：**
```
写入 pending_queue + 打印 [MEMORY] 提示
```

---

### 四、session_distiller.py 改动

**distill_with_llm() 新增错误处理：**
```
API 错误 → 输出特定格式消息：
- 401/403 → "API_KEY_INVALID"
- 429 → "API_RATE_LIMITED"
- 网络错误 → "API_CONNECTION_ERROR"
- 其他 → "API_ERROR: <原始错误>"
```

**distill_messages() 改动：**
```
优先 LLM 蒸馏
↓ LLM 失败
fallback 到 regex
↓ fallback 失败
输出错误消息
```

---

### 五、涉及文件清单

| 文件 | 改动内容 |
|------|---------|
| `SKILL.md` | 新增激活流程、配置管理、蒸馏模式说明、Regex 升级机制 |
| `config.json` | 新增 llm.api_key_asked、regex.count、regex.count_asked |
| `memory/automation.py` | 检测 api_key、regex count，输出特定消息 |
| `memory/session_distiller.py` | API 错误处理 + fallback |

---

### 六、Agent 询问用户时的标准话术

**首次询问 API key：**
```
memory-automation 需要配置以下信息：
1. API key（从哪里获取？）
2. 供应商（默认 minimax）
3. 模型（默认 MiniMax-M2.7）

如暂不提供，将使用 regex 蒸馏（效果较差）。
```

**Regex 30 次询问：**
```
你已经使用 regex 蒸馏 30 次了，效果如何？
是否要：
1）提供 API key 升级到 LLM 蒸馏
2）提供更好的蒸馏关键词/标签
```

**API 错误询问：**
```
memory-automation 的 API key 已失效或配置有误。
请检查或提供新的 API key。
```

---

## 文件路径

```
~/.openclaw/skills/memory-automation/
├── SKILL.md
├── config.json
└── memory/
    ├── automation.py
    └── session_distiller.py
```
