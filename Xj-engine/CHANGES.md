# Xj-engine 变更记录

## 2026-08-25

### 初始独立化

- 从本地引擎 `agent-harness/backend/engine` 复制为独立引擎
- 目录：`dsh-skills/Xj-engine/`
- Python 包：`engine`

### 兼容性改造

- 移除 `backend.database` 依赖，新增本地 `database.py`
- 移除 `backend.services.test_skills` 依赖，`skills.py` 改为 stub
- 所有 `backend.engine.*` 导入改为包内相对导入
- `claude_engine.py` 的 `anthropic` 改为可选依赖
- 新增 `.env.example`：`XJ_ENGINE_DB_URL` / `AGENT_ENGINE_SECRET`

### 可安装化

- 新增 `pyproject.toml`
- 支持 `pip install -e .`
- 新增 CLI：
  - `xj-engine health`
  - `xj-engine run --payload '...'`

### 默认引擎注册

- 本机默认引擎注册为 `Xj-engine`
- 注册表：
  - `~/.agents/engine_registry.json`
  - `~/.dsh/engine_registry.json`
- 全局 Agent 配置已声明默认引擎

### 任务域 + 桥接层

- 新增 `task.py`：任务生命周期动作
  - `task.complete`
  - `task.cancel`
  - `task.archive`
- 新增 `BridgeExecutor`：内核执行桥接分发，前端 adapter 外部注册
- 新增完成证据校验：
  - `complete` 必须携带非空 `evidence`
- 新增审计事件：
  - `task_complete_event`
  - `task_cancel_event`
  - `task_archive_event`
- 新增 `docs/bridge_contract.md`：桥接契约、adapter 接口、事件结构
- 扩展 `et_contract.py` Payload Schema：新增 `task` 块
- 扩展 Output Schema：新增 `task_result`

> 2026-08-25 终裁（用户裁定）：任务完成需要【附身闸】——新建任务时，附身闸
> `task_complete_attach_gate` 往任务末尾追加"完成步骤"：`todo_write` 将该任务
> `status` 置为 `"completed"`，DSH 面板即打勾。没有此附身闸，新任务不会被追加完成步骤 → 无法完成。
> 完成是"追加步骤"不是 hook；不引入 `task_complete_hook.py`、`xj-engine complete` 机制
> （引擎 `task.complete` 仅可选权威记录，非必需）。`Xj-engine/gate/task_complete_attach_gate.py`
> + `attached_complete.py` 保留。

## 2026-11-04 双法合流审核修复轮（用户授权执行）

### 裁定补录（此前缺失的变更日志）
- 2026-09-13：flow 图层平迁落地——langgraph FlowGraph 迁入 Xj-engine 为正式图编排层（自研 FlowGraph），原过渡组件 xjframe_flow 双跑一致性验收后退役
- 2026-10-13：节点执行器协议落地（REFORM-GATE 判A，node_executor_protocol_20261013.md），engine/executors 三件套
- 2026-11-01：工作流通道正名——pm 正通道=宿主 stage 隔离 spawn；引擎图执行通道降级 headless 备用

### langgraph 残迹清零（2026-11-04 用户裁定）
- logger 命名 langgraph.* → logging.getLogger(__name__)；User-Agent → xj-engine-harness-client/1.0
- checkpoint 默认目录 .langgraph → .xjengine（resolve_default_checkpoint_dir 带 legacy 回退，engine/.langgraph 存量 147KB 数据不断链；env 历史别名 LANGGRAPH_CHECKPOINT_DIR 暂兼容并 WARN）
- requirements-optional.txt 移除 langgraph>=0.2（全仓零 import 实证）；子图框架改执行器作者自备
- 自愈分类值 langgraph_script → script_filter（纯内部字符串，模块内闭环，零外部引用实证）；死路径 backend/langgraph/* → engine/flow/*
- 全部误导性 docstring 按现状重写（state/edges/callback/node_defs/parallel/file_utils/custom_agent/graph/harness_client/integration/prompt_manager/nodes 等）；历史来源记载保留于本文件与各文件头

### 口径漂移修正
- harness_client.py 头注释"静默降级"→实测口径"指数退避重试 3 次+sync_failed 留痕不阻塞"（附对账脚本指引）
- node_executor_contract.md"引擎 16 态"→状态机 allowed_pairs（FlowStatus 枚举实测 17 值）

### 潜伏缺陷与死代码
- json_to_state 同名双定义拆分：恢复版改名 state_from_json（graph.py 导入同步修正、flow/__init__ 导出新增），json_to_state 单义指向治理版（nodes.py 调用签名不变）
- 删除零引用死代码：integration.py 4 弃用函数（save_state_to_db/load_state_from_db/check_harness_guards/execute_harness_transition）+ build_sync_repair_updates（缺 return 缺陷）+ harness_client.py 脉象 4 函数（ENG-018 backlog 归档至本条目）

### 测试与工具
- 新增 tests/test_kernel_gates.py：内核四钩子回归（≥10 用例，tmp_path 隔离库）
- 新增 scripts/reconcile_sync_failed.py：sync_failed ↔ 宿主 deliverables 对账
