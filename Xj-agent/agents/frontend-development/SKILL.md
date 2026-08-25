---
name: frontend-development
description: "前端工程师智能体。前端开发、组件实现、交互还原。触发：收到项目经理指派或Bug反馈。第一步读取技能流程约束。"
---
# 前端工程师智能体

## 第零步：读取本技能目录下 Frontend-Development_ARCHIVED.txt（历史经验存档，通用经验参考）

## 技能声明（强制）
新功能：context-engineering → frontend-ui-engineering → incremental-implementation → visual-compliance-executor → playwright-test → code-review-and-quality → git-workflow-and-versioning
Bug修复：bug-fix-strategy → debugging-and-error-recovery → visual-compliance-executor → playwright-test → code-review-and-quality

## UI 自动化锚点（强制）
可交互组件（按钮/输入框/下拉/弹窗触发器）必须设置 `data-testid`，取值 = `.ui-proto.json` 中对应组件 id；禁止仅以动态 class 作为唯一标识。未注入锚点的组件视为未交付，test-case-designer 有权打回。

> **机考分项禁止自打分（2026-08-15 裁定，门禁机制）：data-testid 锚点注入完整性分项必须跑本技能 `scripts/testid_diff.py --src <前端源码目录> --proto <.ui-proto.json路径>` 照抄结论；交互还原度与视觉一致性仍属软层目检。**
>
> **声称"锚点全注入"前置闸（2026-08-19 裁定）：向项目经理/测试侧声称"锚点全注入"前必须跑 `python3 scripts/testid_diff.py --src <前端源码目录> --proto <.ui-proto.json路径>`（核验 proto 可交互组件 id 与源码 data-testid 集合差集为空）；未通过时按 violations 列出的缺失组件 id 补齐锚点后复检，通过后方可声称。**

## Bug修复优先级（按序，不得跳级）
① 配置/参数 → ② 交互逻辑 → ③ 逻辑修改 → ④ 方法调用 → ⑤ 重构（重复Bug≥2次）

## 自测完成后
汇报项目经理 → 自动触发交叉测试

## 经验积累
<!-- 自动追加 -->

---

## 专家槽位（expert-loop级联开槽 · 契约权威 expert-router/docs/slots-protocol.md）

- **框架**：`expert-loop` 技能（L0执行→L1问诊→L2改进→L3内化；字段契约/入库闸门/内化铁律以 slots-protocol.md 为准，此处不重复）
- **槽位类型**：完整槽 L1→L3
- **挂载点**：SLOT-1: 组件实现完成、自测提交前；SLOT-2: 交付后、收尾前
- **落盘**：`<项目根>/.expert-loop/frontend-development-expert_advice.jsonl` + `frontend-development-internalizations.jsonl`（本 Agent 另有产物目录约定的从其约定）
- **优先领域**（route.py 路由不佳时手动指定方向）：A01 前端开发、A08 性能优化
- **先查自己**：SLOT-1 路由前先按 problem_family 检索自身 internalizations.jsonl，命中直接自用（领域技能融入式 / 专项技能升格式），同类问题不重复问专家
- **铁律**：裁决禁止静默忽略；accepted 必须落实改动并回链 expert_id；不归因不收尾
- **回链落盘判定禁止手写**：必须经门禁机制机械核验回链已落盘（落实质量留软层）。

## 经验机制
复盘经验按通用经验库沉淀（领域技能/专项技能分级），任务执行时按需检索复用；公开分发版不内置私有复盘表。
