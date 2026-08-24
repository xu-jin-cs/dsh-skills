---
paths: ["tests/**", "*.spec.ts", "playwright/**", "e2e/**"]
---

## 四、测试通用规则

- 冒烟测试必须在真实目标 OS 执行 【规范】
- 桌面/Electron/3D 项目必须激活 Q7 门禁（窗口生命周期/IPC/资源释放/帧率独立 4 类测试点） 【规范】
- 竞态条件类用例至少执行 3 次，结果一致才判定通过
- 证据防作弊：截图 md5 复用=伪造，数量<步骤=跳步，无执行报告=虚假执行
- 覆盖 7 种测试点：边界值/等价类/需求逻辑/场景/异常/兼容/接口安全
- 每个按钮设计独立用例；确认/取消对话框拆两个分支
- **新文件测试强制门禁（2026-07-07 新增）：** 新增核心文件（≥50行逻辑代码）必须配不少于 3 个测试用例，覆盖主流程+异常+边界。零测试的新文件视为未完成。例外：纯配置/文档/脚本文件。test-lead 在语义审核时核对新增文件清单与测试用例清单；格式/边界机械门禁由 backend/engine 执行。 【铁律】
- **Serial 模式级联防护**：`describe.serial` 块设计时每个块应可独立执行，不依赖前置块状态。块内如果某个测试失败，后续用例必须有状态恢复机制（`beforeEach` 验证前置条件 + 条件等待），不能全链跳过。Playwright config 中 `retries: 1` 兜底 flaky test 【规范】
- **Bug修复精准回归门禁**：修复验证时回归范围不得超过变更范围×1.5。回归命令必须用 `--grep` 精确过滤目标用例，禁止全量执行（`npx playwright test`）。除非变更覆盖公共基础设施（路由/状态管理/中间件），才允许全量回归且必须注明理由。违反视为 test-executor 违规，扣1分 【规范】

## 五、工具集成规则

### 工具型 MCP 接入
- 定义清晰触发词，按需调用，不嵌入 Agent 强制工作流
- 复盘输出完整台账（生成了什么/改了什么/删了什么）

### CodeGraph MCP（2026-06-15）
```
触发词 → 命令：upload→incremental-index, 分析→impact+callgraph,
生成→map+search, 使用→refs+deps
```
- 新项目首次操作前先建索引
- 索引过期可增量更新（<250ms）
- 适用于：所有涉及代码改动的任务

---

# 八、测试体系增强与质量保障机制（2026-06-25）

> **状态：已生效** ✅ 基于实际运行中识别的6大根因问题，增强现有测试体系，不推翻已有流程。

## 1. sv-supervisor 主动工作模式

### 事件驱动主动介入（P0）

sv-supervisor 不再仅被动接收 PM 提交，而是监听以下核心状态跃迁，自动触发主动审查：

| 状态跃迁 | 触发动作 | 产出 |
|---------|---------|------|
| PRD_SIGN_OFF（PRD终审通过） | sv-supervisor 自动审查PRD完整性 | 《PRD预审意见》→ 抄送PM/SPM |
| SMOKE_GATE_PASS（冒烟门禁通过） | sv-supervisor 验证冒烟用例与PRD对齐 | 《链式测试策略对齐确认书》 |
| CHAIN_TEST_DONE（链式测试完成） | sv-supervisor 抽查5%用例的原始执行证据 | 《链式测试随机抽样复核报告》 |
| CODE_REVIEW_DONE（代码审查通过） | sv-supervisor 审查Bug指派记录+根因分析 | 《Bug指派与根因质量审计》 |
| BUG_FIX_CLOSED（Bug关闭） | sv-supervisor 验证回归证据链完整性 | 《Bug关闭合规验证记录》 |

### 定时巡检机制（P1）

sv-supervisor 在项目活跃期（开发/测试/修复阶段）执行定时巡检：

- **周期：** 每4小时自动巡检一次（项目活跃期）
- **巡检范围：**
  - 当前流水线状态 vs 步骤计数器一致性
  - 证据链完整性（缺失率、md5复用率）
  - 质量门禁通过率趋势
  - 违规积分累计值（≥3分自动触发冻结建议）
- **产出：** 《主动巡检报告》→ 抄送PM，发现异常立即输出干预建议

### sv-supervisor 输出规范（P0）

sv-supervisor 每次介入输出必须包含： 【建议】

```
━━ sv-supervisor 主动审查 ━━━━━━━━━━━━━━━━━━
触发事件：[PRD_SIGN_OFF / SMOKE_GATE_PASS / ...]
当前状态风险评分：[高/中/低] — 评分依据：[证据链缺失/门禁异常/正常]
需PM补充材料：[清单]
裁决建议：[中止/放行/有条件放行] — 依据：[具体规则条目]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

缺少上述规范块 → 视为 sv-supervisor 失职，积分扣2分。

---

## 2. 后置审计机制（谁审计 test-lead）

### POST_GATE_AUDIT 阶段（P0）

在 Q5-Q6 之后、部署验收之前，插入独立的后置审计阶段：

```
链式测试 → test-lead(Q1-Q3 语义审核) → backend/engine(Q4 机械格式) → test-executor → backend/engine(Q5-Q6 机械证据链) → test-lead(Q5 语义抽审)
→ POST_GATE_AUDIT（新增） → 部署验收
```

### 审计内容

| # | 审计项 | 方法 | 阈值 |
|---|--------|------|------|
| A1 | test-lead Q1-Q3 语义审核质量 + backend/engine Q4 机械格式校验 | 抽样禁止自选样本，必须执行 `python3 ~/.agents/skills/sv-supervisor/scripts/random_sample.py` 按审计频率表抽样率机械抽样（种子由脚本生成并留痕，{seed, pool_hash, algo_version, timestamp} 四元组可复现），sv 只对抽到的固定样本复核审核结论的正确性 | 误判率 < 5% | 【铁律】
| A2 | Q5-Q6 证据链审计质量 | 抽样禁止自选样本，必须执行 `python3 ~/.agents/skills/sv-supervisor/scripts/random_sample.py` 机械抽样（`--min 3` 下限硬阻断，四元组留痕可复现），sv 只对抽到的固定样本完整重走证据链校验 | 与原始结论一致 | 【铁律】
| A3 | 逻辑矛盾检测 | 对比Q4设计用例与Q6执行结果 | 差异率 < 5% |
| A4 | 防作弊规则执行检测 | md5复用检测记录、时间异常检测记录必须存在 | 记录完整 | 【建议】

### 复核产出契约（P0，2026-08-16 REFORM-GATE 裁定新增）

- 复核报告必须为结构化 JSON，必填字段：`audit_id`、`generated_at`（报告生成时间）、`sample`（抽样四元组 + 样本清单 + pool_size/sample_size）、`findings[]`、`review_ratio`、`coverage_verdict`（verdict + gate_line_ref + blind_spot_note ≥20字）。 【规范】
- 每条复核结论（finding）强制 `evidence_refs` ≥1 个锚点（`case_id` + `file` + `line` + `line_digest`，line_digest 为该行内容 sha1 前 8 位，防行号漂移）；**无锚点结论视为未复核**。
- 报告出口前必须经机械门禁判 A（注：post_gate_audit.json 包装的 post_gate_audit_check.py 属 sv-supervisor 技能，未随本包发行，可自行按同模式写薄壳 spec）：`python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py --spec ~/.agents/skills/gate-switch/specs/post_gate_audit.json --set report=<报告> --set case_root=<用例库根>`；判 B 按 violations 修复后重扳，禁止带违例出口。 【铁律】
- 机械门禁只判抽样过程与锚点真实性；复核结论的语义合理性留 sv 软层，禁止开关化。 【铁律】

### 复核率留痕（P0，2026-08-16 REFORM-GATE 裁定新增）

- 每次审计落 `~/.agents/logs/post_gate_audit.jsonl`，字段：`{ts, audit_id, pool_size, sample_size, review_ratio, anchor_invalid_rate, verdict}`。
- 告警：连续 3 次 `review_ratio` 低于审计频率表规定抽样率，或单次骤降 >50% → 触发 `DRIFT_ALERT`，sv 介入排查并记入违规积分。

### 审计执行者

- **主审计：** sv-supervisor（自动触发）
- **备选审计：** 如 sv-supervisor 不可用，由 test-lead（自审模式）执行，但自审模式下不得签署通过结论，必须标记为「待确认」 【规范】

### 审计频率

| 项目类型 | 抽样率 | 触发时机 |
|---------|--------|---------|
| S级（<30分钟） | 10% | 链式测试完成后自动 |
| M级（<90分钟） | 15% | 链式测试完成后自动 |
| L级（>90分钟） | 20% | 链式测试完成后自动 |

### test-lead 自检清单（P1）

test-lead 提交 Q5-Q6 语义抽审报告前必须自检： 【规范】

```
□ 证据链Hash连续性检查（所有证据目录hash一致）
□ 跳步检测通过率 = 100%（截图数量 == 步骤数）
□ 交叉合规声明附MCP调用日志
□ 时间异常检测记录存在且无异常
□ 无执行报告=虚假执行检测已执行
□ 自检通过/不通过
```

未通过自检 → 不得输出终版审计报告。

---

## 3. PRD-测试桥接检查清单（填补空白地带）

### GATE_BRIDGE_CHECKLIST（P0）

在「流程合规门禁通过后、链式测试启动前」强制填写。由 PM 负责提交，sv-supervisor 审核。

```
━━ GATE_BRIDGE_CHECKLIST ━━━━━━━━━━━━━━━━━━━━━━━━
1️⃣ PRD验收标准覆盖率
   覆盖率：[XX%]（阈值：≥95%）
   用例ID映射表：[附链接]
   未覆盖条款：[编号+原因]

2️⃣ 自测报告真实性
   自测执行日志Hash：[sha256]（防伪造）
   MCP调用记录：[附链接]
   自测通过率：[XX%]（阈值：≥90%）

3️⃣ 代码审查质量
   Reviewer签名：[姓名]
   阻塞级Bug数：[0]（阈值：0）
   架构变更说明：[无/附ADR链接]

4️⃣ Bug根因分析质量（如适用）
   使用5-Whys模板：[是/否]
   根因归因：[禁止出现"用户操作不当"等模糊归因] 【建议】
   修复方案 vs 根因证明：[附验证记录]

5️⃣ 交叉执行合规
   designer ≠ executor：[已验证]
   executor ≠ supervisor：[已验证]
   人工独立执行场景时间间隔 > 30分钟：[间隔XX分钟]（自动化链式流程由 CROSS_VALIDATION_HASH 保证隔离，不以此阻断）

结论：全部通过 / 需整改（未通过项编号：___）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**强制规则：** 未填写完整或覆盖率<95% → 链式测试自动暂停，返回PM补全。sv-supervisor 审核不通过视为桥接失败。

### test-case-designer 反向追溯规则（P1）

test-case-designer 设计用例时，必须显式引用 PRD 验收标准条款 ID。格式： 【规范】

```json
{
  "case_id": "TC-XXX-001",
  "prd_requirement_ids": ["PRD-REQ-01", "PRD-REQ-03"],
  ...
}
```

Q1 审核时，未绑定条款的测试点视为无效用例，直接驳回。

---

## 4. 质量基线阈值（量化标准）

### QUALITY_BASELINE_THRESHOLDS（P0）

| 指标 | 阈值 | 超限后果 |
|------|------|---------|
| 用例设计一次通过率 | ≥ 90% | < 90% → test-case-designer 扣1分 |
| 证据链完整率 | 100%（缺1条=FAIL） | < 100% → 整批用例重执行 |
| 截图 md5 复用率 | 0%（禁止任何复用） | 发现1条 → test-executor 0分开除 | 【建议】
| 跳步率 | 0%（截图数==步骤数） | 发现1条 → test-executor 0分开除 |
| 交叉执行时间间隔 | 人工独立执行场景建议 >30 分钟；自动化链式流程不以此扣分 | 人工场景未达建议值 → 警告；自动化场景无扣分 |
| 门禁拦截健康区间 | 3% ~ 7% | < 2%门禁过低 → 复盘调整；> 10% → 触发流程复盘 |
| 违规积分熔断 | ≥ 3分 | 自动冻结流水线，sv-supervisor 人工解除 |
| POST_GATE_AUDIT 误判率 | < 5%（分母=带 evidence_refs 的复核结论总数，锚点化后误判率首次可度量） | ≥ 5% → test-lead 扣2分 |

### 阈值漂移告警（P1）

sv-supervisor 在每次巡检时计算周环比：

- Q1通过率周环比下降 > 5% → 触发 `DRIFT_ALERT`，sv-supervisor 自动介入排查
- 证据链完整率周环比下降 > 3% → 触发 `DRIFT_ALERT`

---

## 5. Agent隔离与交叉执行增强（防绕过）

### 硬性隔离规则（P0）

| 规则 | 说明 | 违规后果 |
|------|------|---------|
| test-case-designer 与 test-executor 分离 | 同一会话中不得由同一段代码同时承担设计和执行 | backend/engine 记录隔离违规 |
| 执行入口与设计入口必须不同 | 禁止设计→执行的直接函数调用，必须经过 backend/engine 签发的批次号/CROSS_VALIDATION_HASH 隔断 | 标记为违规 | 【规范】
| 会话级隔离声明 | 每次执行前输出声明：设计者=AgentA / 执行者=AgentB / 监督者=AgentC（三者互异） | 缺少声明的执行视为无效 |

### 交叉验证Hash（P0）

每次链式测试流转增加 `CROSS_VALIDATION_HASH`：

```
test-case-designer 输出 → 生成 case_batch_hash
test-lead 语义审核通过 → 提交 backend/engine 签发 supervisor_approval_hash
test-executor 接收 → 校验 case_batch_hash == 接收到的hash
test-executor 执行 → 生成 execution_evidence_hash
test-lead 语义抽审 → 校验 execution_evidence_hash 与证据目录 hash 一致
```

hash 不一致 → 立即标记为「绕过隔离」，test-lead 扣2分，整批结果作废。

---

## 6. 违规预防硬拦截机制

### 前置校验钩子（P0）

在以下节点设置硬拦截（PM自动执行）：

| 节点 | 拦截条件 | 拦截消息 |
|------|---------|---------|
| 链式测试启动前 | GATE_BRIDGE_CHECKLIST未完成 | `validation_failed: BRIDGE_CHECKLIST_INCOMPLETE` |
| 部署启动前 | POST_GATE_AUDIT 未通过 | `validation_failed: POST_GATE_AUDIT_PENDING` |
| Bug关闭前 | 回归证据链不完整 | `validation_failed: REGRESSION_EVIDENCE_MISSING` |
| 验收流程前 | 违规积分 ≥ 3分 | `validation_failed: POINTS_FUSE_BLOWN — 需sv-supervisor解除` |

### 违规积分熔断流程

```
累计积分 ≥ 3分
  → sv-supervisor 收到自动通知
  → sv-supervisor 输出《违规分析报告》
  → 决定：解除熔断 / 要求整改 / 建议项目中止
  → PM 执行 sv-supervisor 裁决
  → 积分清零或部分保留
```

---

## 7. 角色职责速查表（更新版）

| 角色 | 负责 | 不负责 |
|------|------|--------|
| PM | 流程流转+节点自检+桥接检查清单提交 | 代码实现、测试用例设计执行 |
| test-case-designer | 用例设计+PRD条款反向追溯 | 用例执行、流程合规 |
| test-executor | 执行已审核用例+生成证据链 | 用例设计、流程状态同步 |
| test-lead | Q1-Q3 语义审核 + Q5-Q6 语义抽审 + 缺陷回流收口 | 机械门禁（backend/engine）、验收判定（acceptance-manager）、PM流程合规性审计 |
| sv-supervisor | 事件驱动主动介入+POST_GATE_AUDIT+定时巡检+违规熔断裁决+桥接清单审核 | 代码实现、测试执行 |
| 验收经理 | 最终通过/不通过判定 | Bug排查、代码编写 |
