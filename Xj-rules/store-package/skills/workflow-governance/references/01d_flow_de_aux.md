> 分片自 01_workflows.md 2026-08-20 拆分，原章节：二、流程说明 / 流程D：代码图谱分析 + 按需调用 + 流程E：测试模式（原 L610-683）

## 流程D：代码图谱分析（按需调用）

**触发词：** `分析` `生成` `使用`

用户说出以下触发词时，执行对应 code-graph 操作（不切换角色，直接在当前上下文执行）：

| 触发词 | code-graph 命令 | 用途 |
|--------|----------------|------|
| 上传文件夹 / 新项目 | `code-graph-mcp incremental-index` | 首次建立代码索引 |
| `分析` | `code-graph-mcp impact <目标>` + `callgraph <目标>` | 分析影响范围、调用链 |
| `生成` | `code-graph-mcp map --compact` + `search <概念>` | 了解架构和上下文后再生成代码 |
| `使用` | `code-graph-mcp refs <符号>` + `deps <文件>` | 查看符号引用、文件依赖 |

**触发词不带目标参数时**，先向用户确认要分析/生成/使用的具体功能名或文件名，再执行对应命令。

---

## 按需调用（任意阶段）

- **技能12 代码简化**：需要重构时触发，使用扩展-收缩安全迁移模式，禁止一次性大范围重构。 【建议】
- **技能14 文档与ADR**：发生重大技术决策时触发，记录「为什么」而非「是什么」。

---

## 流程E：测试模式（纯测试执行模式）

**触发词：** `测试` `执行测试` `跑测试` `测试一下` `做测试` `走测试` `进行测试` `开始测试` `跑用例` `执行用例` `回归测试` `冒烟测试`

用户说出以上触发词时，PM进入**测试模式**，不启动完整开发流程，只调用测试团队执行测试任务直至产出报告。

### 五种执行模式（PM 根据用户指令判断）

PM 进入测试模式后，首先解析用户输入中的 mode token 与可选项目路径：

- 第二 whitespace token 为 `{func-only, api-only, tdd-only, api-tdd, all-full}` 之一 → 记为 `execution_mode`
- 第三 whitespace token 为合法路径 → 记为 `project_path`，覆盖或补充 Step 0-C 的扫描结果
- 解析失败 → 回退到关键字匹配（兼容旧说法）

| 用户指令 | 解析模式 | 输入文件 | 执行链 |
|:---------|:---------|:---------|:-------|
| `测试` / `执行测试` / `跑测试`（无 mode） | `api-tdd`（默认） | `.prd.md + .api-schema.json + 源码/接口契约` | test-case-designer(api) + test-driven-development → test-lead(Q1-Q3语义审核) + backend/engine(Q4机械格式) → test-executor(api+tdd并行) → test-lead(Q5语义抽审) + backend/engine(Q5-Q6机械证据链) |
| `执行测试 func-only [path]` | `func-only` | `.prd.md + .ui-proto.json` | test-case-designer → test-lead(Q1-Q3语义审核) + backend/engine(Q4机械格式) → test-executor → test-lead(Q5语义抽审) + backend/engine(Q5-Q6机械证据链) |
| `执行测试 api-only [path]` | `api-only` | `.prd.md + .api-schema.json` | test-case-designer(api) → test-lead(Q1-Q3语义审核) + backend/engine(Q4机械格式) → test-executor(api) → test-lead(Q5语义抽审) + backend/engine(Q5-Q6机械证据链) |
| `执行测试 tdd-only [path]` | `tdd-only` | `.prd.md + 源码/接口契约` | test-driven-development → test-lead(Q1-Q3语义审核) + backend/engine(Q4机械格式) → test-executor(tdd) → test-lead(Q5语义抽审) + backend/engine(Q5-Q6机械证据链) |
| `执行测试 api-tdd [path]` | `api-tdd` | `.prd.md + .api-schema.json + 源码/接口契约` | test-case-designer(api) + test-driven-development → test-lead(Q1-Q3语义审核) + backend/engine(Q4机械格式) → test-executor(api+tdd并行) → test-lead(Q5语义抽审) + backend/engine(Q5-Q6机械证据链) |
| `执行测试 all-full [path]` | `all-full` | 全部输入 | 并行三条子链（func / api / tdd）→ 汇总缺陷 → 统一回归 → test-lead 语义收口 + backend/engine 机械证据链审计 → acceptance-manager 验收 |

**判断规则：**
1. 用户未明确指定测试类型或 mode token 不合法 → 默认 `api-tdd`。
2. 用户明确指定 mode → 严格按该 mode 执行，不得自动扩展为 `all-full`。
3. `[path]` 可选；缺省时使用 PM Step 0-C 已扫描的 `project_path`。
4. `execution_mode` 必须写入 `.flow_state.json` 的 `test_execution_mode` 字段，供后续角色与 sv-supervisor 读取。 【规范】

**模式切换：** 已进入某 mode 后如需切换，必须更新 `.flow_state.json` 并经 sv-supervisor 审批，禁止中途静默切换。 【规范】

### 五种模式统一结果分流

- **全部 PASS** → 输出《测试报告》摘要 + `acceptance_report.json`，汇报用户。
- **有 FAILED** → 输出《测试报告》→ **自动触发流程B（Bug 修复）**，测试报告作为 Bug 诊断材料提交开发。
- **`all-full` 子链部分失败** → 汇总失败用例，按模块范围触发精准回归，不重复执行已通过子链。

### 统一交付物（五种模式一致）

| 交付物 | 产生者 | 说明 |
|--------|--------|------|
| `execution-list.json` | test-case-designer / test-driven-development | 用例清单，含 `execution_mode`、`global_batch_id`、需求/接口/UI 绑定字段 |
| `batch_meta.json` | test-lead / backend/engine | 全局批次元数据，含 `cross_validation_hash`、`baseline_diff_hash`、`env_label` |
| `test-baseline-diff.json` | test-case-designer / PM | 基线变更范围，用于精准回归 |
| `test-master-report.json` | test-executor / test-lead / backend/engine | 统一顶层测试总报告，合并原 `report.json` + `evidence-index.json`，mode 字段标识来源 |
| `evidence/` 目录 | test-executor | UI=截图+前后快照；API=请求/响应日志；TDD=覆盖率/stdout |
| `defect-auto-grade.json` | test-lead | 自动缺陷分级，驱动流程 B |
| `bug-fix-record.md` | PM + test-lead | 缺陷记录与回归闭环（有缺陷时） |
| `acceptance_report.json` | acceptance-manager | 最终验收结论，含 `execution_mode` 与 `global_batch_id` / `meta_batch_id` |

