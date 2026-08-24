> 分片自 01_workflows.md 2026-08-20 拆分，原章节：二、流程说明 / 流程A：新增功能 / 项目开发（原 L257-424）

## 流程A：新增功能 / 项目开发

**步骤1 · 项目经理宣布启动**

**→ 步骤0-B：sv-supervisor 规则强制加载（前置硬性）：**
在进入步骤1之前，PM 必须执行以下加载： 【规范】
1. 创建/读取 `.flow_state.json`（状态文件，位于项目根目录）
   - 不存在 → 创建新文件，status=PENDING，step=STEP-01
   - 存在 → 恢复断点，输出当前状态
2. 读取 sv-supervisor/SKILL.md，加载审批调度规则
3. 读取 chain-execution/SKILL.md §3-5，加载状态机+物理证据+前置门控规则
4. 输出声明：`[sv-supervisor rules loaded]`
5. 输出 `sv_verdict` 当前状态
**缺少以上任意一步 → 禁止进入步骤1** 【规范】

**状态加载判定禁止手写（2026-08-16 裁定，gate-switch 机械门禁）：** 「`.flow_state.json` 已创建/已恢复断点」禁止口头声称，必须扳动 `python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py --spec ~/.agents/skills/gate-switch/specs/flow_state_load.json --set project=<项目根路径>` 照抄结论——判 A（文件存在且 status/step 关键字段非空）才允许进入步骤1；判 B 则 violations 原文即缺项清单，补齐后重新扳动。sv-supervisor 规则读取、`[sv-supervisor rules loaded]` 声明等语义项仍属软层自觉。 【铁律】


明确项目名称与目标，向所有角色发出启动指令。
**→ 前置项目输入校验（硬性）：**
如果用户上传了压缩包或给出了项目路径，PM 必须首先校验项目根目录是否存在 `.prd.md`（需求文档）和 `.ui-proto.json`（UI 原型结构化输入）。两者齐全后，所有角色直接读取这两份输入文件熟悉项目结构；缺失任一文件 → 流程暂停，要求补齐前置输入。 【规范】


**步骤2 · 大产品经理：需求分析**
- **→ 读取项目前置输入：** 先读取 `.prd.md`（全项目概览 + 技术栈 + 需求清单），然后按需读取 `.ui-proto.json` 掌握页面/组件/交互结构
- 调用技能1「需求澄清」：需求模糊时，先把模糊想法变成清晰可执行的问题陈述，消除歧义后再继续
- 调用技能2「需求规格化」：确保PRD包含六要素（目标/命令/项目结构/代码风格/测试策略/验收标准）
- 执行 KANO+ROI 分析，输出优先级（P0/P1/P2/P3）
- 输出《总需求PRD》→ 汇报项目经理


**步骤3 · 项目经理确认PRD**
审核PRD完整性，确认后调用技能3「任务拆解」，将开发任务按S/M/L规模拆分，标注估时与验收标准。


**步骤4 · 细节产品经理：交互设计**
接收PRD → **→ 读取项目前置输入：** 读取 `.prd.md` 了解需求范围，按需读取 `.ui-proto.json` 掌握页面结构与交互流程 → 质疑闭环 → 输出《详细交互设计文档》→ 汇报项目经理。


**步骤5 · 并行：视觉设计 + 测试用例**
- 界面设计师：输出视觉规范（7种组件状态、间距、颜色、切图规范）
- 测试工程师：
  - **→ 先读取 `.prd.md` 与 `.ui-proto.json` 了解项目需求与交互结构**
  - **→ 自主发现并使用 ArchMap 分析结果：** 检查 `<项目路径>/archmap/` 是否存在有效的 `02_架构图.md` 与 `03_数据链路图.md`；存在则直接读取使用，不存在或过期则自行调用 `/archmap <项目路径>` 生成
  - **→ 新增用例必须包含 `source_node` / `source_branch` / `test_methods` 三要素** 【规范】
  - 再按 `execution_mode` 设计测试用例，输出 Schema JSON 到统一用例清单 `execution-list.json`
  - **→ UI 用例单源双路挂载：** UI 用例 steps 统一按通用 case JSON schema 产出（`action` / `element_description` / `input_value` / `expected_value` / `wait_ms`，action 白名单与边界值规则由执行引擎自备）；`element_description` 按 `data-testid > id > name > xpath` 优先级取值（取自 DPM 交互文档第 10 节字段约束表 testid 列）。单源双路执行：执行引擎自备（直跑或编译为 `.spec.ts` 后 `npx playwright test`）；边界值用例按字段约束表自动展开 0/min/max/max+1 四组，缺约束表禁止编造边界 【规范】
- 测试用例中需要标注 `smoke: true` 标签（5-8 个 P0 核心场景），供 Step 9.5 冒烟测试门禁使用
- 项目经理确认 UI 完成 + 用例评审通过后，进入开发阶段

**精准回归准备（在 Step 5 同时完成）：**
- test-case-designer 在用例索引中标注每个用例的覆盖范围（模块/页面/接口）
- **基于 ArchMap `precise_analysis.json`（如存在）标记 `baseline_affected: true` 的用例，用于精准回归**
- 覆盖范围标签供后续 Bug 修复时的「变更范围分析 → 精准回归」使用
- 标签示例：`scope: ["用户模块", "个人资料页", "头像上传API"]`


**步骤6 · 前端工程师：前端开发**
- **→ 读取项目前置输入：** 读取 `.prd.md` 与 `.ui-proto.json`，结合代码上下文定位相关模块
- 调用技能5「上下文加载」：每次开发会话开始时，加载项目规范和相关代码
- 调用技能7「前端UI工程」：实现组件时确保四种状态完整（加载中/错误/空状态/有数据），零控制台错误
- 调用技能4「切片实现」：实现→测试→提交循环，禁止跨多个未验证切片批量开发 【规范】
- 前端自测（主流程/异常/边界/空状态）
- 调用技能9「技术测试驱动」：自测阶段使用红绿重构循环
- 自测通过后执行**导入验证门禁**：调用 `python3 -c "from <新模块> import <新函数>"` 验证所有新文件可正确导入
- 涉及函数重命名 → 先执行**跨文件审计**：`grep -rn <旧名称> src/ app/ tests/ --include="*.py" --include="*.ts" --include="*.js"`，确认全部引用后统一替换
- 自测通过 → 汇报项目经理


**步骤7 · 后端工程师：后端开发**
- **→ 读取项目前置输入：** 读取 `.prd.md` 与 `.ui-proto.json`，结合源码上下文理解接口与数据逻辑
- 调用技能5「上下文加载」：每次开发会话开始时必做
- 调用技能8「接口设计」：先定义接口契约（method/params/错误结构/成功结构），再写实现代码
- 调用技能6「文档溯源」：使用任何第三方库前必须查官方文档，禁止凭记忆调用API 【建议】
- 调用技能4「切片实现」：按接口/模块逐步实现，每片测试通过后提交
- 后端自测（冒烟/异常/并发/文件边界）
- 调用技能9「技术测试驱动」：自测阶段使用红绿重构循环
- 自测通过后执行**导入验证门禁**：验证新文件可被正确导入
- 引入新 Python 库 → 立即更新 `requirements.txt`：`echo "<pkg>==<version>" >> requirements.txt && sort -u -o requirements.txt requirements.txt`
- 修改 config.py 等配置文件 → 同步更新 README.md / config_summary.md 等文档中的对应参数说明
- 涉及函数/API 重命名 → 先执行**跨文件审计**再改名
- 自测通过 → 汇报项目经理


**步骤8 · 代码审查**
开发自测完成后、进入任何正式测试前，必须执行代码审查（质量左移）： 【规范】
- 调用技能11「代码审查」：提测前五维度检查（正确性/可读性/可靠性/可维护性/基础安全）
- **新增 4 项审查（2026-07-11）：**
  - 涉及新文件 → 确认导入验证已执行
  - 涉及重命名 → 确认跨文件审计已完成
  - 涉及新依赖 → 确认 requirements.txt 已同步
  - 涉及配置变更 → 确认文档已同步更新
- 审查不通过 → 打回开发修复，禁止进入冒烟/全量测试 【规范】
- 审查通过 → 进入 PM 自测确认


**步骤9 · 项目经理确认前后端自测通过**
审核自测报告与代码审查结论，确认后进入冒烟测试阶段。


**步骤9.5 · 冒烟测试门禁**
在正式全量链式测试前，执行冒烟测试快速拦截基础问题：

1. test-executor 执行冒烟用例（5-8 个 P0 核心场景）：主流程端到端 / 核心数据展示 / 关键按钮可用 / 登录态
2. 冒烟用例调用 playwright-test skill 执行（`npx playwright test --grep "SMOKE"`），又快又准
3. 冒烟结果分流：
   - **全部通过** → 进入 Step 10 全量测试
   - **有失败** → 直接触发流程B（Bug修复），**不进入全量测试**（节省全量测试成本）
4. 冒烟用例由 test-case-designer 在 Step 5 阶段预先设计（标注 `smoke: true` 标签）

冒烟门禁目的：确保提测质量基线，避免全量测试被低级 Bug 阻断浪费资源。

→ 如冒烟失败触发流程B，同步时保持状态不变，记录步骤说明为"冒烟失败→流程B"

**步骤10 · 测试全自动链式执行（chain-execution）**
PM 触发测试链，自动流转：

```
【PM指令】启动测试全自动链。
链：test-case-designer → test-lead(Q1-Q3 语义审核) + backend/engine(Q4 机械格式，`POST /api/test-gates/case-format`) → test-executor → test-lead(Q5 语义抽审) + backend/engine(Q5-Q6 机械证据链，`POST /api/test-gates/evidence-chain`) → acceptance-manager
```

链式引擎自动依次调度：
1. test-case-designer：需求→测试点→Schema JSON 用例（含变更范围分析→精准回归）
2. test-lead：调用质量门禁 Q1-Q3 语义审核用例 → backend/engine `POST /api/test-gates/case-format` 执行 Q4 机械格式校验；签发由 test-lead 提交、backend/engine `POST /api/test-gates/sign-batch` 分配 global_batch_id 并签发 CROSS_VALIDATION_HASH → 写入 `batch_meta.json`
3. test-executor：按 execution_mode 选择引擎执行全量批次
4. test-lead：调用 Q5 语义抽审 + backend/engine `POST /api/test-gates/evidence-chain` 执行 Q5-Q6 机械证据链校验 → 生成 `test-master-report.json` 与 `defect-auto-grade.json`
5. **POST_GATE_AUDIT**：sv-supervisor 执行后置审计（10%-20%抽样复核 test-lead 语义审核与 backend/engine 机械门禁质量）
- **全部通过** → 直接进入步骤12（部署）
- **有失败** → 自动触发流程B
- POST_GATE_AUDIT 发现 test-lead 或 backend/engine 漏检 → 按质量基线阈值扣分


**步骤11 · Bug修复（流程B）**
全量测试或验收不通过后 → 项目经理确认 → 触发流程B。


**步骤12 · 运维部署**
- 运维部署：本地打包、版本记录 → 汇报项目经理


**步骤13 · 验收经理最终判定**
- 验收经理：基于 `test-master-report.json`、`acceptance_report.json`（如需最终验收）做出通过/不通过判定 → 汇报项目经理
- 不通过 → 返回步骤11 Bug修复
- 通过 → 进入步骤14


**步骤14 · 触发流程C（项目收尾）**


---

