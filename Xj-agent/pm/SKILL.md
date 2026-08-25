---
name: pm
description: PM全流程研发调度中枢（流程A · 2026-08-13 架构 · test-lead 三路测试收敛版）
aliases: ["/pm"]
allowed-tools: ["Read","Write","Bash"]
---
<!-- REBUILT 2026-08-14 from rules/01_workflows.md 流程A + 历史技能库 cowork-pm + test-lead（8-13 权威源；原 user/ 镜像路径引用已于 2026-08-17 FIX-dup 解除）。旧 v4.2 dagou 版已归档至 pm/archive_v4.2_dagou/ -->

# pm
## 入参

- `input`: string，输入给PM工作流的项目需求或指令

## 静态执行链路（flow.yml 拓扑顺序）

```
pm_bootstrap → spm → pm_prd_confirm → dpm
→ [ui_designer ∥ test_lead_design]（并行组 design_and_test_design）
→ fe → be → pm_quality_gate（五维审查+自测确认+冒烟门禁）
→ test_lead_full（whitebox/api/ui 三路全量收口）
→ ops → qa → process_audit（流程合规七维审计，2026-08-15 R4 接线）→ retro（流程C，sv-supervisor 复核 APPROVED 才归档）→ __end__
```

缺陷旁路：冒烟失败 / 全量失败 / 验收打回 → **流程B**（分级→修复→复核→回归），流程B 失败回流不进入下游。

## 流程内核（flow_kernel.py · 2026-08-16 盘活 · REFORM-GATE 判A）

**节点流转唯一机械入口**：每节点交付完成后、口头宣布"流转到 X"之前，必须先扳动内核照抄裁决：

```bash
python3 ~/.agents/skills/pm/scripts/flow_kernel.py advance \
  --rules ~/.agents/skills/pm/flow.yml \
  --state <项目根>/.flow_state.json \
  --node <当前节点> --outcome <分支键> \
  --deliverable <交付物路径>（可多个）
```

- **出参 code 即裁决**：`success`（按 next_node 流转 + 逐条执行 sync_commands）/ `reject`（交付物缺失或 Schema 不符，补齐后重扳）/ `block`（非法跳步或分支无出口，流程冻结排查）/ `error`（内核异常）。
- **规则全入参**：节点拓扑 / branch_conditions / 状态机 transitions / 交付物 Schema 模板全部在 flow.yml，内核零 PM 规则硬编码——改流程只改 flow.yml，禁止改内核；换一套规则文件内核行为完全跟随。
- **禁止事项**：禁止口头推进节点（无内核 success 回执 = 未流转）；禁止跳扳内核直接执行 harness-step-sync.sh；内核 block 后禁止强推。
- 查询节点出口：`python3 flow_kernel.py routes --rules flow.yml --node <节点>`。

**流程B retro 匹配硬证据步骤（MATCH 模式，2026-08-16 硬化）**：本环境（DSH）无 UserPromptSubmit 钩子，retro 匹配不会自动触发。Bug 诊断派发前，PM 必须执行：
```bash
bash /Users/xujin/.agents/retro-skills-registry/scripts/retro-match.sh "<用户原始输入>"
```
并在回复中**引用其输出结论行**（`MATCH FOUND <技能名> (<分数>)` 或 `NO MATCH` / 近似候选清单）。跳过本步骤必须在输出中显式写明理由（留痕），禁止静默省略。近似候选（0.20~0.50）不自动注入，由 PM 语义判断适用后手动加载对应 SKILL.md；≥0.50 才自动注入 Resolution Steps。

**retro 匹配执行判定禁止手写（2026-08-16 裁定，gate-switch 机械门禁）**：流程启动时先 `touch /tmp/retro_match_marker_<流程标识>` 标记起点；「已执行 retro 匹配」禁止口头声称，Bug 诊断派发前必须扳动 `python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py --spec ~/.agents/skills/gate-switch/specs/retro_match_gate.json --set work_start=/tmp/retro_match_marker_<流程标识>` 照抄结论——判 A（`~/.agents/retro-skills-registry/runtime/_active_match.md` 新于起点 = 本次真实执行留痕）才允许派发诊断；判 B = 未执行/旧产物冒充，须先执行 retro-match.sh 再重新扳动。

## 引擎归属（backend/engine · agent-harness）

**本工作流无任何内置引擎**，机械门禁/批次签发/状态机流转全部走 `agent-harness backend/engine`（FastAPI `http://127.0.0.1:8001/api`）。**2026-08-17 引擎替换（已裁定，禁止翻案）**：旧 `/api/flow` 端点已下线，旧 orchestrator_gate/signer/guards/validators 模块已删除；旧 test_gates 实现（test_gates.py/signer.py）已退役归档，`/api/test-gates/*` 四端点 URL 保留、内部改接新内核（TestGatesET → kernel.et()），响应为新内核出参，可按同等 Payload 直调；统一入口为 AgentEngine **`POST /api/engine/et`**（body=ET Payload，必填 artifact+trace_id；出参 code ∈ success/reject/block/timeout/error；**expression 已永久移除，payload 携带即 422**），自检 `GET /api/engine/health`：

| 能力 | 新引擎调用 | 说明 |
|---|---|---|
| 用例机械格式（Q4 十项） | `POST /api/engine/et`（artifact_validate/gate_guard 校验块） | 引擎内核 kernel.et 机械裁决 |
| 机械证据链（Q5-Q6） | `POST /api/engine/et`（artifact_validate 校验块） | 截图数/md5防复用/audit.log |
| 交叉执行隔离 | `POST /api/engine/et`（gate_guard 校验块） | 设计者≠执行者 |
| 批次签发 | `POST /api/engine/et`（content_issue 块） | 引擎侧三元组签名（et_sign），Agent 禁止自行签发、禁止自行算签名（旧 generate_signature 语义作废） |
| 状态机/跳步拦截 | ① `POST /api/engine/et`（state_intercept.allowed_pairs 对 from→to 强校验）→ ② code==success 后 `POST /api/instances/{instance_id}/transition` 落库（自动双写 StateStore+审计） | 非法跃迁即 block；非 success 时 new_task_state=null，下游不得把状态字段当推进依据 |

> **四门禁已落地（2026-08-17）**：Q4 用例格式 / B3 证据链 / 交叉隔离 / 批次签发已迁入 ET 契约体系（TestGatesET 四入口 + 内核 8 新原语）。Agent 调用 `POST /api/test-gates/{case-format|evidence-chain|cross-isolation|sign-batch}`（端点已挂载，URL 不变），或按 TestGatesET 同等 Payload 直调 `POST /api/engine/et`。响应为新内核出参：`code ∈ success/reject/block/timeout/error`，细节看 `validate_result` / `issue_meta` / `failure_info`；**非 success 一律不得推进**。批次签发响应 `issue_meta.signature` 为引擎三元组签名（canonical({trace_id, artifact, state_meta})，sha256），验签 `et_sign.verify_issue`；旧五元组签名一次性失效（预期行为）；Agent 禁止自算签名。设计稿存档备查：`agent-harness docs/test_gates_et_design.md`。

引擎离线 → 门禁与签发不可用，必须先 `bash ~/agent-harness/start.sh`，禁止静默降级为软执行。

**流程启动（2026-08-20 用户裁定）**：engine_preflight 已剔除（原第零步耗时拖累进度，REFORM-GATE 判 A）。引擎健康兜底由 harness-step-sync.sh Step 0 承担——离线即 exit 2 报错并提示 `bash ~/agent-harness/start.sh`，禁止静默降级；harness_sync 闸同步判 B 阻断。

## 固化证据铁律（2026-08-15 专家会诊后新增，全节点生效）

**凡任何节点在汇报中声称「已沉淀 / 已入库 / 已同步更新 / 已学习」，必须附机械校验证据，否则视为未固化、汇报打回。**
统一校验工具：`bash ~/.agents/skills/pm/scripts/verify_experience_writeback.sh <本次产出物> <经验/索引文件> [关键词]`（mtime + 关键词双验证）。
背景教训：spm 复盘学习曾长期"声称吸收但未回写经验文档"，6 份复盘报告 4 份零固化——口头声明不可信，唯有机械校验可信。

## 改造前置门禁（REFORM-GATE 触发点 · 2026-08-15 用户裁定焊入）

**凡对本工作流的改造建议（改 flow.yml / 改各角色 SKILL.md / 新增机制·门禁·脚本 / 重构），必须在动手或出口之前先填 [REFORM-GATE] 收益框架块，并过 `reform_gate.json` 判 A 才允许执行；判 B 必须带理由降级为观察或放弃。**
顺序铁律：**先填块 → 判 A → 再动手**。先实施后补票视同未过门（2026-08-15 本工作流固化改造即为此反面案例：改造落地后才补判，虽判 A 追认有效，顺序本身违规）。
框架格式与校验命令见 `~/.agents/rules/11_gate_framework.md` 第三节。

## 范围边界接线（scope_boundary 门禁 · 2026-08-19 A1 契约断链修复）

**契约链：task-breakdown 产出范围文件清单 → PM 传递 → 编码阶段（fe/be）机械核验。**

1. **下发**：task-breakdown 交付的任务拆解 JSON 必含 `"范围文件清单"` 字段（指向落盘清单文件，格式见其 SKILL.md——每行一个相对仓库根路径）。PM 向 fe/be 下达开发指派时，必须将清单文件路径写进指派指令；**无范围文件清单 = 契约断链，编码阶段不得开工**（先打回 task-breakdown 补产出）。
2. **核验（判定禁止手写）**：fe/be 提交代码、进入 pm_quality_gate 之前，必须扳动
   ```bash
   python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py \
     --spec ~/.agents/skills/gate-switch/specs/scope_boundary.json \
     --set repo=<项目git仓库> --set allow=<范围文件清单路径> --set base=HEAD
   ```
   照抄输出——判 A（变更全在范围内）才允许流转 pm_quality_gate；判 B 则越界清单原文上报 PM：确认纳入（更新范围文件清单后重扳）或删除越界改动（即使代码已写也要删掉）。
3. 门禁本体与例外白名单见 `~/.agents/skills/scope-boundary-gate/SKILL.md`。

## 状态同步（每步强制）

每步切换执行：
```bash
bash ~/agent-harness/scripts/harness-step-sync.sh "$PROJECT_NAME" "<目标状态>" "<步骤说明>" "<角色>"
```
各节点目标状态见 flow.yml 中 `harness_sync` 字段。脚本调用方式不变；语义为**先判定后落库两步**（口径3，已裁定）：harness-step-sync.sh 内部先 `POST /api/engine/et`（state_intercept.allowed_pairs 跃迁强校验），code==success 后再 `POST /api/instances/{instance_id}/transition` 落库（自动双写 StateStore+审计）才算状态推进；非 success 时 new_task_state=null，**无 success 回执视为未推进**。

状态机：`PENDING→PRD_REVIEW→DESIGN→DEV_FRONTEND/DEV_BACKEND→PM_CONFIRM→CODE_REVIEW→SMOKE_TEST→FULL_TEST→DEPLOY→ACCEPTANCE→CLOSED`（+FROZEN/ROLLBACK；2026-08-15 B2 修复：CODE_REVIEW 提前至 FULL_TEST 前，与 pm_quality_gate 实际拓扑一致）

## 审批体系（sv-supervisor 终裁）

| 产出 | 初审/执行方 | 终裁方 |
|---|---|---|
| 《总需求PRD》 | PM 完整性审核 | sv-supervisor |
| 任务拆解+规模判定 | task-breakdown | sv-supervisor |
| 《详细交互设计文档》 | 前后端审核 | sv-supervisor |
| 测试用例 | test-lead 语义审核 + 引擎机械格式 | sv-supervisor |
| 测试审计报告 | test-lead 语义抽审 + 引擎机械证据链 | sv-supervisor（POST_GATE_AUDIT 抽样复核） |
| 验收报告 | acceptance-manager | sv-supervisor 终裁→触发流程C |
| 流程C 归档 | PM | sv-supervisor 复核 APPROVED 才归档 |

## 硬性全局约束

1. 每步必须执行 harness-step-sync.sh 状态同步，全链禁止跳步；
   - **同步声称判定禁止手写（2026-08-16 裁定，gate-switch 机械门禁）**：「已同步」禁止口头声称，必须扳动 `python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py --spec ~/.agents/skills/gate-switch/specs/harness_sync.json --set project=<项目根路径> --set expect_state=<本次同步目标状态>` 照抄结论——判 A（本地 `.flow_state.json` 合法 + 引擎实例 current_state 真实落库）才允许进入下一步；判 B = 未同步/不一致/引擎离线/实例冻结，violations 原文即修复指令（引擎离线先 `bash ~/agent-harness/start.sh`，禁止静默降级）。
2. 机械门禁与签发只读引擎裁决，任何 Agent 不得自行判定/签发/改判；
3. 冒烟失败直接触发流程B，禁止进入全量测试；
4. 停点1（用户确认需求方向）不可跳过；
5. 禁止 MCP 协议与未知外部调用；pm 节点唯一 Bash 例外为 /archmap 调度；
6. **级联带槽**：每次指派节点 Agent 时，指派指令必须写明「本节点交付后按自身 SKILL.md 专家槽位章节走 expert-loop L1→L3，落盘 `<项目根>/.expert-loop/`」；流程C retro 前 PM 收集各节点 internalizations.jsonl 按 problem_family 合并计数，作为复盘材料输入（详见 `~/.agents/skills/expert-loop/SKILL.md` 工作流宿主章节）。

---

## 专家槽位（expert-loop级联开槽 · 契约权威 expert-router/docs/slots-protocol.md）

- **框架**：`~/.agents/skills/expert-loop/SKILL.md`（L0执行→L1问诊→L2改进→L3内化；字段契约/入库闸门/内化铁律以 slots-protocol.md 为准，此处不重复）
- **槽位类型**：调度轻槽
- **挂载点**：SLOT-1: 任务拆解/并行编排等调度决策定稿后、下发指派前；SLOT-2: 流程C retro 前，聚合各节点 internalizations 并合并计数
- **落盘**：`<项目根>/.expert-loop/pm-expert_advice.jsonl` + `pm-internalizations.jsonl`（本 Agent 另有产物目录约定的从其约定）
- **优先领域**（route.py 路由不佳时手动指定方向）：G08 项目管理、F05 系统设计思维
- **先查自己**：SLOT-1 路由前先按 problem_family 检索自身 internalizations.jsonl，命中直接自用（领域技能融入式 / 专项技能升格式），同类问题不重复问专家
- **铁律**：裁决禁止静默忽略；accepted 必须落实改动并回链 expert_id；不归因不收尾
- **回链落盘判定禁止手写**：必须扳 `python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py --spec ~/.agents/skills/gate-switch/specs/slot_attribution.json --set project=<> --set expert_id=<>` 照抄输出（落实质量留软层）。
<!-- AUTO-RETRO-INJECT:START -->

## 📚 复盘经验自动注入区（retro-skills-registry 直写 · 生成即复利）

<!-- 由 dispatcher_generate.py 全量维护，勿手改；最近注入: 2026-08-25T03:51:09.088984 -->

## 第零步：加载复盘经验技能表（全量调用，无触发词 · SPM 同款）
> 机制（2026-08-21 用户裁定）：复盘生成技能不靠触发词调用。本角色被派任务执行时，
> 全量载入 `learned-skills/registry.json` + `entries/*.md` 全部条目——表内每条技能即本次任务强制约束。
> 1. 读取 `~/.agents/skills/pm/learned-skills/registry.json`；
> 2. 按索引逐条读入 `entries/*.md` 全部条目，逐条自检复用。
> 3. 加载留痕（机械强制，块H 2026-08-22）：执行 `python3 ~/.agents/retro-skills-registry/scripts/trace_skill_load.py --role pm`，加载事件落计数台账 skill_load_ledger.jsonl（只计数不设率；漏留痕由月度审计后查）。

### 🧭 领域技能（60 条 · 检查维度，融入当前任务点到即止）

- 🔴 **retro-pm-004-data-channel-verify**｜数据生产端与消费端通道校验 — 新增数据源必须验证消费端正确读取和展示
- 🟠 **retro-be-010-pipeline-source-classification-gate**｜数据管道入口必须有源分类门禁，异源/规格外数据在入口拦截，禁止吞入后污染库
- 🟠 **retro-pm-002-engineering-capability-gate**｜复盘产出的可复用能力必须强制固化为Skill/Agent，第5层工程能力固化门禁—可固化未固化禁止归档
- 🟠 **retro-pm-003-delete-dependency-audit**｜删除后端功能前必须审计前端依赖链，grep 确认所有引用组件后再执行删除；功能不工作时先执行流程B诊断而非直接删除
- 🟠 **retro-pm-005-import-verify-gate**｜新文件/新函数 ≥50行提交前必须运行 python3 -c 导入验证，防 import 错误运行时才暴露
- 🟠 **retro-pm-072-交付验收必须区分阻断项与优化项PPT工作流08manifestmd只有**｜交付验收必须区分阻断项与优化项：二元 PASS/FAIL 会让「不报错即 PASS」掩盖不可交付缺陷；
- 🟠 **retro-pm-082-技能改造的消费审计必须覆盖入口包装文件修改-SKILLmd-后-gre**｜修改技能/配置的定义文件后，必须 grep 全部消费方入口（命令包装/快捷入口/引用文档）同步更新，审计三类消费方：数据
- 🟠 **retro-pm-085-禁令类规则必须配机检锚点三级闭环否则形同虚设纯文字禁令禁止跨模板混入依**｜禁令类规则必须配机检锚点三级闭环否则形同虚设：纯文字禁令（禁止跨模板混入）依赖模型自觉，违规只能事后人工发现。
- 🟠 **retro-pm-093-用户要求删除某内容如-KafkaCI流水线时-禁止只删当前讨论的板块必**｜用户要求删除某内容时，禁止只删当前讨论的位置；
- 🟠 **retro-pm-102-复盘扫描范围禁止锚定在当前任务边界内除本次执行问题外必须增加两个固定维**｜复盘扫描范围禁止锚定在当前任务边界内：除「本次执行问题」外必须增加两个固定维度——①被证伪断言清单（先入为主宣称有用/存
- 🟠 **retro-pm-103-执行过程中发现的问题必须当刻登记到复盘输入池并做三层延伸-禁止点对点解**｜执行过程中发现的问题必须当刻登记到复盘输入池并做三层延伸，禁止点对点解决后丢手：①同类模式扫描（同模式缺陷在其他文件/契
- 🟠 **retro-pm-112-技能匹配不到-匹配没命中设计匹配检索机制时禁止凭直觉配置多通道权重必须**｜技能匹配不到、匹配没命中：设计匹配/检索机制时禁止凭直觉配置多通道权重——必须先实测分词器输出形态与评分公式极值，确认单
- 🟠 **retro-pm-113-触发太少-命中太少-或反向的一个关键词触发好几个召回与精度不是二选一召**｜触发太少、命中太少、或反向的一个关键词触发好几个：召回与精度不是二选一——召回靠同义词簇（每技能多条 2-10 字用户口
- 🟠 **retro-pm-249-触发信号把业务工作流pm-多-agent嵌入对接引擎-问题模式易把嵌**｜触发信号：把业务工作流（pm 多 agent）嵌入/对接引擎。
- 🟡 **retro-PM-002-同一失败原样重试复现-1-次即触发熔断禁止第三次串行重试-必须先定位根**｜同一失败原样重试复现 1 次即触发熔断：禁止第三次串行重试，必须先定位根因或切换路径。
- 🟡 **retro-pm-015-retro-generate-exit**｜GENERATE 是复盘总结的内置收尾步骤。复盘内容输出后自动发起 GENERATE 调用，调用成功即为复盘总结完成。
- 🟡 **retro-pm-073-工作流交付物-JSON-示例必须逐字段对照渲染脚本的真实字段白名单验证**｜工作流交付物 JSON 示例必须逐字段对照渲染脚本的真实字段白名单验证，spec 示例不等于合法入参。
- 🟡 **retro-pm-081-通用提取工具改造禁止渗入单一领域素材库跨风格通用工具覆盖国风科技卡通极**｜通用提取工具改造禁止渗入单一领域素材库：跨风格通用工具（覆盖国风/科技/卡通/极简多模板）的素材黑白名单必须按每套输入实
- 🟡 **retro-pm-084-输出质量类问题先查工作流强制节点再怀疑组件精度PPT成品窜台四不像-初**｜输出质量类问题先查工作流强制节点再怀疑组件精度：PPT成品窜台四不像，初判嫌疑在提取器精度，grep实证后真凶是/ppt
- 🟡 **retro-pm-086-用户提交的方案文档与已落地改造重合时先对照评估再取舍按已落地半落地未落**｜用户提交的方案文档与已落地改造重合时先对照评估再取舍：按『已落地/半落地/未落地』三分对照表逐条判定，只采纳真增量（本案
- 🟡 **retro-pm-087-同文件批量并行Edit时短oldstring必须带相邻行上下文唯一化规**｜同文件批量并行Edit时短old_string必须带相邻行上下文唯一化：规则25归并后并行编辑同文件，短串（如skill
- 🟡 **retro-pm-088-复刻仿造类循环任务每轮迭代生成前必须重新-Read-参考模板原图原文档**｜复刻/仿造类循环任务每轮迭代生成前必须重新 Read 参考模板原图/原文档，禁止凭会话记忆理解参考标准。
- 🟡 **retro-pm-090-对同一素材同一方案的修补失败-2-次-第**｜对同一素材/同一方案的修补失败 2 次，第 3 次必须更换素材/方案本身（换图源/换结构），禁止在原素材上打第 3 个补
- 🟡 **retro-pm-091-macOS-办公套件不自动重载已打开文档-覆盖同名-pptx**｜向用户交付会覆盖其已打开文件的产物时：办公套件不自动重载已打开文档，覆盖同名文件后用户看到的仍是旧窗口；
- 🟡 **retro-pm-092-长循环任务必须主动维护断点文档任务定义参考路径进度状态失败黑名单恢复步**｜长循环任务必须主动维护断点文档（任务定义/参考路径/进度状态/失败黑名单/恢复步骤五段式），在上下文膨胀前落盘，禁止被动
- 🟡 **retro-pm-094-渲染-PASS-不等于交付完成桌面-pptx**｜生成管线 PASS 只代表工作目录产物更新；
- 🟡 **retro-pm-095-无侵入零改动方案四态实证拆解法任何宣称零代码无侵入纯概念映射的融合或治**｜任何宣称零代码/无侵入/纯概念映射的方案，执行前必须逐条拆解落地动作并判定四态之一：纯零侵入/载体冲突/存量已有/需开发
- 🟡 **retro-pm-096-复刻验证方法论验证生成工具能力时-用真实高质量产物ppt工作流机械导出**｜复刻验证方法论：验证生成工具能力时，用真实高质量产物（ppt工作流）机械导出为工具模板格式→走工具全链路生成副本→字段级
- 🟡 **retro-pm-097-规则写作必须结论即动作当规则要求评估是否并行时-必须同时写明判定为可并**｜规则写作必须结论即动作：当规则要求'评估是否并行'时，必须同时写明'判定为可并行后立即执行并行'，否则评估容易沦为只出报
- 🟡 **retro-pm-098-并行规则必须双向闭合既要禁止该并行的不并行-也要禁止不该并行的硬并行**｜并行规则必须双向闭合：既要禁止'该并行的不并行'，也要禁止'不该并行的硬并行'。
- 🟡 **retro-pm-099-体系定义完成不等于可执行任何测试度量体系发布前必须先在真实项目跑零测**｜体系「定义完成」不等于「可执行」：任何测试/度量体系发布前必须先在真实项目跑零测试基线并人工核对 gate 必须为 fa
- 🟡 **retro-pm-100-某项上游能力被证伪弃用后-必须同步扫描并修订所有强制消费该能力的下游规**｜某项上游能力被证伪/弃用后，必须同步扫描并修订所有强制消费该能力的下游规则：「决策不依赖 X」与「规则强制消费 X」不能
- 🟡 **retro-pm-101-任何某产物某能力有用的断言必须实证三要素后再采信哪份具体产物-它的生**｜任何「某产物/某能力有用」的断言必须实证三要素后再采信：①哪份具体产物 ②它的生成代码路径 ③它的真实消费方证据；
- 🟡 **retro-pm-104-通用给任何结构化-JSON-产物-人读报告页面新增渲染器时**｜【通用】给任何「结构化 JSON 产物 → 人读报告/页面」新增渲染器时，两类高频缺陷：①渲染器自带默认值补全缺失字段，
- 🟡 **retro-pm-105-通用用户给出参考产物HTML截图文档要求按这种格式展示时-凭印象**｜【通用】用户给出参考产物（HTML/截图/文档）要求「按这种格式展示」时，凭印象仿写会漏区块，且容易做到一半才发现「参考
- 🟡 **retro-pm-106-G32-执行期发现登记池-clauderetro-skills**｜G32 执行期发现登记池 ~/.claude/retro-skills-registry/runtime/_retro_
- 🟡 **retro-pm-107-功能升级后-skillsarchmapSKILLmd-未同步风险清单仍**｜功能升级后 skills/archmap/SKILL.
- 🟡 **retro-pm-108-通用用户报告显示时间数字不对时凭假设逐层读源码排查-不先确认用户观察**｜【通用】用户报告「显示/时间/数字不对」时凭假设逐层读源码排查，不先确认用户观察点，会把定位起点搞错：同一句「时间不对」
- 🟡 **retro-pm-109-系统生成类字段禁止手写编造时间戳序列号ID创建日期等由系统或权威源持有**｜系统生成类字段禁止手写编造：时间戳/序列号/ID/创建日期等由系统或权威源持有的字段，写入前必须读系统时钟（dateti
- 🟡 **retro-pm-110-向-append-only-系统写入前必须对齐字段契约审计日志看板既有**｜向 append-only 系统写入前必须对齐字段契约：审计日志/看板/既有 API 等只增系统，写入前先 dump 一
- 🟡 **retro-pm-111-批量改造活仓库长任务三件套registry索引DB-等可能被并行会话写**｜批量改造活仓库长任务三件套：registry/索引/DB 等可能被并行会话写入的目标，执行前快照计数（条数+目录数）、执
- 🟡 **retro-pm-114-批量改写-全量替换存量数据前按实证数据分层处置有真实验证记录如-mat**｜批量改写、全量替换存量数据前：按实证数据分层处置——有真实验证记录（如 match_count>0、有真实命中日志）的条
- 🟡 **retro-pm-115-用户把两个概念拆着说导致漏命中连续-substring-短语匹配要求字**｜用户把两个概念拆着说导致漏命中：连续 substring 短语匹配要求字面连续，拆散表述（「回滚完了但是还有残留」）永不
- 🟡 **retro-pm-116-复盘扫描时发现登记池没建-复盘扫描失败G32-登记池必须在首次发现问题**｜复盘扫描时发现登记池没建、复盘扫描失败：G32 登记池必须在首次发现问题当刻创建文件（至少含空 entries 骨架），
- 🟡 **retro-pm-117-用户纠正范围只做了一部分用户指令出现全称量化词是全部所有整个时**｜用户纠正范围只做了一部分：用户指令出现全称量化词（「是全部」「所有」「整个」）时，必须以用户最新一次明确口径为准重列全量
- 🟡 **retro-pm-118-误删-api-test-engineer条件句不等于删除授权**｜误删 api-test-engineer：条件句不等于删除授权
- 🟡 **retro-pm-119-子-agent-迁移时编造引擎端点-实证apitest**｜子 agent 迁移时编造引擎端点
实证：/api/test-gates/hash-mismatch 不存在，被写入 t
- 🟡 **retro-pm-120-删除角色时漏删顶层软链副本-实证claudeskillstest-s**｜删除角色时漏删顶层软链副本
实证：~/.claude/skills/test-supervisor 是指向 user/
- 🟡 **retro-pm-124-并行派发子任务前必须先跑一个最小探针任务验证分身通道可用能返回-权限够**｜并行派发子任务前必须先跑一个最小探针任务验证分身通道可用（能返回、权限够用），探针失败直接串行执行；
- 🟡 **retro-pm-125-发现存量数据使用废弃格式废弃-ID-时-必须先列处置选项交用户裁决**｜发现存量数据使用废弃格式/废弃 ID 时，必须先列处置选项交用户裁决，禁止自行转换格式写入；
- 🟡 **retro-pm-126-为流程加治理机器度量报告对账时先建机器后算账-机器每次执行的轮次成本超**｜为流程加治理机器（度量/报告/对账）时先建机器后算账，机器每次执行的轮次成本超过其防返工收益
- 🟡 **retro-pm-127-设计度量指标时按文档承诺取数-未实勘数据源真实存在与语义-落地时口径返**｜设计度量指标时按文档承诺取数，未实勘数据源真实存在与语义，落地时口径返工
- 🟡 **retro-pm-128-并行下发多分身时各方产物契约可能不一致-单向规格下发防不住-合并时才发**｜并行下发多分身时各方产物契约可能不一致，单向规格下发防不住，合并时才发现
- 🟡 **retro-pm-129-文件类成品PPT简历报告等交付时仅在回复正文或表格中文字提及保存路径-**｜文件类成品（PPT/简历/报告等）交付时仅在回复正文或表格中文字提及保存路径，用户感知不到交付已完成，会追问成品在哪、是
- 🟡 **retro-pm-246-触发信号插件打包构建产物内容核对-课件与包内容对账-问题模式构建器收集**｜触发信号：插件打包/构建产物内容核对、课件与包内容对账。
- 🟡 **retro-pm-247-触发信号构建器做调用路径重写文本替换后分发-问题模式重写产物指向的运行**｜触发信号：构建器做调用路径重写/文本替换后分发。
- 🟡 **retro-pm-248-触发信号某协议闸存在但从没被触发过-用户问为什么没走-X-闸**｜触发信号：某协议/闸'存在但从没被触发过'、用户问'为什么没走 X 闸'。
- 🟡 **retro-pm-250-触发信号分析多个机制引擎计划闸工作流并列时如何路由-问题模式易画成**｜触发信号：分析多个机制（引擎/计划闸/工作流）并列时如何路由。
- ⚪ **retro-pm-083-用户中断并把已下达的修改项降级为可选建议时-禁止贸然继续执行也禁止擅自**｜用户中断并把已下达的修改项降级为可选建议时，禁止贸然继续执行也禁止擅自丢弃，先用 AskUserQuestion 确认范
- ⚪ **retro-pm-089-单一页面单点的修改子循环超过-3-轮未获用户验收-必须停止继续生成**｜单一页面/单点的修改子循环超过 3 轮未获用户验收，必须停止继续生成，输出当前版 vs 参考的方向对比请用户确认方向后再

### 🎯 专项技能（0 条 · 场景触发时升格为执行主线，按卡内步骤逐项深入）


<!-- 共 60 条（领域 60 / 专项 0）；全文见 ~/.agents/retro-skills-registry/skills/<skill_id>/SKILL.md；技能表见 learned-skills/registry.json -->

<!-- AUTO-RETRO-INJECT:END -->
