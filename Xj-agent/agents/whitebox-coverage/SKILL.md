---
name: whitebox-coverage
description: "白盒覆盖率端到端执行技能。单 Agent 在指定工程完成 R0 基线 → R1-R3 分层轮次 → 终判报告全链路，产出 test-master-report.json。触发：白盒测试、覆盖率验证、/whitebox <项目路径>。"
---

# 白盒覆盖率端到端执行技能（单 Agent 验证模式）

[whitebox-coverage] — 白盒覆盖率 R0→R3 全链路执行

## 模式声明

本技能为**端到端验证 / 独立执行模式**：设计、执行、审计由同一 Agent 完成，交叉执行与引擎门禁在此模式下由 Agent 自检代替；正式项目测试必须切回多角色链（tcd/TDD → test-lead + 引擎门禁 → executor → acceptance）。

**模式标记硬约束（2026-08-15 用户裁定 A 案 · 入口分流）**：本模式产出的 `test-master-report.json` 顶层 `execution_mode` 字段**必须写 `"whitebox-verification"`**，禁止冒充多角色链模式值（func-only / api-only / tdd-only / api-tdd / all-full）。该报告仅作验证/彩排/引擎不可用环境的参考依据；正式验收由 acceptance_verdict 门禁机械拒收 whitebox-verification 报告——自检顶替门禁的通道已从规则层焊死。

规则权威源（本文件只给执行骨架，细节冲突以它们为准，禁止双写）：
- `../test-driven-development/SKILL.md` — Step 0（基线/Schema/豁免生命周期/术语字典）+ Step 1（分层轮次闭环执行规范）
- `../test-lead/SKILL.md` — 语义审核/收口；机械门禁（格式/证据链）归引擎 et 契约执行（Xj-engine：`xj_engine.kernel.et`）。四门禁已落地（case-format / evidence-chain / cross-isolation / sign-batch）：Agent 直调引擎 et 契约，响应 code ∈ success/reject/block/timeout/error（非 success 一律不得推进）；批次签发 signature 为引擎三元组签名（sha256），Agent 禁止自算签名
- `../acceptance-manager/SKILL.md` — tdd 抽查要点与 P0 硬拦截
- 模板：`../test-driven-development/templates/`（coverage-tiers.json / coverage-exemptions.json / test-master-report.sample.json）
- 脚本：`../test-driven-development/scripts/normalize_coverage.py`

## 输入

- `project_path`（必填）：目标工程根目录
- 自动探测：Python（pytest + pytest-cov）或 JS/TS（jest）测试栈；源码目录（src/ 或包声明目录）

## 模式门禁（2026-08-14 新增 · 机械分流，禁止闭眼全量）

进入 Phase 0 之前必须先做模式判定，判定依据仅为文件存在性，禁止凭感觉选择。**（2026-08-15 升级：判定禁止手写，必须经门禁机制机械判定照抄输出（whitebox_mode spec）：退出码 0=A 进 diff 增量模式；2=B 走 full 全量且 violations 即缺失基线清单，必须原文写入报告⑥段。）**

1. **增量回归（有基线时强制）**：`<project>/archmap/full_index.json` 存在 **且** `<project>/test-master-report.json` 存在已完成 R0→R3 基线 → **强制进入「版本更新增量模式（diff）」**，执行范围唯一依据 `archmap/diff_impact.json`（先跑 `/archmap <project> diff` 产出）；**禁止从 Phase R0 起跑全量**
2. **首版全量（唯一例外入口）**：无测试基线（`test-master-report.json` 不存在或 R0→R3 未完成）→ 走 Phase R0→R3 全量；若 archmap 基线也不存在，先 `/archmap <project>` 全量建基线，为下一工作期 diff 增量做准备
3. 判定结果与依据写入 `test-master-report.json` ⑥ 环境适配备注（mode=diff/full + 判定依据文件清单），供验收经理核验

## Phase 0：环境预检（任一不满足 → 停止并报告，禁止编造产物）

1. 测试运行器可用：`python3 -m pytest --version` 且 `pytest --cov` 可加载，或 `npx jest --version`
2. 确定覆盖率目标目录 `<src>`（如 `src/`、`app/`、包名目录）
3. 无 tests/ 目录不阻断（基线将全缺口，属正常）
4. 生成批次号：`BC-TDD-<YYYYMMDD>-001`

## Phase R0：基线轮

1. **分层配置**：扫描 `<src>` 下模块，按业务关键性提出 P0/P1/P2 映射（P0=主链路/鉴权/资金/数据写入；P1=核心业务非主路径；P2=工具/边缘），以模板起手写 `<project>/coverage-tiers.json`。`exclude` 至少含 `**/tests/**`、`**/dto/**`、`**/generated/**`，且必须 ⊆ `.coveragerc` 或 `pyproject.toml` 的 omit（脚本自检①强制）
2. **豁免初始化**：脚手架/平台 shim/确认死代码 → 逐条写入 `coverage-exemptions.json`（必填 reason + apply_round + approved_by；验证模式 `approved_by` 记 `"e2e-validation"`，并在最终汇报中列为待人工确认项）
3. **两段式基线生成**：

```bash
cd <project>
# Python（JS/TS：npx jest --coverage --coverageReporters=json → coverage/coverage-final.json，归一化自动识别 istanbul）
python3 -m pytest tests/ --cov=<src> --cov-branch --cov-report=json:evidence/baseline/coverage_raw.json --cov-report=
python3 ../test-driven-development/scripts/normalize_coverage.py \
  evidence/baseline/coverage_raw.json --tiers coverage-tiers.json \
  --exemptions coverage-exemptions.json --baseline \
  --batch-id <batch_id> --env-label test --root . \
  --out evidence/baseline/coverage.json
```

4. **基线自检**：exit 0/1 均正常（1=gate fail 是缺口信号）；exit 2 = 自检①失败，修 tiers exclude 后重跑；读 `files[].missing_branches` 按 tier 分组缺口清单

> ⚠️ **pytest-cov 分支数据静默丢失坑（2026-08-12 实证）**：pytest 9.x + pytest-cov 7.x 组合下 `pytest --cov --cov-branch` 可能静默产出无分支数据的 raw JSON（文件缺 `num_branches`/`missing_branches` 键），归一化将记 `branch_coverage_missing` 审计且所属 tier gate 强制 fail。检出后改用直跑模式重新生成：
> ```bash
> python3 -m coverage run --branch --source=<src> -m pytest tests/ && python3 -m coverage json -o evidence/<阶段>/coverage_raw.json
> ```
5. 向用户汇报缺口分布（各 tier 缺失弧数、Top 缺口模块）后再进 R1

## Phase R1-R3：分层轮次循环（严格串行）

每轮固定七步：

1. **锁定缺口**：仅当轮 tier 的 missing_branches——R1=P0 全部弧，R2=P1，R3=P2。禁止跨 tier 提前设计
2. **设计+写测试**：每条缺失弧 ≥1 条用例，断言必须针对分支行为本身（禁止只调用不断言的凑覆盖率用例）；测试文件写入工程 tests/ 目录，随用例记录 `target_missing_arcs`
3. **全量执行+测量**（每轮必须全量跑，分母不变防虚高）：

```bash
python3 -m pytest tests/ --cov=<src> --cov-branch --cov-report=json:evidence/tdd/coverage_raw_r<N>.json --cov-report=
python3 ../test-driven-development/scripts/normalize_coverage.py \
  evidence/tdd/coverage_raw_r<N>.json --tiers coverage-tiers.json \
  --exemptions coverage-exemptions.json --batch-id <batch_id> --round <N> \
  --prev <上一轮coverage.json（第1轮用基线）> --new-cases <本轮新增用例数> \
  --root . --out evidence/tdd/coverage_round<N>.json
python3 ../test-driven-development/scripts/normalize_coverage.py \
  --diff <上一轮coverage.json> evidence/tdd/coverage_round<N>.json \
  --out evidence/tdd/diff_round<N>.json
```

4. **回填 rounds[]**：从 diff 顶层 `summary{fixed_arcs,new_missing_arcs,remaining_arcs}` + 本轮实测 `tiers` 取数，追加到 `test-master-report.json.coverage.rounds[]`（结构照 test-master-report.sample.json）
5. **门禁判定**（阈值引用声明：各 tier 达标线以技能层权威源 `gate_thresholds.yaml`（本技能目录，键 `whitebox_gate_thresholds`）为准（P0=100 / P1=85 / P2=75，单位 %；技能层持有，引擎层不再承载），由 normalize_coverage.py 读取并判定；本技能文本不持有裸数值判定逻辑；回退默认值时产物 `meta.gate_threshold_source` 必留痕 `default_fallback`）：
   - R1：`P0 branch_pct 达到 whitebox_gate_thresholds.P0` 才进 R2；不达标回流（死代码/平台分支走豁免流程，禁止无理由批量豁免）
   - R2：`P1 branch_pct ≥ whitebox_gate_thresholds.P1`；实测 `meta.coverage_efficiency_risk=true` → 停止加用例，转豁免评审，每条效率豁免弧记录 audit_log
   - R3：`P2 branch_pct ≥ whitebox_gate_thresholds.P2`，最多回流 1 轮，余量走豁免审批
6. **断点续跑**：重进会话先读 `evidence/tdd/coverage_round*.json` 与 `test-master-report.json.coverage.rounds[]`，从最后一轮继续，不重跑已通过轮次
7. 每轮实测文件按 `coverage_round<N>.json` 命名，禁止覆盖历史轮

## 终判与报告

1. 最终轮实测复制为 `evidence/tdd/coverage.json`（门禁读取入口）
2. 组装 `test-master-report.json`（骨架照样例模板）：`summary` / `quality_gate` / `coverage{rounds, final}` / `audit_log` / `conclusion`；存在 `coverage_efficiency_risk` / `exemption_over_limit` / 跨批次退化 → 顶层 `coverage_risk_notes` 必填处置说明
3. 验收判定照 acceptance-manager tdd 要点：`final.tiers.P0.gate != pass` → 直接 FAIL
4. **Markdown 报告必备区块（六段固定结构，缺一视为报告不完整）**：输出 `<项目名>_白盒测试报告_<批次>.md`，必须包含：
   - **① 核心数据总览表**：批次/日期/结论、测试用例总数（含各轮新增拆分）、通过/失败/跳过与 pass_rate、发现 Bug 总数（分级+闭环状态）、遗留覆盖缺口数、累计修复弧数、总行/总分支覆盖率、豁免数、风险标记
   - **② 终态覆盖率表**：P0/P1/P2 行 line_pct、branch_pct、目标、门禁结果
   - **③ 分层轮次表**：每轮聚焦 tier、新增用例、累计用例、修复弧、新增缺口、遗留弧
   - **④ 缺陷统计**：量化汇总表（业务 Bug / 覆盖缺口缺陷 按 P0/P1/P2 分级 × 已闭环/遗留）；业务 Bug 明细表（缺陷描述/等级/发现轮次/状态/回归用例）；遗留缺口明细表（文件/弧 from→to/分支内容，逐条列出，禁止只写汇总数字）
   - **⑤ 审计与证据**：Q1-Q6 门禁结果表、分层门禁与豁免占比、风险标记、evidence_index 证据清单（路径+MD5）、audit_log 摘要
   - **⑥ 环境适配备注**：采集方式变更、基线重建等溯源说明
   - 数据来源：全部数字取自 `test-master-report.json` 与 `evidence/tdd/coverage.json`（遗留弧明细取 raw coverage 的 missing_branches），禁止凭记忆填数

> **报告数字一致性判定禁止手写（2026-08-16 裁定，机械门禁）：Markdown 报告交付前必须经门禁机制照抄结论（whitebox_report_consistency spec，脚本 `scripts/whitebox_report_check.py`）——判 A（用例总数/通过率/缺陷数/行分支覆盖率与 test-master-report.json、coverage.json 机械比对一致）才允许交付报告；判 B 按 violations 改报告或补证据后重扳。**

5. **HTML 报告必备（2026-08-12 新增，与 Markdown 并列强制）**：输出 `<项目名>_白盒测试报告_<批次>.html`，Appium 报告同款暗色可折叠页面，由渲染器生成：

```bash
python3 ../test-driven-development/scripts/render_whitebox_html.py \
  --report test-master-report.json --coverage evidence/tdd/coverage.json \
  --project <项目名> --out evidence/tdd/<项目名>_白盒测试报告_<批次>.html
cp evidence/tdd/<项目名>_白盒测试报告_<批次>.html ~/Desktop/
```

   **输出位置（固定）**：渲染原件存项目 `evidence/tdd/` 归档，渲染成功后立即 `cp` 到 `~/Desktop/<项目名>_白盒测试报告_<批次>.html` 作为交付副本（成品输出桌面同惯例），桌面副本缺失视为终判步骤未完成。

> **HTML 桌面交付判定禁止手写（2026-08-17 扳手改造，机械门禁）：cp Desktop 完成后、输出终判汇报回执前，必须经门禁机制照抄输出（whitebox_html_delivery spec）——判 A（桌面副本存在 + 非空壳 + 新于 evidence 归档原件）才允许声称终判报告已交付；判 B 即终判步骤未完成，按 violations 补 cp 后重扳，禁止用文字提及路径冒充交付。**

   必备区块（缺一视为报告不完整）：
   - **统计卡片条**：总用例 / 通过 / 失败 / 阻塞跳过 / 通过率 / Bug 总数 / 总行覆盖 / 总分支覆盖 / 总耗时
   - **Bug 严重度卡片**：严重/阻塞（P0）、一般（P1）、轻微/影响小（P2）各一张，含未闭环数
   - **终态覆盖率表**：P0/P1/P2 行覆盖 + 分支覆盖进度条 + 目标 + 遗留弧 + 门禁徽章
   - **分层轮次表**：每轮 tier / 新增用例 / 修复弧 / 新增缺口 / 遗留弧
   - **用例明细面板**：按 P0/P1/P2 → 模块两级折叠，每条用例可展开（状态/耗时/目标弧/断言明细/失败信息）
   - **Bug 明细表**：描述 / 严重度徽章 / 发现轮次 / 闭环状态 / 回归用例
   - **遗留覆盖缺口表**：逐弧列出（tier / 文件 / from→to），禁止只写汇总数字
   - **审计与证据**：Q1-Q6 门禁徽章 + audit_log + 证据清单（路径+MD5）+ 风险处置横幅
   渲染器只从 `test-master-report.json` + `coverage.json` 取数；cases[]/defects[] 为空时对应区块降级显示汇总，禁止编造明细
   - **数据回填配套**：每轮执行时必须把用例明细回填 `test-master-report.json.cases[]`（case_id/name/tier/module/status/duration_ms/round/target_missing_arcs/asserts），Bug 回填 `defects[]`（id/desc/severity(P0=严重阻塞/P1=一般/P2=轻微影响小)/status/found_round/regression_case），`summary` 增加 `total_duration_ms` 与 `blocked`——HTML 卡片与面板全部取自此三处
6. 汇报格式：

```
【白盒端到端验证完成】<project>
批次：BC-TDD-<YYYYMMDD>-001 | 轮次：N 轮（R1×a / R2×b / R3×c）
用例：总数 xx（新增 xx）| 通过 xx/xx（xx%）
Bug：发现 x 个（P0×a P1×b P2×c），已修复 x，遗留 x
终态：P0 xx% ✅❌ / P1 xx% ✅❌ / P2 xx% ✅❌ | 总行 xx% / 总分支 xx%
覆盖缺口：遗留 x 条弧（P0×a P1×b P2×c）| 豁免：xx 条（permanent x / batch x）
风险：efficiency_risk / exemption_over_limit / 无
产物：coverage-tiers.json、coverage-exemptions.json、evidence/、test-master-report.json、<项目名>_白盒测试报告_<批次>.md、<项目名>_白盒测试报告_<批次>.html
待人工确认：验证模式豁免 xx 条（approved_by=e2e-validation）
```

## 版本更新增量模式（diff，精准回归）

**适用**：项目已完成过全量 R0→R3（基线存在），本次为代码版本更新后的回归验证。首版测试仍走全量 R0→R3。

**执行时机（固定卡点）**：功能新增/修改完成后、复盘阶段前，先执行 `/archmap <project> diff [修改内容备注]`——变更（时间+修改内容+行区间+影响闭包）自动记入 `archmap/10_变更历史.md` 作为复盘台账输入；验收通过后 `/archmap <project> sync` 刷新基线并回补 01~09 分析文档，diff 记录、变更历史、分析文档构成一个整体。

**核心原则**：diff 差异来源唯一权威 = **archmap diff_impact.json**（行级快照比对 + AST 导入图影响闭包），禁止凭 git status / 人工判断圈定范围。未变更且不在影响闭包内的代码与用例**不重跑、不重设计**。

**范围圈定单刀双掷开关（2026-08-16 用户裁定「加扳手进去」· 判定禁止手写）：** 进入下方执行链路前，必须先经门禁机制机械判定照抄输出（whitebox_scope spec，脚本 `scripts/whitebox_scope_switch.py`）——掷点 A：脚本机械核验 diff_impact.json 存在/合法/不陈旧（computed_at 晚于最新源码变更）并输出「范围圈定照抄块」（AFFECTED_CLOSURE/SCOPE_SELECTED/SCOPE_UNTESTED_CHANGES/SCOPE_CMD），测试范围只能照抄该块，禁止手写增删；掷点 B：violations 即修复指令（先跑 archmap diff 再重扳），判 B 禁止进入执行链路；「无代码变更免测」由脚本判定输出，禁止自行宣布。背景：文本禁令（上行核心原则）长期无牙，Agent 凭 git status 圈范围导致跨文件影响闭包丢失，故判定权收归脚本（软点机械化）。

执行链路：

1. **产出 diff 影响面**：`/archmap <project> diff [修改内容备注]` → `<project>/archmap/diff_impact.json`（无基线时先跑全量 `/archmap <project>` 建立基线+快照；有变更时同步追加 `diff_history.jsonl` 并重渲染 `10_变更历史.md`）
2. **分流判定**：
   - `stats.changed_files == 0` → 汇报「无代码变更，免测」直接结束
   - `deleted_files` 非空 → 增量可继续（归一化自动从分母剔除已删文件），验收后 sync/full 重建基线；**变更量不设阈值回退**（2026-08-12 起废弃变更占比统计），安全网由 diff_gate 兜底
   - 其余 → 进入增量模式
3. **选择性执行**：仅运行 `test_selection.selected` 列出的测试文件（`python3 -m coverage run --branch --source=<src> -m pytest <selected...> && python3 -m coverage json -o evidence/tdd/coverage_raw_diff.json`）；`test_selection.untested_changes` 非空 → 必须为无测试变更文件先补用例再执行
4. **diff 缺口过滤**：归一化带 `--diff-scope <project>/archmap/diff_impact.json`，产出 `diff_scope` 区块（变更弧 ∩ 未覆盖弧清单 + diff_gate）
5. **diff 门禁**：`diff_gate = fail`（存在 P0/P1 变更弧未覆盖）→ 针对缺口弧补用例回流，直至 pass；tier 百分比在选择性套件下仅供参考、不参与门禁
6. **记录**：`test-master-report.json.coverage.rounds[]` 追加 `{"round": "diff-N", "mode": "diff", "diff_scope": {...}}`；报告按六段结构输出，① 总览表增加「变更文件数 / 影响闭包文件数 / 选中用例文件数 / 跳过用例文件数」四行
7. **快照语义**：diff 比对基准为最近一次 full/sync 写入的行级快照；验收通过后执行 `/archmap <project> sync` 刷新基线与快照、回补 01~09 分析文档，进入下一工作期

## 红线

- 禁止编造 coverage_raw.json、禁止手工修改任何 coverage 数值（=伪造证据）
- 全量轮次（R0→R3）禁止只测 diff 文件造成分母虚高，每轮必须全量执行测试；增量模式（diff）是唯一例外入口，必须以 archmap diff_impact.json 影响闭包为执行范围依据
- 禁止跨 tier 提前设计/执行用例（R1 只做 P0）
- 豁免必须逐条 reason + apply_round + approved_by，禁止单行批量豁免
- 用例必须有真实断言，弱断言凑覆盖率视为作弊
- 环境跑不起来 → 停止上报，不得继续

---

## 专家槽位（expert-loop级联开槽 · 契约权威 expert-router/docs/slots-protocol.md）

- **框架**：`../expert-loop/SKILL.md`（L0执行→L1问诊→L2改进→L3内化；字段契约/入库闸门/内化铁律以 slots-protocol.md 为准，此处不重复）
- **槽位类型**：完整槽 L1→L3
- **挂载点**：SLOT-1: R0 基线完成、R1-R3 分层策略定稿时；SLOT-2: test-master-report.json 终判交付后
- **落盘**：`<项目根>/.expert-loop/whitebox-coverage-expert_advice.jsonl` + `whitebox-coverage-internalizations.jsonl`（本 Agent 另有产物目录约定的从其约定）
- **优先领域**（route.py 路由不佳时手动指定方向）：B02 自动化测试、B01 测试策略
- **先查自己**：SLOT-1 路由前先按 problem_family 检索自身 internalizations.jsonl，命中直接自用（领域技能融入式 / 专项技能升格式），同类问题不重复问专家
- **铁律**：裁决禁止静默忽略；accepted 必须落实改动并回链 expert_id；不归因不收尾
- **回链落盘判定禁止手写**：必须经门禁机制照抄输出（slot_attribution spec：project / expert_id 入参）（落实质量留软层）。


## 引擎接线（Xj-engine）

本技能为通用公开版，已剥离私有宿主依赖。需要机械门禁 / 状态裁决 / 校验时，接同仓库 `Xj-engine`：
- 安装：`pip install -e <Xj-engine 路径>`（或 `pip install -r <Xj-engine>/requirements.txt`）
- 健康检查：`xj-engine health`
- 按 ET 契约调用：`xj-engine run --payload '<ET Payload>'`，或 `from xj_engine.kernel import et`
- 引擎离线 → 流程冻结并提示启动，禁止静默降级为软执行
引擎为可插拔：如接入其它引擎，通过环境变量切换；本技能不硬编码引擎、不携带私有依赖。
