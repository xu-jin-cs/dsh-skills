# Xj-engine — 独立 Agent 引擎内核（中文说明）

> dsh-skills 生态的默认引擎：ET 契约、节点调度与控制、交付物签发、事件上报——**引擎永远不替你跑模型**。
>
> [English](README.md) · [← 返回 dsh-skills](../README.md)

> ⚠️ **使用边界**：本引擎**不做执行**——不内置模型、不推演节点体、无生产 runner。
> 只负责：**内容（交付物）签发 · 节点调度与控制 · 契约编译/校验 · 事件上报**。
> 执行归宿主：`assemble → spawn → snapshot`，模型就是当前会话。（2026-11-13 裁定；**2026-11-17 起为结构事实**——headless 进程内执行通道及其内置 PM 节点体、内置 LLM 推理节点已全部移除，引擎在结构上不可能自行执行 workflow。）

## 是什么 / 治什么痛点

LLM Agent 的流程编排常把「谁决策」和「谁执行」搅在一起。Xj-engine 把两层分开——宿主会话（带着模型）负责推演，引擎负责一切机械事项：

- Python 包 `engine`，API 入口 `engine.kernel.et`，CLI `xj-engine`。
- **执行载体边界（2026-11-13 裁定）**：执行 = ZCode 宿主拉形态——`assemble → spawn（会话/子代理）→ snapshot`，模型就是当前会话；引擎只做：契约编译/校验、节点调度与控制、交付物签发、事件上报。
- `default_runner`（`SCI_RUNNER_CMD`）只是测试/自定义桥接，**不是生产执行入口**——未配置时显式报错，禁止静默桩跑。
- `tests/` 下 11 个 pytest 套件看守内核门禁、流程强制、范式选择、团队决策等。
- **headless 通道已废除（2026-11-17）**：内置 PM 节点体、内置 LLM 推理节点、平台 HTTP 上报件与并行分支执行器全部删除——引擎只做契约编译/校验、节点调度与交付签发；`flow run` 仅保留 stage 节点 + runner 委托骨架（runner 是测试桥，永非生产入口）。

## 30 秒安装

```bash
pip install -r Xj-engine/requirements.txt
pip install -e Xj-engine          # 注册为可编辑安装（本机默认引擎）
# 可选 Claude 执行引擎：
pip install -r Xj-engine/requirements-optional.txt
```

## 5 分钟上手

CLI：

```bash
xj-engine health
xj-engine run --payload '{"op": ...}'
xj-engine workflow init | validate
xj-engine flow
```

Python 入口：

```python
from engine.kernel import et
# 按 ET 契约传入 payload
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

桥接执行（宿主侧 adapter 按契约注册）：

```python
from engine.task import get_bridge_executor

def adapter_dsh(event):
    # 例如调用 todo_write 标记 completed
    return {"ok": True}

get_bridge_executor().register_adapter("dsh", adapter_dsh)
```

详见 `docs/bridge_contract.md`，另有 `docs/node_executor_contract.md` / `docs/stage_runtime_contract.md`。

## 输入 / 输出

- **输入**：ET 契约 payload（内核）、任务生命周期事件（`complete` / `cancel` / `archive`，带证据）、workflow 定义（init/validate）。
- **输出**：契约校验后的调度、签发的交付物、审计事件、状态持久化。
- **构成**：`kernel.py`（统一入口，含任务桥接）· `et_contract.py` / `et_sign.py`（契约 + 签名）· `audit.py` · `state_store.py` / `state_wiring.py`（双写收口）· `task.py`（生命周期 + BridgeExecutor）· `et_test_gates.py` · `database.py`（独立 SQLite）· `engine/flow/`（编译器 / 构建器 / 校验器 / 图 / 并行 / 检查点）。

## 能力与边界

- **擅长**：契约校验的编排、双写收口的状态持久化、交付物签发、审计留痕、ET 契约内测试门禁。
- **不在射程**：引擎不内置模型、不推演节点体、无自有生产 runner——宿主执行，引擎记账。
- **兼容性**：已移除平台数据库依赖（本地 `database.py`）、外部测试技能服务依赖（`skills.py` stub）、私有路径依赖与平台业务代码。
- **环境变量**（见 `.env.example`）：`XJ_ENGINE_DB_URL`（数据库）、`AGENT_ENGINE_SECRET`（内核签发密钥）。

## 组合用法

- **[gate-switch](../gate-switch/README_zh.md)**：`et_test_gates` 把门禁语义装进 ET 契约。
- **[parallel-dispatch](../parallel-dispatch/README_zh.md)**：≥10 单元批量走引擎 workflow 编排。

注册：使用它的机器在 `engine_registry.json` 中将其登记为本机默认引擎（见 `.env.example` 与仓库文档）。

---

许可：[自定义源码可用许可](../LICENSE)（中文对照：[LICENSE-zh.md](../LICENSE-zh.md)）——仅供个人非商用本地使用；未经书面授权禁止公开 Fork、商用分发、SaaS 服务。作者 [xu-jin-cs](https://github.com/xu-jin-cs)。
