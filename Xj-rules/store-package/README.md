# Kimi Code 多智能体工作流体系 · 商店版（57 个独立技能）

每个文件夹是一个符合 agentskills.io 规范的独立技能（YAML frontmatter + 触发条件 + 用法），可单独安装、单独出售。

## 上传必看：Git 发布前兼容性检查

> 以后任何项目上传到 Git 前，必须先按此清单检查；不通过禁止上传。

### 1. 路径必须可移植

- [ ] 禁止出现本机绝对路径：`/Users/<用户名>`、`C:\Users\...`、`/home/...`
- [ ] 路径统一使用相对路径 `./data/...`、`$HOME`、`Path.home()` 或环境变量
- [ ] 代码、文档、配置中不得出现私人目录名

### 2. 凭据必须清零

- [ ] 不得出现真实 `password` / `secret` / `token` / `api_key` / 私钥
- [ ] 已泄露的账号密码必须删除
- [ ] 新增 `.env.example`，真实配置通过环境变量注入

### 3. 私有依赖必须剥离

- [ ] 不得 import 外部私有项目模块，例如 `backend.*`、`etl.common.*`
- [ ] 不得出现内部私有项目名：`agent-harness`、`retro-skills-registry`、`Xj-rules`、个人名等
- [ ] 仓库必须能独立 `clone` 后按 README 安装并运行

### 4. 无关文件必须忽略

- [ ] `data/`、`__pycache__/`、`*.pyc`、`.DS_Store`、`node_modules/`、`*.tgz`、`*.zip` 不入库
- [ ] 数据库文件、模型权重、大体积临时文件不入库

### 5. 上传前必须执行校验

```bash
# 绝对路径扫描：应无命中
grep -RIn --exclude-dir=.git --exclude-dir=data -E '/Users/|C:\\Users|/home/' .

# 凭据扫描：不应出现真实密码/密钥
grep -RIn --exclude-dir=.git -iE 'password|secret|token|api[_-]?key' .

# 语法/配置校验
python3 -m py_compile $(find . -name '*.py' -not -path './.git/*')
```

- [ ] Python 语法检查通过
- [ ] YAML / JSON 解析通过
- [ ] 在全新目录 `git clone` 后，按 README 跑通最小示例

## 安装

```bash
# 单个技能：把整个文件夹拷入 Kimi Code 技能目录
cp -R skills/<技能名> ~/.agents/skills/

# 全套：
cp -R skills/* ~/.agents/skills/
```

B 类闸技能自带 `gate_switch.py` 引擎拷贝，单买即可运行；少数闸在 SKILL.md「依赖」节标注了需同装的姊妹技能。C 类为纯规则文档包，挂载方式见各自 SKILL.md。

## 建议定价分组

- **入门免费/引流**：`gate-switch`（引擎本体）——另有 MIT-0 免费版可单独投放。
- **单品区（$2~5/个）**：46 个 B 类闸技能，按需求单买。
- **合集区（$9~19）**：A 类 7 个框架技能 + C 类 4 个规则文档包。
- **全家桶（$29~49）**：全部 57 个。

## 总目录（57）

### A. 框架技能（7）

| `bug-fix-strategy` | Bug最短路径修复策略。所有Bug修复必须先走本策略，按优先级依次尝试，禁止跳级。同一Bug重复≥2次才进入重构评估。 |
| `dual-gates` | 声明闸+查询闸 双闸落地（正式定稿版）。前置意图定性路由：通道①意图硬路由（信号真源 trigger_signals.json：安全S-DANGER-CMD/问题S-PROBL… |
| `gate-switch` | 通用概率执行门禁骨架（实证族 L2 引擎）。任何"声称 X 已满足/已写入/已生成/已同步/已验收"的场景，把 X 写成检查项 spec JSON，引擎逐项机械核验：全过→掷点… |
| `idea-forge` | 设想锻造炉。用户提出粗糙设想/构想/机制想法时，按 11 维补齐清单自动补全设计（定位边界/维度/颗粒度/触发/执行/写法/门禁/强制与选择性/留痕/演化路径/体系挂载），输出… |
| `parallel-dispatch` | 并行调度与子分身机制总规则（2026-08-14 用户裁定正式版；2026-08-16 增补 PARALLEL-GATE 门禁与文件数量纲）。只要出现多任务（≥2 个子任务/诉… |
| `plan-select` | 扳手框架｜方案择优引擎 v2（三维度槽位原型池，2026-08-18 用户两次裁定定稿，REFORM-GATE 判A，替代 PLAN-FIRST-GATE 用户审核环节）。候选… |
| `scope-boundary-gate` | 范围边界门禁。编码阶段执行，拦截超范围开发，保障需求聚焦。 |

### B. gate-switch 实证闸（46）

| `anchor_registry_audit` | 锚点登记审计闸（2026-08-18 用户裁定采纳锚点注册表补位后落地，REFORM-GATE 判A；first_push_audit 同族'产物在/锚点缺'不对称检测）。 |
| `archmap_diff_freshness` | archmap 复盘前 diff 留痕固定卡点（REFORM-GATE 激活战役 item1，2026-08-15 裁定）：校验 {project}/archmap/diff_… |
| `archmap_sync_freshness` | archmap ETL 配置契约报告新鲜度机械闸（2026-08-16 D 域批量开关化，archmap/SKILL.md 模式 D L195 回填约定）：修改 ETL 配置后… |
| `be_api_schema` | backend-engineer 交付物 .api-schema.json 机械自检（REFORM-GATE 改造 P5a）：契约权威=消费方 api-test-enginee… |
| `bug_fix_gate` | bug-fix-strategy 修复级别机械门禁（2026-08-15 裁定）：script_exit 包装 bug_fix_switch.py，机械核验禁止跳级/重构重复次… |
| `clarify_gate` | CLARIFY-GATE 需求五要素齐备性声明填充完整性机械校验：ui-designer Phase 0 判闸。 |
| `danger_cmd_gate` | 危险命令事前闸（铁律7，2026-08-17 存量清算落地）：bash 执行涉 rm/cp递归/find -delete/mv 等命令前，把待执行命令原文落盘为文本文件，扳本闸… |
| `deploy_admission` | 部署启动准入（DEPLOY-001 重生版：交付物缺失阻塞部署）。 |
| `dispatcher_config_sync` | dispatcher 配置变更同步证据：配置 mtime 新于文档时，文档必须同步更新（doc 新于 config 或同时）——防'已同步'假声称 |
| `dpm_section10` | DPM 交互文档第10节字段约束表存在性：缺此节 → 测试角色退回补充，禁止凭猜测编造边界（min/max 单元格空值语义校验留待批次2脚本化） |
| `engine_literal_scan` | 短板2防复发闸（2026-08-20 REFORM-GATE 判A）：「引擎零业务常量」从软规则升级为机械扫描。 |
| `exp_doc_shell` | 经验文档空壳检测（P3 · 2026-08-15 REFORM-GATE 判A）：角色经验文件 <200 字节判空壳。 |
| `field_consumer` | 字段修改前验证消费闸（01_workflows.md 规则24，2026-08-16 开关化）：修改任何配置/规则/YAML 字段前，必须实证 {field_name} 在 {… |
| `first_push_audit` | L2 开关第一推动事后审计闸（2026-08-17 REFORM-GATE 判立即改落地，短板A改造）：无钩子环境下'何时该扳开关'靠自觉、不扳不留痕。 |
| `flow_state_load` | 流程A 步骤0-B 状态加载闸（01_workflows.md L257 区，2026-08-16 开关化）：进入步骤1之前 PM 必须创建/读取 {project}/.flo… |
| `func_signature` | 规则27 函数签名实证（半开关）：写测试调用前实证被测函数存活与真实签名，判 A 贴签名原文；判 B=已删除/重命名禁止凭记忆 |
| `generalize_gate` | GENERALIZE-GATE 填充完整性+模式库登记机械校验（2026-08-17 存量清算落地，仿 reform_gate.json 骨架，rules/11 第五节骨架化）… |
| `goal_gate` | 长期目标创建/续轮前置闸（2026-08-20 用户裁定废弃自主修码任务并根治重复触发落地点）。 |
| `loop_fuse` | 规则32 复刻循环熔断：3轮未过强制升级/同源补丁>2次熔断/超轮上限熔断，计数留痕 jsonl 不凭记忆 |
| `merge_gate` | parallel-dispatch SLOT-MERGE 合并槽门禁：四道校验中可机械化的两道——a) 文件级冲突（两分身改同一文件即违例）b) 产物完整性（期望清单差集为空）… |
| `no_abs_path` | 绝对路径硬编码零容忍 tripwire（2026-08-20 三短板根源治理 M2，REFORM-GATE v2 判A）：活体代码禁止字面量 /Users/* 路径——写死即换… |
| `parasite_nest_claim` | 寄生巢落巢实证闸（CLAIM-GATE 族）：声称某寄生虫已落巢时扳本闸。 |
| `perf_no_sleep` | 性能规范机械闸（rules/10 L155，2026-08-17 存量清算落地）：交付源码禁止固定 sleep/人为阻塞代码。 |
| `plan_select_contract` | plan_select.py 四态契约回归闸（CLAIM-GATE 族复用件，2026-08-19 落地）：闸脚本 plan_select.py 改动后「声称已还原/已修复」的… |
| `ppt_delivery` | ppt-direct 节点3 交付实证闸（2026-08-17 C域开关化，SKILL.md L276-277）：机械核验成品已复制到 ~/Desktop/{name}.ppt… |
| `ppt_extract_mode` | ppt 节点03 分流判定：A=executed（模板目录存在且含 page_*.png，走解析+复刻）；B=passthrough（无模板，violations 即 pass… |
| `ppt_gate_a` | ppt 主链 Gate A（设计决策出口，2026-08-15 裁定自归档 legacy-workflow 引擎迁移 gate-switch）：主线06 质检通过后、主线07 渲… |
| `prd_inputs` | 项目前置输入准入闸（01_workflows.md 规则6，2026-08-16 开关化）：用户上传压缩包或给出项目路径时，PM 必须先校验 {project}/.prd.md… |
| `problem_gate` | 问题闸（2026-08-20 用户裁定独立成闸并亲定核心逻辑决策树）。 |
| `receipt_gate` | parallel-dispatch SLOT-RECEIPT 回报槽门禁：分身结构化回报五字段契约机械校验（status 枚举 / artifacts 数组与存在性 / dev… |
| `reform_exit_guard` | 请示出口闸（2026-08-17 用户裁定，扳手性质禁软提示词）：改造方案/建议出口后或复盘审计时扳本闸——E1 会话出口文本含请示句式（是否需要我/要不要执行/等你确认 等）… |
| `reform_gate` | REFORM-GATE 填充完整性+层位一致性机械校验（2026-08-19 v4：从查填没填到查层位对不对；2026-08-20 v5 定版：问题闸核心逻辑决策树四节点必填（… |
| `resume_delivery` | resume-direct 节点3 交付实证闸（对齐 ppt_delivery，2026-08-17 改造）：机械核验成品已复制到 ~/Desktop/{name}.pptx—… |
| `rules_inflation_guard` | 01_workflows.md 规则通胀拆分守护闸（2026-08-20 REFORM-GATE 判 A，Shard A 落地）：① 主文件瘦身 ≤300 行（强制规则全文+分… |
| `safety_cmd_audit` | 安全铁律事后审计闸（2026-08-17 REFORM-GATE 判立即改落地，短板B改造；2026-08-20 补铁律8查点）：扫 旧版 会话 jsonl 的 tool/c… |
| `scope_boundary` | 范围边界机械拦截（SV-GATE-001 重生版：git diff 变更文件集 vs 范围清单集合运算，替代旧 YAML 文本关键词桩）。 |
| `session_compliance_audit` | 会话合规审计合并闸（2026-08-19 复盘闸族瘦身，REFORM-GATE 判 A 落地）：原 first_push_audit（F1-F8 该扳未扳，F8=查询闸漏扳后查… |
| `shard_result_gate` | 分身结果落盘核验（2026-08-17 结果落盘制落地，parallel-dispatch 三槽契约 SLOT-PRE ⑦ / SLOT-RECEIPT）：母体收编每路分身成果… |
| `stat_citation` | 统计引用口径闸（2026-08-20 问题闸+REFORM-GATE 双判A，挂 CLAIM-GATE 族）——任何统计结论（命中率/通过率/比率/占比）出口前机械三查+时效一查。 |
| `task_launch_gate` | 会话循环熔断：每次任务发起前置记账（按会话维度），同会话同一任务累计发起>3次（第4次）禁止加入并上报用户决定；复盘动作清空当前会话任务版。 |
| `test_executor_evidence` | 测试执行证据门：接件校验+证据完整性。A=证据链完整可交付；B=拒绝执行/标记证据异常，violations 即异常清单（防假证据假通过率） |
| `testlead_dispatch` | test-lead 三路下发门禁：输出三路输入齐备向量。A=三路齐全部下发；B=按 violations 识别缺口路——缺哪路搁置哪路（B 不是全停，其余路正常并行，viola… |
| `todo_resend_audit` | L2 TodoList 重发义务事后审计闸（2026-08 REFORM-GATE 判立即改落地）：旧版 todos 投影 turn 级清零是外部既定语义，goal 续轮与子… |
| `whitebox_html_delivery` | whitebox-coverage 终判 HTML 报告桌面交付实证闸（2026-08-17 C域开关化，块4 retro-pm-129 同类）：机械核验 HTML 报告已复制… |
| `whitebox_mode` | 白盒模式门禁：有完整基线→A(diff 增量)；缺基线→B(full 全量，violations 即缺失理由) |
| `zero_residual` | 零残留参数化模板闸（2026-08-16 开关化，一模三绑）：机械核验 {pattern} 在 {path}（支持 glob）内命中数==0。 |

### C. 规则文档包（4）

| `workflow-governance` | 多智能体工作流治理规则包：目录安全铁律、流程A/B/C 全流程、任务路由。 |
| `roles-and-standards` | 角色职责与工程标准规则包：角色分工、工程技能、开发规范、性能优化。 |
| `test-quality-system` | 测试质量体系规则包：测试分层、质量门禁、UI 技能规则。 |
| `governance-archive` | 治理规则与归档史规则包：全局治理规则、历史裁定归档、寄生巢机制。 |
