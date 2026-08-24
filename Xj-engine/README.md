# Xj-engine

`Xj-rules` 配套的通用默认 AgentEngine。

- `agent-harness` 只是可选平台宿主，不是引擎
- 本机默认引擎注册为 `Xj-engine`
- Python 包：`xj_engine`
- 入口：`xj_engine.kernel.et`
- CLI：`xj-engine`

## 内容

- `kernel.py` — 内核统一入口
- `et_contract.py` — ET 契约校验
- `et_sign.py` — 签名/验签
- `audit.py` — 审计事件
- `state_store.py` — 状态持久化
- `state_wiring.py` — 状态双写收口
- `et_test_gates.py` — 测试门禁 ET 模块
- `claude_engine.py` — Claude API 执行引擎（可选）
- `database.py` — 独立 SQLite 数据库入口

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

或参考 `et_contract.py` 中的 payload/输出契约。

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
