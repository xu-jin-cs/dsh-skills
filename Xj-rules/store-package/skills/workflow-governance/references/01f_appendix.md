> 分片自 01_workflows.md 2026-08-20 拆分，原章节：二、流程说明 / 工程技能调度总表 + 附录A：PM 流程状态输出模板 + 附录B：规则文件索引表（原 L823-896）

## 工程技能调度总表

| 编号 | 技能名称 | 调用阶段 | 谁来用 |
|------|---------|---------|-------|
| 1 | 需求澄清 | 需求模糊时 | 大产品经理启动前 |
| 2 | 需求规格化 | PRD输出时 | 大产品经理执行中 |
| 3 | 任务拆解 | PRD确认后 | 项目经理调用 |
| 4 | 切片实现 | 整个开发阶段 | 前端 + 后端 |
| 5 | 上下文加载 | 每次开发会话开始 | 前端 + 后端 |
| 6 | 文档溯源 | 使用第三方库时 | 后端工程师 |
| 7 | 前端UI工程 | 组件实现时 | 前端工程师 |
| 8 | 接口设计 | 接口定义时 | 后端工程师 |
| 9 | 技术测试驱动 | 自测 + 交叉测试 | 前端 + 后端 + 测试工程师 |
| 10 | 调试排错 | Bug发现时 | 测试工程师 + 对应开发 |
| 11 | 代码审查 | 提测前 | 项目经理调用 |
| 12 | 代码简化 | 重构时（按需）| 对应开发 |
| 14 | 文档与ADR | 重大决策时（按需）| 对应开发 |
| 15 | playwright-test (Playwright UI自动化测试skill) | Step5生成 + 测试阶段 | 测试用例设计Agent |
| 16 | 测试证据链 | 测试执行 + 审计 | 测试执行Agent + 测试监督Agent |
| 17 | 测试执行引擎(test-run) | 执行时 | 测试执行Agent |
| 18 | 测试质量门禁(test-quality-gate) | 审核时 + 审计时 | 测试监督Agent |
| 19 | 测试用例设计 | 测试阶段 | 测试用例设计Agent |
| 20 | 测试调度与语义审核 | 全测试阶段 | test-lead |
| 21 | 代码图谱分析 | 流程D（按需） | 全体角色 |
| 22 | 项目输入规范（.prd.md + .ui-proto.json） | 流程A Step1硬性 + 各Agent启动前 | 全体角色 |
| 23 | Andrej Karpathy Dev Skill | 每次编码修改时强制执行 | 全体开发/测试角色 |
| 24 | UI自动化测试标准化全流程 v2.0 | UI自动化用例设计前硬性 | UI自动化测试工程师 |
| 25 | UI 原型结构化输入规范 | UI自动化用例设计前硬性 | UI自动化测试工程师 |
| 26 | retro-skill-dispatcher Retro技能自动匹配分发 | 流程B Phase 1.5 + 流程C Step 2.5 | 项目经理 |
| 27 | ui-designer UI重构总流程编排 | UI视觉改造任务时 | PM指派 → ui-designer编排 |
| 28 | internal-taste-analyze 内置风格解析 | ui-designer Step 1 | ui-designer子agent调度 |
| 29 | ui-expert-designer UI设计专家 | ui-designer Step 2 | ui-designer子agent调度 |
| 30 | ui-interaction-detail 交互细节落地 | ui-designer Step 3 | ui-designer子agent调度 |
| 31 | ui-frontend-standard 前端工程标准化 | ui-designer Step 4 | ui-designer子agent调度 |
| 32 | ui-visual-acceptance 视觉验收评审 | ui-designer Step 5 | ui-designer子agent调度 |

---

## 附录A：PM 流程状态输出模板（步骤切换强制）

```
━━ 流程状态自检 ━━━━━━━━━━━━━━━━━━━━━━
① 上游交付物: ✅ 齐全（共N个）
② 上游结论: ✅ 通过
③ 阻塞项: ✅ 无未解决阻塞
④ sv-supervisor: ✅ APPROVED / ❌ BLOCKED
⑤ 规则: ✅ sv-supervisor规则已置顶
⑥ 新文件导入验证: ✅ 已执行 / ⬜ 不涉及
⑦ 跨文件重命名审计: ✅ 已执行 / ⬜ 不涉及
⑧ 依赖同步: ✅ requirements.txt已更新 / ⬜ 不涉及
⑨ 配置文档同步: ✅ 已同步 / ⬜ 不涉及
⑩ 测试设计输入资产: ✅ 已由 test-case-designer 生成/读取 / ⬜ 不涉及
⑪ 测试用例三要素齐全: ✅ 已校验 / ⬜ 不涉及
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
缺少自检块不得推进。`sv_verdict` 不为 APPROVED 时自动暂停。

## 附录B：规则文件索引表

| 文件 | 内容 | 加载条件 |
|------|------|---------|
| `rules/00_root_safety.md` | 目录树安全完整禁令 | 全局始终加载 |
| `rules/01_workflows.md` | 强制规则 + 流程分片索引（流程正文 2026-08-20 拆分至 01a/01b/01c/01d/01e/01f 六个分片） | 开发/项目相关文件 |
| `rules/02_roles_responsibility.md` | 全角色职责 + PM 合规门禁 | 角色配置/Skill 文件 |
| `rules/03_engineering_skills.md` | 工程技能规范（正文 12 套，全量 32 套索引见本文件技能调度总表） | 源码文件 |
| `rules/04_dev_standard.md` | 前后端通用开发规范 | 工程配置文件 |
| `rules/05_test_quality_system.md` | 测试体系 + sv-supervisor 审计 | 测试相关文件 |
| `rules/07_ui_skill_rules.md` | Taste/UI UX Pro Max 等 UI 技能规则 | UI 设计文件 |
| `rules/08_governance_rules.md` | 全局治理规则 G29-G32（G33 三问评估已废止，见 `09_governance_archive.md` 第十节第 6 条） | 全局始终加载 |
| `rules/09_governance_archive.md` | 历史事故/钩子约束/已删规则归档（非阻断，不参与生成约束） | 不按需加载（归档参考） |
| `rules/10_performance_optimization.md` | 全局性能优化编码规范（单行优先/IO单次/懒加载/无阻塞） | 源码文件 / 工程配置文件 |
| `rules/11_gate_framework.md` | 强制填充门元方法族（L1/L2/L3 选档 + REFORM-GATE + GENERALIZE-GATE + 模式库） | 全局始终加载 |
| `rules/12_parasite_nest.md` | 寄生附属执行模式（寄生巢：宿主闸内置任务容器，落巢休眠、闸出口唤醒并行执行、永久驻留） | 寄生附属执行模式规则 |
| `rules/13_workflow_router.md` | 专用工作流路由强管控（注册触发词精确匹配唯一准入，禁隐式触发，唯一权威注册表 workflow-registry.json） | 工作流路由强管控规则 |

（注：06 号位已删除，见 `09_governance_archive.md` 第八节。）
