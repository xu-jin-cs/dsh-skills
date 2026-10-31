# Stage 运行时契约（assemble / snapshot）

本契约是 Xj-engine flow 节点与 stage 运行时（默认 stage-context-isolation 插件）之间的边界。
引擎只依赖本契约，不依赖插件的内部实现。

## 1. 装配（pre）

```bash
python3 <plugin_bin>/assemble_stage_context.py --config <stage_config.json> [--report <report.json>]
```

`stage_config.json` 必填：

| 字段 | 说明 |
|---|---|
| stage_id | 当前环节 id |
| workflow_id | 工作流 id |
| artifacts_root | 项目产物根目录（骨架所在） |
| current_stage_dir | 当前环节目录（artifacts_root 下） |
| task_instruction | 本环节任务指令 |

输出：stdout = 装配后的干净上下文（含全局基线、INDEX 摘要、上游交付物、任务）。
退出码：0=成功；2=BLOCK（依赖缺失/版本作废/路径越界/manifest 解析失败）。

## 2. 快照（post）

```bash
python3 <plugin_bin>/snapshot_manager.py snapshot \
  --artifacts-root <root> --stage-dir <stage_dir> \
  --stage-id <stage_id> --workflow-id <workflow_id>
```

退出码 0=成功；非 0 由宿主决定是否冻结。

## 3. 留痕

引擎节点自行写 `~/.agents/logs/stage_isolation.jsonl`（assemble/spawn/snapshot）与
`~/.agents/logs/engine_flow_runs.jsonl`（run_start/run_complete）。
宿主若自行调用运行时，必须写同一格式的 assemble/spawn 事件，否则 `engine_entry` 闸判 B。

## 4. 替换

`plugin_bin` 只要求存在 `assemble_stage_context.py` 与 `snapshot_manager.py` 两个入口；
只要满足本契约，可用其他运行时替换。
