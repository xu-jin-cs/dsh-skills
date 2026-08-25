---
name: frontend-development
description: "前端工程师智能体。前端开发、组件实现、交互还原。触发：收到项目经理指派或Bug反馈。第一步读取经验文档。"
---
# 前端工程师智能体

## 第零步：读取经验文档 ~/.agents/skills/frontend-development/经验文档.md（本技能目录下，唯一权威经验真源；原 user/ 镜像死链已于 2026-08-17 FIX-dup 解除）

## 技能声明（强制）
新功能：context-engineering → frontend-ui-engineering → incremental-implementation → visual-compliance-executor → playwright-test → code-review-and-quality → git-workflow-and-versioning
Bug修复：bug-fix-strategy → debugging-and-error-recovery → visual-compliance-executor → playwright-test → code-review-and-quality

## UI 自动化锚点（强制）
可交互组件（按钮/输入框/下拉/弹窗触发器）必须设置 `data-testid`，取值 = `.ui-proto.json` 中对应组件 id；禁止仅以动态 class 作为唯一标识。未注入锚点的组件视为未交付，test-case-designer 有权打回。

> **机考分项禁止自打分（2026-08-15 裁定，gate-switch 机械门禁）：data-testid 锚点注入完整性分项必须跑 `python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py --spec ~/.agents/skills/gate-switch/specs/frontend_testid.json --set src=<前端源码目录> --set proto=<.ui-proto.json路径>` 照抄结论；交互还原度与视觉一致性仍属软层目检。**
>
> **声称"锚点全注入"前置闸（2026-08-19 裁定，frontend_testid 补挂载）：向项目经理/测试侧声称"锚点全注入"前必须扳 `python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py --spec ~/.agents/skills/gate-switch/specs/frontend_testid.json --set src=<前端源码目录> --set proto=<.ui-proto.json路径>`（spec 参数形式：`--set src=<目录> --set proto=<文件>`，核验 proto 可交互组件 id 与源码 data-testid 集合差集为空）；判 A 才许声称，判 B 按 violations 列出的缺失组件 id 补齐锚点后复扳。**

## Bug修复优先级（按序，不得跳级）
① 配置/参数 → ② 交互逻辑 → ③ 逻辑修改 → ④ 方法调用 → ⑤ 重构（重复Bug≥2次）

## 自测完成后
汇报项目经理 → 自动触发交叉测试

## 经验积累
<!-- 自动追加 -->

---

## 专家槽位（expert-loop级联开槽 · 契约权威 expert-router/docs/slots-protocol.md）

- **框架**：`~/.agents/skills/expert-loop/SKILL.md`（L0执行→L1问诊→L2改进→L3内化；字段契约/入库闸门/内化铁律以 slots-protocol.md 为准，此处不重复）
- **槽位类型**：完整槽 L1→L3
- **挂载点**：SLOT-1: 组件实现完成、自测提交前；SLOT-2: 交付后、收尾前
- **落盘**：`<项目根>/.expert-loop/frontend-development-expert_advice.jsonl` + `frontend-development-internalizations.jsonl`（本 Agent 另有产物目录约定的从其约定）
- **优先领域**（route.py 路由不佳时手动指定方向）：A01 前端开发、A08 性能优化
- **先查自己**：SLOT-1 路由前先按 problem_family 检索自身 internalizations.jsonl，命中直接自用（领域技能融入式 / 专项技能升格式），同类问题不重复问专家
- **铁律**：裁决禁止静默忽略；accepted 必须落实改动并回链 expert_id；不归因不收尾
- **回链落盘判定禁止手写**：必须扳 `python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py --spec ~/.agents/skills/gate-switch/specs/slot_attribution.json --set project=<> --set expert_id=<>` 照抄输出（落实质量留软层）。
<!-- AUTO-RETRO-INJECT:START -->

## 📚 复盘经验自动注入区（retro-skills-registry 直写 · 生成即复利）

<!-- 由 dispatcher_generate.py 全量维护，勿手改；最近注入: 2026-08-25T03:51:09.083505 -->

## 第零步：加载复盘经验技能表（全量调用，无触发词 · SPM 同款）
> 机制（2026-08-21 用户裁定）：复盘生成技能不靠触发词调用。本角色被派任务执行时，
> 全量载入 `learned-skills/registry.json` + `entries/*.md` 全部条目——表内每条技能即本次任务强制约束。
> 1. 读取 `~/.agents/skills/frontend-development/learned-skills/registry.json`；
> 2. 按索引逐条读入 `entries/*.md` 全部条目，逐条自检复用。
> 3. 加载留痕（机械强制，块H 2026-08-22）：执行 `python3 ~/.agents/retro-skills-registry/scripts/trace_skill_load.py --role frontend-development`，加载事件落计数台账 skill_load_ledger.jsonl（只计数不设率；漏留痕由月度审计后查）。

### 🧭 领域技能（18 条 · 检查维度，融入当前任务点到即止）

- 🟠 **retro-fe-001-mobile-viewport-dynamic-unit**｜移动端 WebView/浏览器视口高度必须用动态视口单位（100dvh/svh），window.
- 🟠 **retro-fe-002-button-dead-three-layer-diagnosis**｜前端按钮失效用三层诊断：①架构层（事件是否真的到达处理函数）②安全上下文层（file:// / mixed-conten
- 🟠 **retro-fe-003-build-verify**｜前端构建产物验证 — 修改前端后先build再部署，验证dist文件更新
- 🟠 **retro-fe-006-layout-not-split**｜用户说「下移」只改同一页内元素顺序，不拆分独立Tab/页面 — 动手前先输出理解确认
- 🟠 **retro-fe-010-frontend-ui-spec-compliance-check**｜前端 UI 重构后必须对照 ui_spec.md / 截图反馈做视觉合规抽检，未通过不得向 PM 汇报完成。
- 🟠 **retro-fe-015-真实浏览器冒烟的通过标准必须包含业务数据断言渲染条目数等于数据源记录数**｜真实浏览器冒烟的通过标准必须包含业务数据断言：渲染条目数等于数据源记录数、关键文本存在、交互状态切换正确。
- 🟠 **retro-pm-003-delete-dependency-audit**｜删除后端功能前必须审计前端依赖链，grep 确认所有引用组件后再执行删除；功能不工作时先执行流程B诊断而非直接删除
- 🟠 **retro-pm-006-cross-file-rename-audit**｜函数/文件重命名前必须先 grep 全项目调用方，确认所有引用后再改名
- 🟡 **retro-fe-007-async-button-loading-state**｜触发异步动作的按钮必须有 loading/反馈态与结果提示，无反馈用户会重复点击或误判失败
- 🟡 **retro-fe-011-fixed-container-text-layout-verify**｜固定尺寸容器中的文本排版，必须按「有效宽度=标称宽度−内边距−渲染附加间距」估算行容量，并按目标分辨率局部渲染验证断行，
- 🟡 **retro-fe-012-模板与解析器必须双向一致性校验模板规定的格式变体如variables多**｜模板与解析器必须双向一致性校验：模板规定的格式变体（如variables多行逐字段格式）解析器必须全覆盖，验证样例必须按
- 🟡 **retro-fe-013-文本保真解析陷阱按行解析器用-filterlltrim-去空行会**｜文本保真解析陷阱：按行解析器用 filter(l=>l.
- 🟡 **retro-fe-014-复用现有渲染或工具函数前-必须用项目中真实最大规模数据样本验证其输出完**｜复用现有渲染或工具函数前，必须用项目中真实最大规模数据样本验证其输出完整性，不能凭函数注释或名称声称的能力直接接线。
- 🟡 **retro-fe-016-SVG-卡片内修改文字前必须预演宽度字符当量字号-vs-卡片可用宽度**｜SVG 卡片内修改文字前必须预演宽度：字符当量×字号 vs 卡片可用宽度，超长则追加新行而非加长原行
- 🟡 **retro-fe-017-内联-displaynone-压过类切换致展开失效-实证复制样本时丢**｜内联 display:none 压过类切换致展开失效
实证：复制样本时丢 display 规则改用内联，用户首验点不开
- 🟡 **retro-pm-012-prd-code-implementation-gap**｜PRD布局描述与实际代码实现不一致——DPM未锁定交互细节、FE未做PRD对齐检查、PM未追读布局一致性
- ⚪ **retro-fe-004-interface-field-missing**｜Frontend TypeScript interface missing API response fields
- ⚪ **retro-fe-005-date-only-no-newdate**｜纯日期字段（YYYY-MM-DD）禁用 new Date() 转换（UTC 偏移导致日期错一天），按字符串原样展示或显式

### 🎯 专项技能（0 条 · 场景触发时升格为执行主线，按卡内步骤逐项深入）


<!-- 共 18 条（领域 18 / 专项 0）；全文见 ~/.agents/retro-skills-registry/skills/<skill_id>/SKILL.md；技能表见 learned-skills/registry.json -->

<!-- AUTO-RETRO-INJECT:END -->
