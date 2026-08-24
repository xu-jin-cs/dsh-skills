# Xj-engine

`Xj-rules` 配套的通用默认 AgentEngine。

- `agent-harness` 只是可选平台宿主，不是引擎
- 本机默认引擎注册为 `Xj-engine`
- Python 包：`xj_engine`
- 入口：`xj_engine.kernel.et`
- CLI：`xj-engine`

## 内容

- `kernel.py` — 内核统一入口（含任务桥接执行）
- `et_contract.py` — ET 契约校验（含 task 块）
- `et_sign.py` — 签名/验签
- `audit.py` — 审计事件（含任务完成/取消/归档）
- `state_store.py` — 状态持久化
- `state_wiring.py` — 状态双写收口
- `task.py` — 任务生命周期 + BridgeExecutor
- `et_test_gates.py` — 测试门禁 ET 模块
- `claude_engine.py` — Claude API 执行引擎（可选）
- `database.py` — 独立 SQLite 数据库入口
- `docs/bridge_contract.md` — 桥接契约

## 安装

```bash
# 常规安装依赖
pip install -r requirements.txt

# 注册为可编辑安装（本机默认引擎）
pip install -e .
```

可选 Claude 执行引擎：

```bash
pip install -r requirements-optional.txt
```

## 使用

```python
from xj_engine.kernel import et
# 按 ET 契约传入 payload 调用
```

或使用 CLI：

```bash
xj-engine health
xj-engine run --payload '{"op": ...}'
```

任务生命周期示例：

```json
{
  "task": {
    "action": "complete",
    "task_id": "task-001",
    "evidence": {"output_file": "result.json"},
    "targets": ["dsh"]
  }
}
```

## 桥接

桥接执行器在内核调用，具体前端 adapter 通过契约实现：

```python
from xj_engine.task import get_bridge_executor

def adapter_dsh(event):
    # 调用 todo_write 标记 completed
    return {"ok": True}

get_bridge_executor().register_adapter("dsh", adapter_dsh)
```

详细见 `docs/bridge_contract.md`。

## 注册为默认引擎

本机默认引擎注册在：

- `~/.agents/engine_registry.json`
- `~/.dsh/engine_registry.json`

全局 Agent 配置（`~/.agents/AGENTS.md`、`~/.dsh/AGENTS.md`、`~/.claude/CLAUDE.md`、`~/.codex/AGENTS.md`）已声明默认引擎为 `Xj-engine`。

## 环境变量

见 `.env.example`。

- `XJ_ENGINE_DB_URL`：数据库地址
- `AGENT_ENGINE_SECRET`：内核签发密钥

## 兼容性说明

- 已移除原平台数据库依赖，改为本地 `database.py`
- 已移除外部测试技能服务依赖，`skills.py` 为 stub
- 已移除原平台私有路径依赖
- 不包含原平台业务代码
- `agent-harness` 仅是平台宿主，默认引擎是 `Xj-engine`
