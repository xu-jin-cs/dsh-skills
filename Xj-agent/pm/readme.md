# pm — PM 全流程研发调度中枢（13 节点流程 · 公开骨架版）

> 公开分发骨架版。本目录为通用、自包含的 PM 全流程调度骨架，默认引擎接线为同仓库 `Xj-engine`。
> **不捆绑具体角色技能**：各节点角色执行能力由适配方自行接线对应技能/Agent；
> 审计看板、复盘经验库等宿主/生态能力按适配方自身环境替换，不做硬绑定。

## 引擎

**无内置引擎** — 机械门禁 / 批次签发 / 状态机流转全部交由引擎裁决。默认接线为 `Xj-engine`
（Python 包 `xj_engine`，入口 `xj_engine.kernel.et`，CLI `xj-engine`）：

- 机械门禁 / 批次签发 / 状态机：按引擎 **et 契约**调用（统一入口，禁带 expression；出参
  `code ∈ success/reject/block/timeout/error`，非 success 一律不得推进）。
- 状态机：跃迁走 `state_intercept.allowed_pairs`（from→to 对强校验）；success 后才落库状态
  （自动双写状态存储 + 审计）；非 success 时 new_task_state=null，不得当推进依据。
- 引擎离线 → 流程冻结并提示启动，禁止静默降级为软执行。
- 引擎可插拔：通过环境变量 `ENGINE_HEALTH_CMD` / `ENGINE_START_CMD` / `PM_HARNESS_SYNC_CMD`
  切换（见 `SKILL.md` 与 `scripts/engine_preflight.sh`）。

## 主线（13 节点）

```
pm_bootstrap → spm → pm_prd_confirm → dpm
→ [ui_designer ∥ test_lead_design]          # 步骤5a/5b 并行
→ fe → be                                    # 步骤6a/6b
→ pm_quality_gate                            # 步骤7-9：五维审查+自测确认+冒烟门禁（质量左移，失败→流程B）
→ test_lead_full                             # 步骤10：whitebox/api/ui 三路全量收口（引擎门禁把关）
→ ops → qa                                   # 步骤12 部署 → 步骤13 验收
→ process_audit → retro → __end__            # 流程合规审计 → 收尾复盘 → 归档
```

缺陷旁路：冒烟失败 / 全量失败 / 验收打回 → **流程B**（分级→修复→复核→回归），流程B 失败回流不进入下游。

## 关键机制

1. 节点流转唯一机械入口：`scripts/flow_kernel.py advance`（规则全入参自 flow.yml，成功回执才流转）
2. 测试段三路收敛：whitebox-coverage / api-test-engineer / ui-test-engineer（test-lead 统一下发）
3. 质量左移：代码审查在提测前（pm_quality_gate），冒烟失败直接触发流程B
4. 每步状态同步 + 审批贯穿全程
5. 固化证据铁律：凡声称"已沉淀/已入库"必须过 `scripts/verify_experience_writeback.sh` 机械校验

## 安装与运行

```bash
pip install -r requirements.txt   # PyYAML + jsonschema（flow_kernel.py 运行依赖）
python3 scripts/flow_kernel.py routes --rules flow.yml --node be   # 试跑：查询节点出口
```

## 目录结构

```
pm/
├── SKILL.md                  # 入口（本架构说明）
├── flow.yml                  # 13节点编排（节点拓扑 / 分支 / 状态机 / 交付物模板）
├── requirements.txt          # 脚本运行依赖（PyYAML / jsonschema）
├── readme.md                 # 本文件
└── scripts/
    ├── flow_kernel.py                 # 节点流转内核（规则全入参）
    ├── engine_preflight.sh            # 引擎健康检查（默认 xj-engine）
    └── verify_experience_writeback.sh # 经验固化机械校验
```
