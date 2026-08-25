# pm — PM全流程研发调度中枢（流程A · 2026-08-13 架构）

> 2026-08-14 重建：以 `rules/01_workflows.md` 流程A（8-13 12:03）+ 历史技能库 `cowork-pm`（8-13 12:11）+ `test-lead`（8-13 11:47）为权威源（原 user/ 镜像路径引用已于 2026-08-17 FIX-dup 解除）。
> 旧 v4.2「dagou 内置引擎」版（8月5 源）已归档至 `archive_v4.2_dagou/`，不再生效。

## 引擎
**无内置引擎** — 机械门禁 / 批次签发 / 状态机流转全部归 `agent-harness backend/engine`。2026-08-17 引擎替换（已裁定）：旧 `/api/flow` 下线，旧 orchestrator_gate/signer/guards/validators 模块删除；旧 test_gates 实现（test_gates.py/signer.py）已退役归档，`/api/test-gates/*` 四端点 URL 保留、内部改接新内核（TestGatesET → kernel.et()），响应为新内核出参；统一入口 AgentEngine `POST /api/engine/et`（ET Payload，禁带 expression；出参 code ∈ success/reject/block/timeout/error）：
- 机械门禁：`POST /api/engine/et`（artifact_validate/gate_guard 校验块，kernel.et 裁决）
- 批次签发：`POST /api/engine/et`（content_issue 块，引擎三元组签名 et_sign；Agent 禁止自行签发/算签名，旧 generate_signature 语义作废）
- 状态机：跃迁走 state_intercept.allowed_pairs（from→to 对强校验），每步 harness-step-sync.sh（外壳不变，内部=先 et 判定 → success 后 POST /api/instances/{instance_id}/transition 落库，自动双写 StateStore+审计）；非 success 时 new_task_state=null，不得当推进依据

> 四门禁已落地（2026-08-17）：Q4 用例格式 / B3 证据链 / 交叉隔离 / 批次签发已迁入 ET 契约体系。Agent 调用 `POST /api/test-gates/{case-format|evidence-chain|cross-isolation|sign-batch}`（端点已挂载，URL 不变），或按 TestGatesET 同等 Payload 直调 `POST /api/engine/et`。响应为新内核出参：`code ∈ success/reject/block/timeout/error`，细节看 `validate_result` / `issue_meta` / `failure_info`；非 success 一律不得推进。批次签发响应 `issue_meta.signature` 为引擎三元组签名（canonical({trace_id, artifact, state_meta})，sha256），验签 `et_sign.verify_issue`；旧五元组签名一次性失效（预期行为）；Agent 禁止自算签名。设计稿存档备查：`agent-harness docs/test_gates_et_design.md`。

## 主线（13节点 · 流程A）
```
pm_bootstrap → spm → pm_prd_confirm → dpm
→ [ui_designer ∥ test_lead_design]          # 步骤5a/5b 并行
→ fe → be                                    # 步骤6a/6b
→ pm_quality_gate                            # 步骤7-9：五维审查+自测确认+冒烟门禁（质量左移，失败→流程B）
→ test_lead_full                             # 步骤10：whitebox/api/ui 三路全量收口（引擎门禁把关）
→ ops → qa                                   # 步骤12 部署 → 步骤13 验收（DEPLOY→ACCEPTANCE 为状态机唯一合法流向）
→ retro → __end__                            # 步骤14：流程C 收尾，sv-supervisor 复核 APPROVED 才归档
```

## 与旧版（v4.2 dagou）的关键差异
1. 删除 `gov_infer` 治理预处理节点（步骤1 直接 PM 宣布启动 + 输入校验）
2. 测试段收敛：旧 `tcd + executor_smoke/full + supervisor_pre/post` → **test-lead + 三路**（whitebox-coverage / api-test-engineer / ui-test-engineer）
3. 代码审查位置：旧版在全量测试后 → **提测前**（步骤7-9，质量左移）
4. 冒烟失败：旧版本节点自回流 → **直接触发流程B**
5. 每步强制 harness-step-sync 状态同步 + sv-supervisor 审批/终裁贯穿全程
6. `invoked_skills` 全部指向已迁移技能（不再引用 test-supervisor / test-quality-gate 等已废弃角色）

## 目录结构
```
pm/
├── SKILL.md                  # 入口（本架构说明）
├── flow.yml                  # 13节点编排（含 harness_sync / 门禁 / 分支）
├── readme.md                 # 本文件
├── archive_v4.2_dagou/       # 旧 v4.2 dagou 版归档（flow.yml/SKILL.md/readme.md，只读）
├── self_engine_config/       # ⚠️ 已废弃（旧 dagou 引擎配置，保留仅供参考，不参与运行）
├── langgraph_config/         # ⚠️ 已废弃（历史参考）
└── output_delivery/          # 历史交付物示例（保留）
```
