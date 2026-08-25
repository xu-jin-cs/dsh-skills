---
name: pm
description: PM全流程研发调度中枢（13 节点流程 · 公开骨架版，引擎接线默认 Xj-engine）
aliases: ["/pm"]
allowed-tools: ["Read","Write","Bash"]
---

# pm

> 公开分发骨架版。本 SKILL.md 描述 13 节点 PM 全流程调度、节点流转内核与引擎接线。
> 各节点角色能力由 `flow.yml` 中 `invoked_skills` 指向的技能 SKILL.md 定义（适配方按自身生态替换对应技能）。
> 私有/宿主相关能力（如审计看板、复盘经验库、审批体系）此处仅保留通用形态，不做硬绑定。

## 安装依赖

```bash
pip install -r requirements.txt   # PyYAML + jsonschema（flow_kernel.py 运行所需）
```


## 入参

- `input`: string，输入给 PM 工作流的项目需求或指令

## 静态执行链路（flow.yml 拓扑顺序）

```
pm_bootstrap → spm → pm_prd_confirm → dpm
→ [ui_designer ∥ test_lead_design]（并行组 design_and_test_design）
→ fe → be → pm_quality_gate（五维审查+自测确认+冒烟门禁）
→ test_lead_full（whitebox/api/ui 三路全量收口）
→ ops → qa → process_audit（流程合规审计）→ retro（收尾复盘）→ __end__
```

缺陷旁路：冒烟失败 / 全量失败 / 验收打回 → **流程B**（分级→修复→复核→回归），流程B 失败回流不进入下游。

## 流程内核（scripts/flow_kernel.py · 节点流转唯一机械入口）

每节点交付完成后、口头宣布"流转到 X"之前，必须先扳动内核照抄裁决：

```bash
python3 scripts/flow_kernel.py advance \
  --rules flow.yml \
  --state <项目根>/.flow_state.json \
  --node <当前节点> --outcome <分支键> \
  --deliverable <交付物路径>（可多个）
```

- **出参 code 即裁决**：`success`（按 next_node 流转 + 逐条执行 sync_commands）/ `reject`（交付物缺失或 Schema 不符，补齐后重扳）/ `block`（非法跳步或分支无出口，流程冻结排查）/ `error`（内核异常）。
- **规则全入参**：节点拓扑 / branch_conditions / 状态机 transitions / 交付物 Schema 模板全部在 flow.yml，内核零 PM 规则硬编码——改流程只改 flow.yml，禁止改内核。
- **禁止事项**：禁止口头推进节点（无内核 success 回执 = 未流转）；内核 block 后禁止强推。
- 查询节点出口：`python3 scripts/flow_kernel.py routes --rules flow.yml --node <节点>`。
- **状态同步命令**由环境变量 `PM_HARNESS_SYNC_CMD` 配置（见 flow_kernel.py 头部说明），未配置时内核仅输出状态流转提示，适配方应指向所接引擎（如 Xj-engine）的状态同步入口。

## 引擎归属（默认 Xj-engine）

**本工作流无内置引擎**，机械门禁 / 状态机流转 / 交付物校验全部交由引擎裁决。默认接线为 `Xj-engine`（Python 包 `engine`，入口 `engine.kernel.et`，CLI `xj-engine`）：

- 安装与使用见同仓库 `Xj-engine/README.md`。
- 健康检查：`xj-engine health`。
- 按 ET 契约调用：`xj-engine run --payload '<ET Payload>'` 或 `from engine.kernel import et`。
- 引擎离线 → 流程冻结并提示启动，禁止静默降级为软执行。

> 引擎为可插拔：如接入其它引擎，通过环境变量（`ENGINE_HEALTH_CMD` / `ENGINE_START_CMD`，见 `scripts/engine_preflight.sh`）与 `PM_HARNESS_SYNC_CMD` 切换，业务规则不硬编码进引擎。

## 固化证据铁律（全节点生效）

凡任何节点在汇报中声称「已沉淀 / 已入库 / 已同步更新 / 已学习」，必须附机械校验证据，否则视为未固化、汇报打回。统一校验工具：

```bash
bash scripts/verify_experience_writeback.sh <本次产出物> <经验/索引文件> [关键词]
```

（mtime + 关键词双验证：经验文件需新于产出物且命中关键词，否则=未固化。）

## 硬性全局约束

1. 每步切换执行状态同步（经 flow_kernel 出参的 sync_commands），全链禁止跳步；
2. 机械门禁与裁决只读引擎结论，任何 Agent 不得自行判定 / 改判；
3. 冒烟失败直接触发流程B，禁止进入全量测试；
4. 停点1（用户确认需求方向）不可跳过；
5. 节点流转必须经 flow_kernel success 回执，禁止口头推进。

## 目录结构

```
pm/
├── SKILL.md            # 入口（本文件）
├── flow.yml            # 13节点编排（节点拓扑 / 分支 / 状态机 / 交付物模板）
├── requirements.txt    # 脚本运行依赖（PyYAML / jsonschema）
├── readme.md           # 架构说明
└── scripts/
    ├── flow_kernel.py                 # 节点流转内核（规则全入参）
    ├── engine_preflight.sh            # 引擎健康检查（默认 xj-engine）
    └── verify_experience_writeback.sh # 经验固化机械校验
```
