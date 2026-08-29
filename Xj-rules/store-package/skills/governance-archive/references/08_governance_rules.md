---
paths: ["**/*"]
---

# 八、全局治理规则（G 系列）

> 本文件承载跨流程、跨角色的全局治理规则，由 AGENTS.md 全局按需加载。
> 规则编号格式：G##，与工程技能编号、YAML 规则编号处于不同命名空间。

---

## G29：测试执行模式显式声明规则

**适用：** 任何进入流程 E（测试模式）或流程 A 步骤 9 测试链的任务。

1. 任何测试任务必须显式声明执行模式： 【规范】
   ```
   execution_mode ∈ {func-only, api-only, tdd-only, api-tdd, all-full}
   ```
2. 用户未显式声明时，PM 默认按 `api-tdd` 执行，但必须在流程状态条中标记 `mode=default(api-tdd)`。 【规范】
3. `execution_mode` 必须写入项目根目录 `.flow_state.json` 的 `test_execution_mode` 字段，作为后续角色调度和 sv-supervisor 审计的依据。 【规范】
4. 模式声明后不得中途切换；如需切换，必须更新 `.flow_state.json` 并经 sv-supervisor 审批。 【规范】

---

## G30：ctx-reader 两包隔离规则

**适用：** 所有可分发配置、Skill 文件、规则文件、文档。

1. **公共包（GitHub 可分发）**：
   - 路径范围：`~/.agents/skills/`（唯一真源，2026-08-17 声明，见 00）、`~/.agents/rules/`、`~/.agents/AGENTS.md`（2026-08-29 起取代 `~/.dsh/AGENTS.md`）。
   - 禁止包含 `ctx-reader` Skill、配置、调用示例、文档、依赖声明。 【建议】
   - 默认输入必须为 `.prd.md`（需求文档），涉及 UI 自动化的项目还必须提供 `.ui-proto.json`。 【规范】
2. **私有本地包（不上传）**：
   - 路径范围：`~/.agents/skills/local/` 或用户自定义私有目录。
   - 可将 `ctx-reader` 作为可选内部扩展保留，但 SKILL.md 描述第一行必须标注 `[LOCAL-ONLY]`。 【规范】
   - 不得出现在任何公共技能推荐链/对照表（原 using-agent-skills 声明表 2026-08-20 已退役归档）、流程 A/B/C/E 的公共调用链、或任何面向外部用户的示例中。
3. **引用审计**：
   - 任何提交公共包前，必须全局搜索 `ctx-reader`、`ctx_scan`、`ctx-audit-manifest`，确认公共路径下零命中。 【规范】
   - 发现公共路径残留 → 立即迁移到 `~/.agents/skills/local/` 或删除。

---

## G31：统一闭环规则（API / 白盒 / UI 同链）

**适用：** 所有测试执行闭环，无论 mode。

1. **统一链路**：所有测试用例必须经过以下闭环： 【规范】
   ```
   test-case-designer / test-driven-development
   → test-lead（语义审核：Q1 覆盖充分性 / Q2 等价类 / 人工审查）
   → backend/engine 机械门禁（POST /api/test-gates/case-format）
   → test-executor（执行）
   → backend/engine 机械门禁（POST /api/test-gates/evidence-chain）
   → test-lead（收口 + 语义抽审）
   → acceptance-manager（验收）
   ```
   机械门禁由 backend/engine 物理执行，任何角色不得绕过；语义审核与收口归 test-lead。
2. **批次标识**：每个用例批次必须生成： 【规范】
   - `global_batch_id`：全局唯一批次号，格式 `BC-[mode]-[YYYYMMDD]-[NNN]`（例如 `BC-FUNC-20260718-001`）。`all-full` 模式下各子链生成子 `batch_id`，最终汇总为 `META-[YYYYMMDD]-[NNN]` 作为 `meta_batch_id`。
   - `CROSS_VALIDATION_HASH`：由 test-lead 提交、backend/engine `POST /api/test-gates/sign-batch` 签发，写入 `batch_meta.json`。
3. **交叉执行**：用例设计者与执行者必须是不同 Agent；同一 Agent 不得既设计又执行同一批次用例。 【规范】
4. **缺陷回流**：任何 FAILED 用例必须进入缺陷回流： 【规范】
   ```
   test-lead 分析归属 → PM 指派 → 开发修复
   → test-case-designer 补充/调整用例
   → test-lead 语义审核 → test-executor 精准回归
   → backend/engine 证据链校验 → 关闭或重指派
   ```
   精准回归范围由 test-lead 根据变更范围标签确定，避免非必要的全量回归。
5. **交付物一致性**：五种 mode 统一输出以下交付物：
   - `execution-list.json`（含 `global_batch_id`、`execution_mode`、需求/接口/UI 绑定字段）
   - `batch_meta.json`（全局批次元数据，含 `cross_validation_hash`、`baseline_diff_hash`、`env_label`）
   - `test-baseline-diff.json`（基线变更范围，用于精准回归）
   - `test-master-report.json`（统一顶层测试总报告，合并原 `report.json` + `evidence-index.json`）
   - 证据目录（UI 为截图/前后快照；API 为请求/响应日志；TDD 为覆盖率/stdout）
   - `defect-auto-grade.json`（自动缺陷分级，驱动流程 B）
   - `bug-fix-record.md`（有缺陷时）
   - `acceptance_report.json`

---

## G32：执行期问题发现登记与延伸规则

**适用：** 所有任务执行过程。不限流程、不限任务类型、不限是否计划复盘。

1. **即时登记义务：** 执行过程中发现的任何问题——契约与实现不符、产物无效、能力低于宣称、意外坑点、与预期不符的行为——无论当下是否已解决/已绕过，必须在发现当刻登记到 `~/.agents/retro-registry/runtime/_retro_experiences_<project>.json`（按项目命名变体，如 `_retro_experiences_example.json`），格式：发现内容 → 实证 → 当下处置。**禁止以「当时已处理」为由不登记**：已解决的问题正是经验本体；只调整当下决策而不登记，等于销毁复盘输入。 【规范】
   **登记字段契约（2026-08-12 新增，dispatcher GENERATE 消费硬要求）：** 每条必须含 `found_at` / `source` / `problem` / `evidence` / `resolution` / `content` / `role` / `project`；其中 `content` = problem + "\n实证：" + evidence + "\n处置：" + resolution（dispatcher 只读 `content` 字段，缺 `content` 的条目被静默过滤 → GENERATE 报「无输入」空跑）；`role` 取 be/pm/fe/te 等角色码，`project` 取项目短名。**禁止手填 `id`/序号字段**（2026-08-12 废除 pNNN_NNN 编码：并行会话凭记忆顺延撞号实证）；serial_number 由系统分配为 skill_id。 【规范】

2. **延伸义务（发现问题禁止点对点解决）：** 每个执行期发现的问题，处置时必须完成三层延伸： 【建议】
   - **同类模式扫描：** 同模式缺陷在其他文件/契约/规则中是否也存在？grep 验证，命中即同批处置（例：一份文档是幽灵 → 全部产物清单逐个 grep 生成路径）。
   - **影响面清零：** 被证伪/被弃用对象在 `rules/` 与 `skills/` 中的所有引用，逐条修订或删除，grep 零残留实证。
   - **根源规则化：** 该问题的防再发机制能写成 if/when 规则的，固化为规则或门禁；只有不可规则化的部分才允许留在经验文档。

3. **复盘核对义务：** 复盘第三部分必须先读取登记池逐条过账（每条标注已落地/未落地），再回扫本任务执行记录确认执行期发现全部已登记、全部纳入本次复盘；发现漏登 → 当场补登并记为复盘自身缺陷。 【规范】

4. **闭环判定：** 登记池存在未落地条目、或延伸三层任一层未完成时，禁止宣告任务「完成 / 闭环 / 收敛」。 【规范】

---

## G33：机制/规则修改前三问轻量评估规则

> **裁决标注（2026-08-17）：** 本规则触发域与 REFORM-GATE（`11_gate_framework.md` 第三节）完全重叠，无用户裁定，按"更严格条款优先"裁决——**REFORM-GATE 五要素框架为唯一有效收益评估与放行机制**（详见 `~/.agents/logs/rule_conflict_adjudication.jsonl` 冲突③）。~~G33 三问作为独立放行依据~~（已废止·见裁决记录）。本条保留仅为历史可追溯与第 3 项设计目标锚定（轻量化方向）仍生效。

**适用：** 任何对机制（流程、调度、门禁、引擎行为）和规则（rules/、skills/ 中的约束文本）的修改提案——**一律改走 REFORM-GATE 框架**。

1. **修改前必答三问（口头/简短书面即可，禁止评估本身变重）：**（已废止·见裁决记录——三问为 REFORM-GATE 收益五要素子集，直接填 REFORM-GATE 框架，不再单独作答）
   - **牵扯面大不大？** 该改动会波及哪些流程节点、技能、规则、存量项目？
   - **性能会不会骤降？** 改动是否引入显著变慢、token 暴涨、串行卡点变多？
   - **整体会不会显得笨重？** 改动是否让流程变长、规则变厚、使用门槛变高？
2. **评估后按三档决策是否要做：**（已废止·见裁决记录——放行/做废判定并入 REFORM-GATE ④判定档，本规则不再产生放行效力）
   - **牵扯面大 → 提交用户决定：** 必须把收益性描述清楚（带来什么具体收益、代价是什么），连同受影响清单一并提交用户裁定，禁止自主动手。 【规范】
   - **命中任一做废条件 → 不做：** ① 性能会骤降；② 流程和内容变得膨胀；③ 规则会存在冗余。三条命中任意一条，直接放弃或重新设计。
   - **自主放行条件 → 可自主决定执行修改：** 性能有提升 / 规则更轻便 / 改了更通用，三条中**任意占一条**，且无负面收益（不触发上面任一做废条件、牵扯面不大），即可自主执行，无需等待用户批准。
3. **设计目标锚定（2026-08-14 用户裁定，仍生效）：** 一切机制与规则的演进方向是 **快速、通用、轻量化**——宁可功能少一点，不可流程重一分。
4. **例外：** 纯文字勘误、格式修正、编号调整等无行为变更的修改免评估。

---

## 变更记录

| 规则 | 新增/删除 | 日期 | 说明 |
|------|----------|------|------|
| G17 | 删除 | 2026-07-18 | 全自动复盘自迭代机制移除，见 01_workflows.md 变更 |
| G29 | 新增 | 2026-07-18 | 测试执行模式显式声明 |
| G30 | 新增 | 2026-07-18 | ctx-reader 公共/私有包隔离 |
| G31 | 更新 | 2026-07-19 | 统一闭环规则：批次号改为 global_batch_id，batch_hash.json 改为 batch_meta.json，report.json+evidence-index.json 合并为 test-master-report.json，新增 test-baseline-diff.json 与 defect-auto-grade.json |
| G32 | 新增 | 2026-08-12 | 执行期问题发现登记与延伸：发现即登记复盘池+三层延伸（同类模式扫描/影响面清零/根源规则化），禁止点对点解决不登记；来源 archmap 无效文档未纳入复盘事件 | 【规范】
| G33 | 更新 | 2026-08-14 | 机制/规则修改前三问轻量评估 + 三档决策（牵扯面大→用户决定；性能骤降/膨胀/冗余→不做；提升·轻便·通用任一且无负面→自主执行）；目标锚定快速·通用·轻量化 |
