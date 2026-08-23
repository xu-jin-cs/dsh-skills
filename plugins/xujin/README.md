# xujin —— DeepSeek Harness 专属工程治理插件

> 仓库：https://github.com/xu-jin-cs/dsh-skills （插件目录 `plugins/xujin`）

本插件为 100% 原创、仅适配 DeepSeek Harness（DSH / Cordis）生态的外置增强治理插件，不属于 DSH 官方原生内核，为独立自研架构扩展层。
不通用、不支持其他 Agent 框架，所有机制、闸规则、状态机、检索架构专为 DSH-Harness 事件总线、任务调度、会话生命周期深度定制。

## 原创架构溯源声明（公开确权）

本 xujin DSH 技能插件 v1.4.0 为作者独立原创设计，完整自研体系包括：

- L1 声明闸 / L2 机械扳手闸 / L3 交付校验闸 三层分层门禁体系
- 寄生巢并行分身执行机制（宿主闸产出副本、并行隔离、失败不连坐）
- Plan-Select 多维方案择优引擎
- Dual-Gates 双闸检索前置架构（声明定性 + 定向溯源检索）
- 78 份可机械判定 Spec 零裁量门禁系统
- 17 态标准化工程流程状态机
- 完整闸序总线：问题闸 → 计划闸 → 收益闸 → 并行闸

整套体系为 DSH-Harness 生态独有扩展设计，所有公开引用、二次学习、二次改造必须保留本溯源声明。

## 开源模式说明（防摘桃子）

本项目采用 Source-Available 源码可见模式：

- ✅ 允许：个人学习、本地部署、内部 DSH 环境自用
- ❌ 禁止：未授权 Fork、二次公开发布、改包重发、商用售卖、对外 SaaS 服务
- ❌ 禁止：移植到其他 AI/Agent 框架开源发布

完整约束见仓库根目录 LICENSE 文件。

## DSH-Harness 专属适配说明

本插件所有能力强依赖 DSH 原生机制：

- 依赖 DSH Cordis 事件总线注入规则
- 依赖 DSH 会话 Turn 生命周期、任务调度模型
- 依赖 DSH 插件加载体系、Profile 机制、CLI 运行时
- 依赖 DSH 原生 Read/Grep/Glob 检索链路做闸前置拦截

无法脱离 DSH-Harness 独立运行，不属于通用开源框架。

## 统一术语对照表（DSH 专属）

| 术语 | DSH 专属释义 |
|---|---|
| L1/L2/L3 分层闸 | DSH 外置三层治理：L1 路由声明、L2 机械判定、L3 交付终审 |
| 寄生巢分身 | DSH 任务并行扩展：单任务派生多分身、隔离执行、独立落盘 |
| 双闸 Dual-Gates | DSH 检索强管控：先定性、再检索，杜绝无边界乱查、幻觉溯源 |
| 四态退出码 | DSH 闸控统一标准：0 放行 / 2 阻断 / 3 澄清 / 4 违规 |
| Plan-Select 引擎 | DSH 需求求解择优机制，最低步骤、最高复用优先级决策 |
| 闸序总线 | DSH 多闸联动固定顺序，杜绝模型乱执行、乱跳过门禁 |

---

## 一、一键下载与安装

**前置准备**：本地已安装 DeepSeek Harness CLI（终端可执行 `dsh`），Node.js ≥ 20。

**macOS / Linux**——复制三行粘贴到终端：

```bash
curl -LO https://github.com/xu-jin-cs/dsh-skills/releases/latest/download/xujin-1.4.0.tgz
curl -LO https://github.com/xu-jin-cs/dsh-skills/releases/latest/download/install.sh
bash install.sh
```

> 备用直链（任何时候可用）：把上面 URL 换为
> `https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/plugins/xujin/dist/xujin-1.4.0.tgz`
> `https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/plugins/xujin/dist/install.sh`

**Windows PowerShell**：

```powershell
Invoke-WebRequest -Uri "https://github.com/xu-jin-cs/dsh-skills/releases/latest/download/xujin-1.4.0.tgz" -OutFile "xujin-1.4.0.tgz"
Invoke-WebRequest -Uri "https://github.com/xu-jin-cs/dsh-skills/releases/latest/download/install.sh" -OutFile "install.sh"
bash install.sh   # 推荐 Git Bash / WSL 执行
```

> 默认装入 `web` profile；装其他 profile：`bash install.sh default`。
> 安装内容：插件本体 + 2 个 CLI shim（`~/.dsh/bin/xujin-gate` / `xujin-engine`）+ 查询闸焊点插件 dsh-trigger-auto。

**安装校验**：

```bash
dsh plugin --profile web list    # 列表中出现 xujin 与 dsh-trigger-auto 即成功
```

重启 DSH（或等热重载）后：会话技能目录出现 `rule-00-root-safety` ~ `rule-13-workflow-router` 等 19 份规则技能与 7 个原子技能；终端执行 `~/.dsh/bin/xujin-gate 任意名` 能列出可用 spec 清单（共 78 份）即闸引擎可用。

**卸载**：`bash uninstall.sh`（默认 web profile）——插件、查询闸焊点、CLI shim 全部移除，DSH 重载后自动注销全部技能注册。

---

## 二、包内容总览（v1.4.0）

| 类别 | 数量 | 说明 |
|---|---|---|
| 规则技能 | 19 份 | 流程/角色/测试/治理全套规则，以技能形态注册、按需加载 |
| 原子技能 | 7 个 | 可直接调用的治理能力（含触发词，见第四节） |
| 闸 spec | 78 份 | 机械可判的 0/1 门禁，由 `xujin-gate` 执行（见第五节） |
| 引擎硬规则 | 5 组 53 条 + 17 状态状态机 | L1 调度/L3 校验/输出治理/强制路由（见第六节） |
| 随包插件 | dsh-trigger-auto | 查询闸焊点：检索动作前置定性（见第七节） |

---

## 三、规则技能（19 份）—— 告诉 Agent"应该怎么做"

| 技能名 | 作用 |
|---|---|
| rule-00-root-safety | 零虚构原则 + 目录安全铁律，所有文件操作的根安全底线 |
| rule-01-workflows | 强制规则总纲 + 分片索引（最高优先级规则集中营） |
| rule-01a-flow-a-new-feature | 流程A：新增功能/项目开发 14 步全流程（PM 调度主线） |
| rule-01b-flow-b-bugfix | 流程B：Bug 修复链（经验匹配 → 归属分析 → 修复 → 精准回归） |
| rule-01c-flow-c-wrapup | 流程C：项目收尾（5 问法复盘门禁、经验沉淀、配置变更审计） |
| rule-01d-flow-de-aux | 流程D 代码图谱分析（按需）+ 流程E 纯测试模式（5 种执行模式） |
| rule-01e-retro-system | 复盘标准结构——四部分复盘模板与着陆规范 |
| rule-01f-appendix | 工程技能调度总表（何时调用哪个技能的查表） |
| rule-02-roles-responsibility | 角色职责规范（PM 规范、各 Agent 权责边界） |
| rule-03-engineering-skills | 工程技能规范（切片实现、调试排错 5 步法等） |
| rule-04-dev-standard | 通用开发规则 + 经验积累 + 补丁分发分级 |
| rule-05-test-quality-system | 测试通用规则（Q1-Q6 质量门禁体系、用例规范） |
| rule-07-ui-skill-rules | UI 技能专项规则 |
| rule-08-governance-rules | 全局治理规则 G 系列（输出治理、状态同步等） |
| rule-09-governance-archive | 治理规则归档（已废止条款的非阻断参考，防考古误判） |
| rule-10-performance-optimization | 通用性能优化编码规范（禁固定 sleep 等） |
| rule-11-gate-framework | 强制填充门元方法族：REFORM-GATE 收益门禁 / GENERALIZE-GATE 举一反三 / L1声明闸·L2开关闸·L3框架闸 选档判断树 |
| rule-12-parasite-nest | 寄生附属执行模式：宿主闸内置寄生巢任务模板队列，闸出口复制副本并行执行 |
| rule-13-workflow-router | 专用工作流路由强管控：注册表触发词精确匹配唯一准入、产物兼容校验、冲突熔断 |

---

## 四、原子技能（7 个）—— 作用与触发词

| 技能 | 作用 | 触发词/触发时机 |
|---|---|---|
| **gate-switch** | 通用概率执行门禁骨架：任何"声称 X 已满足/已写入/已验收"写成 spec 机械核验，全过掷点 A 放行、任一失败掷点 B 阻断并列违例。治"该做的没做、缺斤短两、伪造声称" | 验收判定、写入实证、证据核验、模式分流、交付完整性检查、部署准入 |
| **parallel-dispatch** | 并行调度与子分身机制总规则：PARALLEL-GATE 声明 + 单刀双掷开关（dispatch_switch）机械判定 parallel/sequential；文件数量纲双维决策；三槽契约；结果落盘制 | **无触发词依赖——多任务（≥2 子任务）出现即强制触发**；任务步骤（todo_write）出来后执行前必过 |
| **dual-gates** | 声明闸+查询闸双闸：意图硬路由（安全/问题信号）→ 机械指令不经裁量；2 字词根白名单 + 兜底词根 → 命中才进查询闸做会话锚点定向溯源检索 | /dual-gates、声明闸、查询闸、数据源检索前置判定；评估基准/方案/源码/历史记录读取前置路由 |
| **scope-boundary-gate** | 范围边界门禁：编码阶段拦截超范围开发，保障需求聚焦 | 编码阶段执行时 |
| **plan-select** | 方案择优引擎：3 维度槽位候选池（原生内置/历史复用/迭代效率），无效槽过滤防 0 分脏数据，最低步骤数最优直接执行，双校验失败顺位切换 | 用户抛需求/任务且需选择实现路径时 |
| **bug-fix-strategy** | Bug 最短路径修复策略：按优先级依次尝试禁止跳级，同一 Bug 重复 ≥2 次才进重构评估 | Bug 修复必经（流程B 强制先进入） |
| **idea-forge** | 设想锻造炉：粗糙设想按 11 维补齐清单自动补全设计，补齐部分标注来源，关键决策点必须问用户 | /idea-forge、设想补齐、我有个设想、帮我完善这个想法 |

---

## 五、闸（78 份 spec）—— 把"应该做"变成"必须过"

执行方式：`~/.dsh/bin/xujin-gate <闸名> [--set 键=值]`，四态退出码 0=A 放行 / 2=B 阻断 / 3=CLARIFY / 4=VIOLATION。判定禁止手写，模型只许扳闸照抄输出。

### 元方法闸族（想问题的闸）
| 闸 | 作用 | 触发节点 |
|---|---|---|
| reform_gate | **收益闸**：改造/新增机制/重构建议出口前强制填框架（问题定义→方案→收益五要素→判定），填不满意见视为不存在 | 改造建议出口前 |
| generalize_gate | 举一反三门禁：新机制采纳落地后强制评估泛化（1 实证+N 同类） | 新机制落地后 |
| problem_gate | 问题闸：能不能一次性根治的决策树四节点强制落盘 | 问题类输入 |
| clarify_gate | 需求五要素齐备性声明填充校验 | UI 设计 Phase 0 |
| plan_select_contract | plan-select 四态契约回归校验 | 择优脚本契约漂移防护 |
| goal_gate | 长期目标创建/续轮前置闸（防误授权烧 token） | goal 创建前 |

### 安全闸族（别闯祸的闸）
| 闸 | 作用 | 触发节点 |
|---|---|---|
| danger_cmd_gate | 危险命令事前闸：rm 递归/cp 递归/find -delete 等先落盘判 A 才执行 | bash 危险命令执行前 |
| safety_cmd_audit | 安全铁律事后审计（查漏扳/固定区块/打断弱审计） | 复盘期 |
| security_baseline | 新项目/引擎交付前 6 项安全基线 | 交付前 |
| backup_hygiene | 备份残渣零容忍归档（只 mv 不 rm） | 会话开始 |
| no_abs_path | 绝对路径硬编码零容忍 | 引擎/规则交付 |
| scope_boundary | git diff 变更文件集 vs 范围清单集合运算拦超范围 | 编码阶段 |

### 并行/分身闸族（多任务的闸）
| 闸 | 作用 | 触发节点 |
|---|---|---|
| shard_result_gate | 分身结果落盘核验：单片失败不连坐 | 收编每路分身前 |
| merge_gate | 合并槽门禁：文件级冲突+大纲完整性 | 分身成果合并前 |
| receipt_gate | 分身结构化回报五字段契约校验 | 分身回报时 |
| task_launch_gate | 同会话同任务第 4 次发起判 B（循环熔断） | 任务发起/重试前 |
| loop_fuse | 复刻循环熔断：3 轮未过升级/同源补丁>2 次熔断 | 每轮循环/补丁前 |
| parasite_nest_claim | 寄生巢落巢实证 | 声称已落巢时 |

### 声称实证闸族（别吹牛的闸）
| 闸 | 作用 | 触发节点 |
|---|---|---|
| stat_citation | 统计结论出口前口径机械三查+时效一查 | 命中率/通过率等出口前 |
| zero_residual | 回滚后特征字符串 0 残留才许宣告完成 | 回滚完成后 |
| field_consumer | 改配置字段前先实证该字段被引擎真实消费 | 字段修改前 |
| func_signature | 写测试调用前实证被测函数存活与真实签名 | 测试编写前 |
| publish_sync_gate | 声称"已发布"前查符号链接/未提交/未推送 | 发布声称前 |
| dispatcher_config_sync | 配置变更后文档同步证据 | 配置变更后 |
| harness_sync | 流程节点过闸后状态同步一致性 | Harness 同步 |
| flow_state_load | 流程A 步骤前状态加载核验 | 流程步骤切换 |

### 流程合规审计闸族（第一推动有没有漏扳）
| 闸 | 作用 | 触发节点 |
|---|---|---|
| session_compliance_audit | 会话合规合并闸：第一推动八查+安全三查+todo 重发一次扳完 | 复盘着陆前 |
| first_push_audit | 开关第一推动事后审计（倒逼事前自觉） | 复盘期 |
| todo_resend_audit | todo_write 重发义务逐 turn 后查 | 复盘期 |
| reform_exit_guard | 改造方案出口后查先斩后奏/跳闸 | 方案出口后 |
| post_gate_audit | 后置审计报告锚点化+勾稽化 | 审计复核 |
| slot_attribution | 裁决归因回链核验（防静默跳过） | 裁决收尾 |
| anchor_registry_audit | 数据源锚点登记完整性 | 产物收尾 |

### 引擎防复发闸族（引擎自己别退化）
| 闸 | 作用 | 触发节点 |
|---|---|---|
| engine_literal_scan | 引擎层业务字面量扫描（业务规则禁下沉引擎） | 引擎交付/复盘期 |
| statestore_wiring_diff | 实例状态直写 vs 统一收口差集 | 引擎交付/复盘期 |
| rules_inflation_guard | 规则行数上限/分片完整/断链清零 | 复盘期 |
| component_freshness | 成分标定新鲜度（漂移>5% 强制重标） | 成分值守 |

### 测试链闸族（测试质量）
| 闸 | 作用 | 触发节点 |
|---|---|---|
| acceptance_verdict | 验收结论禁止手写，照抄门禁输出 | 验收判定时 |
| testlead_dispatch | 测试三路（whitebox/api/ui）下发齐备向量 | 测试下发前 |
| case_selfcheck | 用例设计自检禁止手写 | 用例设计 Step5 |
| tcd_baseline | 精准回归必须真实消费基线差异 | 回归设计前 |
| test_executor_evidence | 测试执行证据链完整性（7 项） | 用例执行接件 |
| te_tracker_independent | 执行追踪器独立证据源（防自报自验） | 执行追踪 |
| tdd_red_evidence | TDD 每条技术用例必须有 RED 失败证据 | TDD 用例提交 |
| ui_case_check | UI 用例 action 白名单合规 | UI 用例交付 |
| api_report_check | 接口测试汇报与产物照抄一致性 | 接口测试汇报 |
| be_api_schema | 后端 .api-schema.json 机械自检（12 项） | 后端交付 |
| frontend_testid | 前端 data-testid 锚点注入完整性 | 前端交付 |
| dpm_section10 | 交互文档第 10 节字段约束表存在性 | 测试角色接件 |
| whitebox_mode / whitebox_scope / whitebox_report_consistency / whitebox_html_delivery / archmap_sync_freshness | 白盒五闸组：模式分流/增量范围圈定/报告数字一致性/HTML 交付实证/契约新鲜度 | 白盒链路各节点 |

### 出片链闸族（PPT/简历质量）
| 闸 | 作用 | 触发节点 |
|---|---|---|
| ppt_gate_a / ppt_gate_b | PPT 主链双闸：设计决策出口（14 项）/渲染产物出口 | PPT 主链节点 |
| ppt_delivery / resume_delivery | 成品交付实证 | 交付声称时 |
| ppt_design_trace | 复刻成品与设计决策溯源一致性 | 复刻目检 |
| ppt_direct_scorecard / resume_direct_scorecard / resume_scorecard | 机考分项实证（裁判运动员分离，禁止自打分） | 出片放行判定 |
| ppt_extract_mode | 模板目录存在性分流判定 | PPT 节点03 |
| ppt_shots_seq | 模板截图序列完整性 | 逆向解析输入 |
| ppt_asset_gate | 素材三禁令合并闸 | 素材下载后 |

### 流程角色自检闸族（各角色别偷懒）
| 闸 | 作用 | 触发节点 |
|---|---|---|
| prd_inputs | 项目前置输入准入（缺 PRD 禁止启动） | PM 启动前 |
| task_breakdown | 任务拆解输出八字段/size/deps 合法 | 拆解输出时 |
| dev_selfcheck | 修复提交前自检（旧名零残留+导入冒烟+依赖+文档） | Bug 修复提交前 |
| bug_fix_gate | 修复级别机械判定禁止跳级 | Bug 修复定级 |
| sv_precheck / sv_verdict | 监督者前置校验/终裁禁止手写 | 步骤切换/终裁 |
| process_audit_core | 流程审计核心五维 | 流程审计 |
| council_gate / council_reverify | 专家团证据锚点真实性/对抗复核留痕 | 体检报告出口 |
| deploy_admission | 部署启动准入（交付物缺失阻塞部署） | 部署 Step1 前 |
| exp_doc_shell | 经验文档空壳检测（<200 字节判空壳） | 经验审计 |
| spm_skill_entry / dpm_skill_entry | 学习成果入技能表实证 | 复盘学习模式 |
| dispatcher_admission | 复盘 GENERATE 准入禁止手工自觉 | 复盘沉淀前 |
| perf_no_sleep | 交付源码禁止固定 sleep/人为阻塞 | 代码交付 |
| registry_integrity | 复盘 registry 新增条目完整性 | 条目入库 |
| retro_generate_token / retro_match_score / trigger_corpus_alignment / skill_value_gate | 复盘闸组：GENERATE 实证/match_score 反编造/触发词语料见证/准入价值三态 | 复盘着陆链 |

> 另有 10 份闸因依赖外部服务未入包（engine_health、harness_sync、archmap_diff_freshness、backup_hygiene、engine_literal_scan、no_abs_path、security_baseline、statestore_wiring_diff、retro_match_gate、stat_citation）——完整环境可见源码仓库说明。

---

## 六、引擎 —— 硬规则与状态机

### 引擎硬规则（5 组 53 条，RuleGate 经 Cordis 事件总线注入，只改外置契约不动内核）

| 组 | 条数 | 作用 |
|---|---|---|
| orchestrator_rules（L1 调度层） | 25 | 状态机非法跳转拦截、task_breakdown 顺序锁、冒烟未过禁全量、P0/P1 未关闭禁审查、违规积分熔断、角色职权隔离（PM 禁 Bash/TCD 禁执行/FE 禁改契约）、分身数量上限 |
| deliverable_rules（L3 交付物） | 9 | 交付物必须真实存在、PRD 六要素、测试闭环必产 master report、ZIP 禁含 PRD/测试报告等 |
| directory_safety_rules（L3 目录安全） | 7 | 禁递归/通配删除、禁 git clean -fd、禁路径穿越等 |
| output_governance_rules（L3 输出治理） | 8 | 输出首段必须治理元数据块、代码禁止对话内展示、长文本必须落盘、大文本禁入状态等 |
| routing_rules（L1 强制路由） | 4 | 文档摘要/Bug 修复/收尾强制路由到指定处理链 |

### 流程状态机（17 状态）

```
PENDING → PRD_REVIEW → DESIGN → DEV_FRONTEND / DEV_BACKEND → PM_CONFIRM
        → SMOKE_TEST → FULL_TEST → CODE_REVIEW → DEPLOY → ACCEPTANCE → CLOSED
并行区：DESIGN → WAIT_BRANCH_AGGREGATE ⇄ SCAN_NEXT_BATCH → EXIT_PARALLEL_ZONE
任意态 → FROZEN；PM_CONFIRM / CODE_REVIEW / ACCEPTANCE → ROLLBACK
```

### 两个 CLI

```bash
# 扳闸（四态退出码 0=A / 2=B / 3=CLARIFY / 4=VIOLATION）
~/.dsh/bin/xujin-gate <闸名> [--set 键=值 ...]
~/.dsh/bin/xujin-gate --spec-file <路径> [--set 键=值 ...]   # 显式 spec 调试

# 引擎内核
~/.dsh/bin/xujin-engine sign --trace-id <id> --artifact '<json>'     # 交付物签发（防篡改）
~/.dsh/bin/xujin-engine verify --trace-id <id> --artifact '<json>' --signature <签名>
~/.dsh/bin/xujin-engine step-sync <项目> <节点> "<说明>" <角色>       # 状态同步（本地直写）
~/.dsh/bin/xujin-engine et payload.json                              # 六段流水线全链路
```

**两个前提**：① hmac-sha256 防伪签发需环境变量 `AGENT_ENGINE_SECRET`（无内置回落，未设置时中文报错；sha256 纯哈希模式无需密钥但只有完整性校验）；② 运行时数据落盘 `~/.dsh/xujin-engine/`（state/ 实例状态 + audit.jsonl 审计流）。

---

## 七、查询闸焊点（dsh-trigger-auto，随包安装）

安装后 Agent 每个 turn 首个 `read`/`grep`/`glob` 检索动作前，必须先过一次声明闸定性：

```bash
python3 ~/.agents/skills/dual-gates/scripts/dual_gates.py declare --raw "<本turn用户原始诉求>"
# 判 is_query → 续扳 query 闸定向溯源；判 not_query → 直接重试检索动作即放行
```

未定性直接检索会被事前阻断并给出上述指引——这是设计本意，不是故障。配套触发词兜底：`找` / `查询` / `寻找` 命中用户输入即提醒过闸。

---

## 八、触发信号总表（文本扫描层，命中即机械执行）

| 信号 | 触发词 | 命中后必扳 |
|---|---|---|
| S-QUERY | 找 / 查询 / 寻找 | dual_gates declare 定性 |
| S-RETRO-WORDS | 复盘/验收通过/项目完成/收尾/结项/完工/交付/关闭 | retro 匹配 + 复盘着陆闸族 |
| S-DANGER-CMD | rm/cp 递归/find -delete/mv 等 | danger_cmd_gate 判 A 才执行 |
| S-PUBLISH-CLAIM | 已发布 | publish_sync_gate 三项核验 |
| S-CLAIM-WORDS | 已写入/已生成/已同步/已验收 | CLAIM-GATE 族对应闸判 A |
| S-ENGINE | engine/引擎/harness/流程A/流程B/流程C//pm | engine_health 探针 |
| S-PERF | 性能规范相关交付 | perf_no_sleep 判 A |
| S-REFORM | 改造/新增机制/规则/重构 | reform_gate 收益闸判 A |
| S-PROBLEM-GATE | 问题类输入 | problem_gate 决策树判 A |
| S-STAT-CITE | 统计结论出口前 | stat_citation 口径核验 |
| S-PLAN-ENTRY | 怎么改/怎么做/怎么解决/怎么设计 | 计划闸进（plan-select → 收益闸 → 并行闸） |

**闸序总线**：多闸都经过时固定顺序——问题闸 → 计划闸 → 收益闸 → 并行闸（内置子分身逻辑判断）。

---

## 九、常见问题

| 现象 | 原因与处理 |
|---|---|
| 提示「资产包解析失败」 | assets/rules.json 损坏（传输截断/被篡改） → 重新下载完整插件包 |
| 提示「资产包结构异常」 | 包内资产缺 skills 数组 → 重新从官方渠道下载 |
| 闸命令报「不存在 spec」 | 插件版本过旧（v1.2 及以前资产包不含闸 spec） → 升级到 v1.4.0+ |
| 检索动作被阻断 | 查询闸焊点生效中（设计本意） → 按指引扳一次 declare 即放行 |

---

## 开发者区（重新打包）

```bash
node scripts/build_manifest.mjs                          # 1. 收集资产生成清单
node scripts/build_assets.mjs --manifest manifest.real.json   # 2. 明文打包资产
npm pack                                                  # 3. 打出分发包
```
## 十、最小运行 Demo（仅 DSH-Harness 环境可用）

必须在已安装 DeepSeek Harness 的终端环境执行：

```bash
# 执行标准门禁测试（纯检查原语闸，零配置直跑）
echo demo > /tmp/xujin_demo.txt
~/.dsh/bin/xujin-gate shard_result_gate --set result=/tmp/xujin_demo.txt
# → verdict: A（文件真实存在且非空），退出码 0；把路径改成不存在的文件即判 B（退出码 2）

# 问题闸（决策树四节点强制填充闸）标准用法：先把问题块落盘再过闸
~/.dsh/bin/xujin-gate problem_gate --set block=<问题块文件路径>

# 审计日志自动落盘（DSH 专属路径）
cat ~/.dsh/xujin-engine/audit.jsonl
```

## 免责与边界声明

本插件为 DeepSeek Harness 专属自研扩展，非官方内核组件，仅适配 DSH 生态。请勿移植至其他 Agent 框架公开分发。工具仅供技术研究与内部工程治理使用，上线业务需自行完成全量测试，作者不承担衍生业务风险。

