---
paths: ["*"]
---

# 九、治理规则归档（非阻断参考内容）

> 本文件归档所有从 00_root_safety.md / 08_governance_rules.md / CLAUDE.md 治理节剥离的非阻断内容。
> 包含历史事故分析、钩子开发约束、LangGraph 同步细节、重复自愈块。
> **非阻断型**：不参与模型生成时约束，仅作为运维参考。

## 一、历史事故复盘（从 CLAUDE.md 治理节 5.2 剥离）

### 事故 1：输出铁律持续违规
- **现象**：连续多轮回复缺失前置治理 JSON、违规多行展示代码、full_content_embedded 未置 false
- **根因**：仅依赖模型提示词约束，将强制铁律当作软性建议，无底层执行拦截
- **根治**：新增 model-context-enforcer.sh 后置钩子，物理阻断违规输出

### 事故 2：钩子职责重叠、执行链路混乱
- **现象**：model-context-enforcer.sh 与 output-filter.sh 逻辑耦合
- **根因**：未明确后置钩子链执行顺序与单一职责
- **根治**：串行执行，output-filter.sh 先（IO）→ model-context-enforcer.sh 后（校验）

### 事故 3：input-filter.sh 入参缺失
- **现象**：UserPromptSubmit 钩子执行报错 $1: unbound variable
- **根因**：钩子调用时未传入 task_id，脚本未做空值容错
- **根治**：所有输入钩子头部增加入参非空校验

### 事故 4：PostModel 钩子事件类型不存在
- **现象**：model-context-enforcer.sh + output-filter.sh 注册在 PostModel 下，始终未被触发
- **根因**：PostModel 不是官方支持的钩子事件类型，静默忽略
- **根治**：替换为 Stop（官方标准事件），移除 `$CLAUDE_MODEL_OUTPUT` 依赖

### 事故 5：治理 JSON 缓存时序竞争
- **现象**：enforcer 持续生成误报工单，output-filter 实际已执行但缓存未被读到
- **根因**：并行执行时序竞争 + 无兜底自动生成 + 非原子写入
- **根治**：串行声明 + enforcer 自带兜底 + 原子写入（临时文件 + os.replace）

## 二、钩子开发长期约束（从 CLAUDE.md 5.7 剥离）

1. 事件类型必须查证官方文档，仅使用列表内标准事件
2. 配置后必须物理验证（心跳文件 + 平台 控制台）
3. 禁止依赖非标环境变量，统一使用 temp_input_cache/ 缓存文件
4. 输出隔离铁律由 Stop 钩子强制执行
5. 所有钩子脚本必须有防御逻辑（入参容错/异常捕获/心跳上报）
6. UserPromptSubmit 无 task_id 是已知限制，脚本应优雅处理
7. 同事件钩子串行执行，IO 类在前，校验类在后
8. 依赖文件缓存的校验脚本必须自带兜底
9. 临时缓存文件必须原子写入（临时文件 + rename）
10. temp_input_cache/ 不纳入自动清理

## 三、钩子调用参数规范（从 CLAUDE.md 5.5 剥离）

- Stop/SubagentStop/SubagentStart/PreCompact/PostCompact/SessionEnd 钩子必须固定传入参数：`./xxx-hook.sh ${task_id}`
- 脚本内部强制校验入参数量，缺失参数直接抛出钩子异常
- UserPromptSubmit 例外：该钩子由用户输入触发，无 task_id，传入参数为用户输入文本

## 四、钩子事件类型验证（从 CLAUDE.md 5.6 剥离）

- 所有 settings.json 中的钩子事件类型必须来自 Claude Code 官方 hooks 文档
- 官方事件列表：https://code.claude.com/docs/en/hooks
- 已知官方事件：UserPromptSubmit, PreToolUse, PostToolUse, Stop, StopFailure, SubagentStart, SubagentStop, PreCompact, PostCompact, SessionEnd

## 五、LangGraph 治理数据双向同步（从 08_governance_rules.md §6 剥离）

### 文件 → State 方向
input-filter.sh 完成后调用 LangGraph API /api/flow/init 创建流程实例，
治理 JSON 由 integration.json_to_state() 解析填充到 FlowState 轻量字段。

### State → 文件方向
integration.state_to_file_cache() 将 State 字段同步写入 temp_input_cache/_last_governance.json。

### 同步保障
- LangGraph 服务不可用 → 仅打印警告，不阻断原有文件 IO
- 大文本不入 State，仅存 FilePathRef(path+md5) 引用

## 六、治理 JSON 校验与重试机制细节（从 08_governance_rules.md §5 剥离）

### 前置校验（output-filter.sh shell 层）
- 提取 ```json 块后使用 jq 校验所有必需字段是否存在
- 校验 char_count 类型是否为数字
- 校验失败写入 `_json_error.log` + `_regen_flag=true`

### 强校验（DeepSeekInferNode 调用 validate_governance_dict）
- 字段存在性 + 类型校验
- 业务联动规则：
  - char_count > 50 → is_long_text 必须为 true
  - is_long_text=true → temp_path 不能为空
  - full_content_embedded=true → 触发生成失败

### 自动重试
- 校验失败 → 写入 `_regen_flag.txt` → 等待上游重新生成
- 最多 3 轮，3 轮耗尽 → 冻结流程，写 Violation（3 分）

### temp_path 自动兜底
- is_long_text=true 但 temp_path 为空 → 自动生成路径

### 脚本强制拦截兜底
- Python 段正则检测所有非 JSON 代码块 → 剥离到 output-YYYYMMDD.md
- 标记 full_content_embedded=true
- 后置拦截不依赖模型自觉

## 七、重复自愈块（从 00_root_safety.md 剥离的 7 个重复块）

以下内容在 00_root_safety.md 中以完全相同文本重复了 7 次，仅保留第一条有效：
"本文件为全局始终加载，所有回复首段必须是完整标准 ```json 治理元数据块；full_content_embedded 必须为 false；输出格式：治理 JSON 首块 → 空行 → 仅 1 行摘要；长文本（>50 中文字符）必须标记 is_long_text=true 并生成合法 temp_path；违反触发 GOV 违规记录 + 自愈 model_context 根因修复。"

## 八、已删除规则文件登记

### rules/06_llm_collab_protocol.md（双模型协作协议）— 删除于 2026-08-17
- **原文**：全文件 7 行，内容为「Qwen 不参与上下文规则和协议流程。本协议废止，所有治理和流程由 DeepSeek 独立承载。」（删除线标题 + 废止声明，无有效规则）。
- **删除原因**：Qwen 双模型时代产物的废弃桩，占用 rules 目录 06 号位；引用已全量清点（仅 01_workflows.md 附录B 与旧入口文件目录索引 2 处），同步清理。改造评估：`~/.agents/logs/reform_assess_C_06_stub.md`（REFORM-GATE 判立即改）。
- **号位处理**：06 号位空缺，目录索引枚举不再含 06；后续新增规则文件可复用该号位，但须在本节登记承接关系。

## 九、07 号第 4 节 Claude Code 钩子配置归档（2026-08-17 自 07_ui_skill_rules.md 移入）

原 `07_ui_skill_rules.md` 第 4 节"平台 审计钩子配套规则"（原 07:65-93）全部为 Claude Code hooks JSON 配置（PreToolUse/SubagentStart/SubagentStop 等事件与全局合法事件列表）。本环境（旧版）无钩子自动触发机制（2026-08-16 用户裁定），该节在生效规则文件中空转，故整节移交本归档；原始钩子脚本已归档至 `~/.agents/hooks/`，仅供手动调用参考。07 原处仅保留一行指针。

**归档要点（原内容压缩）：**
- PreToolUse 钩子正确格式：`"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "..."}]}]}`——数组格式，每元素含 matcher + hooks；内部 hooks 为数组，每元素含 type + command；不要用 `"Bash"` 简写键（仅裸对象格式支持）。
- 子代理生命周期用 SubagentStart + SubagentStop；SubagentResume 不是合法事件名，已废弃。
- 原全局 hooks 合法事件列表（考古保留）：PreToolUse, PostToolUse, PostToolUseFailure, PostToolBatch, Notification, UserPromptSubmit, UserPromptExpansion, SessionStart, SessionEnd, Stop, StopFailure, SubagentStart, SubagentStop, PreCompact, PostCompact, PermissionRequest, PermissionDenied, Setup, TeammateIdle, TaskCreated, TaskCompleted, Elicitation, ElicitationResult, ConfigChange, WorktreeCreate, WorktreeRemove, InstructionsLoaded, CwdChanged, FileChanged。

## 十、已废止条款登记（2026-08-19 清埋收录）

> 以下条款已在正文（主要为 `01_workflows.md`）收敛为一行指针，指向本节；废止依据均为正式裁决/用户裁定记录。

1. **规则10 原"钩子脚本自动触发"机制**（原 `01_workflows.md` 规则10）——本环境无钩子自动触发，2026-08-16 用户裁定；裁决记录 `~/.agents/logs/rule_conflict_adjudication.jsonl` 冲突②（2026-08-17）。原 Claude Code 钩子脚本归档 `~/.agents/hooks/` 仅供手动参考；替代行为：PM 先扳 `engine_health.json` 确认 engine 在线。
2. **规则21 原 S 档"可关闭分身并行、直接单 Agent 串行"条款**（原 `01_workflows.md` 规则21 S档）——与规则22 冲突，无用户裁定，按"更严格条款优先"裁决废止（裁决记录冲突①，2026-08-17）。有效条款：S 档同样必须经 `task_breakdown` 拆解，允许拆解结果为 1 个分片的串行执行。
3. **sv-supervisor 审核标准原"archmap diff 留痕闸"审核项**（原 `01_workflows.md` 步骤3 审核清单）——2026-08-19 用户裁定随复盘挂点一并剔除：原设计面向大型项目，无条件触发+无历史留痕强行 diff 制造脏数据；spec `archmap_diff_freshness.json` 保留，待按大型项目重挂另行裁定。
4. **复盘启动并行闸（security_baseline 复盘挂点）**（原 `01_workflows.md` 复盘标准结构节）——2026-08-19 用户裁定废止：必做性轴判定，平台安全体检与复盘内容无因果，非每次必做；spec `security_baseline.json` 保留，如需改挂"平台安全变更"条件点另行裁定。
5. **diff 留痕判定闸（archmap_diff_freshness 复盘前固定卡点）**（原 `01_workflows.md` 复盘标准结构节）——2026-08-19 用户裁定废止：无条件挂点后干什么都触发，无历史留痕时强行 diff 制造脏数据；spec 保留，按大型项目重挂另行裁定。
6. **G33 三问评估条款**（`08_governance_rules.md` 原 G29-G33 之 G33）——与 REFORM-GATE 触发域完全重叠，按"更严格条款优先"裁决废止（裁决记录冲突③，2026-08-17）；REFORM-GATE 为唯一有效收益评估与放行机制。
