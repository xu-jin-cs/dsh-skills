# gate-switch spec 索引台账（SPEC-INDEX）

> 生成时间：2026-08-20 12:09 · 生成方式：脚本扫描 specs/*.json + gate_switch.jsonl 使用留痕统计（2026-08-20 问题闸全量复审后重生成：9 闸撤除归档 specs/archive/，见 REPORT_ALL96.md）
> 防漂移纪律：新增/退役 spec 必须同步本表；本表 spec 数与目录 glob 数不一致即漂移（可用 grep_count 机械校验）。
> 总览：85 个 spec · 累计真实扳动 990 次

| # | spec 文件 | gate 名 | 检查项数 | 真实扳动次数 | 用途 |
|--:|---|---|--:|--:|---|
| 1 | acceptance_verdict.json | acceptance_verdict | 8 | 12 | 验收 verdict 禁止手写：验收经理必须跑本门禁照抄结论。A=机械校验全过（可判 PASS 进入软层语义复审）；B= |
| 2 | anchor_registry_audit.json | anchor_registry_audit | 2 | 3 | 锚点登记审计闸（2026-08-18 用户裁定采纳锚点注册表补位后落地，REFORM-GATE 判A；first_pus |
| 3 | api_report_check.json | api_report_check | 1 | 2 | api-test-engineer 汇报照抄核验：汇报文本的 exit code/gate_result/计数必须与 a |
| 4 | archmap_diff_freshness.json | archmap_diff_freshness | 1 | 11 | archmap 复盘前 diff 留痕固定卡点（REFORM-GATE 激活战役 item1，2026-08-15 裁定 |
| 5 | archmap_sync_freshness.json | archmap_sync_freshness | 1 | 2 | archmap ETL 配置契约报告新鲜度机械闸（2026-08-16 D 域批量开关化，archmap/SKILL.m |
| 6 | backup_hygiene.json | backup_hygiene | 2 | 3 | 备份与目录卫生闸（2026-08-20 REFORM-GATE 判A落地，Shard C 清算配套）：机械核验治理域（~ |
| 7 | be_api_schema.json | be_api_schema | 12 | 2 | backend-engineer 交付物 .api-schema.json 机械自检（REFORM-GATE 改造 P5 |
| 8 | bug_fix_gate.json | bug_fix_gate | 1 | 31 | bug-fix-strategy 修复级别机械门禁（2026-08-15 裁定）：script_exit 包装 bug_ |
| 9 | case_selfcheck.json | case_selfcheck | 2 | 6 | test-case-designer Step5 自检门禁（2026-08-15 裁定）：自检判定禁止手写，机械校验 1 |
| 10 | clarify_gate.json | clarify_gate | 8 | 3 | CLARIFY-GATE 需求五要素齐备性声明填充完整性机械校验：ui-designer Phase 0 判闸。把「需求 |
| 11 | council_gate.json | council_gate | 1 | 9 | review-council 三闸机械门禁（2026-08-15 裁定）：证据闸（file:line 锚点真实存在且行号 |
| 12 | council_reverify.json | council_reverify | 3 | 4 | review-council 对抗复核留痕机械闸（2026-08-16 D 域批量开关化，SKILL.md 06 对抗复 |
| 13 | danger_cmd_gate.json | danger_cmd_gate | 1 | 27 | 危险命令事前闸（铁律7，2026-08-17 存量清算落地）：bash 执行涉 rm/cp递归/find -delete |
| 14 | deploy_admission.json | deploy_admission | 5 | 2 | 部署启动准入（DEPLOY-001 重生版：交付物缺失阻塞部署）。A=三项全满足放行 Step1；B=拒绝启动，viol |
| 15 | dev_selfcheck.json | dev_selfcheck | 1 | 2 | Bug 修复提交前开发自检闸（01_workflows.md 流程B 强制自检，2026-08-16 开关化）：修复提交 |
| 16 | dispatcher_admission.json | dispatcher_admission | 1 | 14 | retro-skill-dispatcher GENERATE 准入禁止手工自觉（2026-08-15 裁定）：PM 在 |
| 17 | dispatcher_config_sync.json | dispatcher_config_sync | 2 | 4 | dispatcher 配置变更同步证据：配置 mtime 新于文档时，文档必须同步更新（doc 新于 config 或同 |
| 18 | dpm_section10.json | dpm_section10 | 4 | 1 | DPM 交互文档第10节字段约束表存在性：缺此节 → 测试角色退回补充，禁止凭猜测编造边界（min/max 单元格空值语 |
| 19 | dpm_skill_entry.json | dpm_skill_entry | 4 | 2 | dpm 学习成果入技能表实证（2026-08-20 技能表化，克隆 spm_skill_entry 换路径）：交互文档复 |
| 20 | engine_health.json | engine_health | 1 | 19 | 引擎探针闸（2026-08-16 B 域开关化）：治「引擎离线时 Agent 静默降级为软执行」的提示词执行失效。机械核 |
| 21 | engine_literal_scan.json | engine_literal_scan | 2 | 6 | 短板2防复发闸（2026-08-20 REFORM-GATE 判A，块文件 ~/.agents/logs/reform_ |
| 22 | exp_doc_shell.json | exp_doc_shell | 2 | 2 | 经验文档空壳检测（P3 · 2026-08-15 REFORM-GATE 判A）：角色经验文件 <200 字节判空壳。挂点 pm/flow.yml 经验空壳审计步（2026-08-20 重建，审计误判零引用已复盘） |
| 23 | field_consumer.json | field_consumer | 1 | 4 | 字段修改前验证消费闸（01_workflows.md 规则26，2026-08-16 开关化）：修改任何配置/规则/YA |
| 24 | first_push_audit.json | first_push_audit | 1 | 17 | L2 开关第一推动事后审计闸（2026-08-17 REFORM-GATE 判立即改落地，短板A改造）：无钩子环境下'何 |
| 25 | flow_state_load.json | flow_state_load | 3 | 2 | 流程A 步骤0-B 状态加载闸（01_workflows.md L257 区，2026-08-16 开关化）：进入步骤1 |
| 26 | frontend_testid.json | frontend_testid | 1 | 7 | frontend data-testid 锚点注入完整性实证：proto 可交互组件 id 与源码 data-testi |
| 27 | func_signature.json | func_signature | 1 | 2 | 规则29 函数签名实证（半开关）：写测试调用前实证被测函数存活与真实签名，判 A 贴签名原文；判 B=已删除/重命名禁止 |
| 28 | generalize_gate.json | generalize_gate | 7 | 21 | GENERALIZE-GATE 填充完整性+模式库登记机械校验（2026-08-17 存量清算落地，仿 reform_g |
| 29 | harness_sync.json | harness_sync | 1 | 5 | Harness 步骤同步一致性闸（01_workflows.md 规则9 + pm/SKILL.md 硬性全局约束1，2 |
| 30 | loop_fuse.json | loop_fuse | 1 | 7 | 规则34 复刻循环熔断：3轮未过强制升级/同源补丁>2次熔断/超轮上限熔断，计数留痕 jsonl 不凭记忆 |
| 31 | merge_gate.json | merge_gate | 2 | 2 | parallel-dispatch SLOT-MERGE 合并槽门禁：四道校验中可机械化的两道——a) 文件级冲突（两分 |
| 32 | no_abs_path.json | no_abs_path | 6 | 3 | 绝对路径硬编码零容忍 tripwire（2026-08-20 三短板根源治理 M2，REFORM-GATE v2 判A） |
| 33 | parasite_nest_claim.json | parasite_nest_claim | 4 | 1 | 寄生巢落巢实证闸（CLAIM-GATE 族）：声称某寄生虫已落巢时扳本闸。A=巢存储文件中该宿主闸的模板队列确含该任务且 |
| 34 | perf_no_sleep.json | perf_no_sleep | 1 | 2 | 性能规范机械闸（rules/10 L155，2026-08-17 存量清算落地）：交付源码禁止固定 sleep/人为阻塞 |
| 35 | plan_select_contract.json | plan_select_contract | 1 | 2 | plan_select.py 四态契约回归闸（CLAIM-GATE 族复用件，2026-08-19 落地）：闸脚本 pl |
| 36 | post_gate_audit.json | post_gate_audit | 1 | 7 | POST_GATE_AUDIT 复核报告锚点化+勾稽化机械门禁（2026-08-16 REFORM-GATE 裁定，ru |
| 37 | ppt_asset_gate.json | ppt_asset_gate | 2 | 4 | ppt 主链素材三禁令合并闸（2026-08-17 C域开关化，分类产物 /tmp/all_classification |
| 38 | ppt_delivery.json | ppt_delivery | 1 | 6 | ppt-direct 节点3 交付实证闸（2026-08-17 C域开关化，SKILL.md L276-277）：机械核 |
| 39 | ppt_design_trace.json | ppt_design_trace | 1 | 10 | ppt-direct 设计溯源一致性机考闸（2026-08-17 扳手改造，retro-pm-084 对策：复刻成品四不 |
| 40 | ppt_direct_scorecard.json | ppt_direct_scorecard | 1 | 13 | ppt-direct 四维门禁机考分项实证：矢量合规与交付完整性必须 pptx_check.py 退出码 0 才允许记分 |
| 41 | ppt_extract_mode.json | ppt_extract_mode | 2 | 4 | ppt 节点03 分流判定：A=executed（模板目录存在且含 page_*.png，走解析+复刻）；B=passt |
| 42 | ppt_gate_a.json | ppt_gate_a | 14 | 2 | ppt 主链 Gate A（设计决策出口，2026-08-15 裁定自归档 xujin-workflow 引擎迁移 ga |
| 43 | ppt_gate_b.json | ppt_gate_b | 1 | 2 | ppt 主链 Gate B（渲染产物出口，2026-08-15 裁定自归档 xujin-workflow 引擎迁移 ga |
| 44 | ppt_shots_seq.json | ppt_shots_seq | 2 | 4 | ppt-direct 节点0 模板逆向解析输入闸（2026-08-17 C域开关化，SKILL.md 输入校验规则 L1 |
| 45 | prd_inputs.json | prd_inputs | 2 | 2 | 项目前置输入准入闸（01_workflows.md 规则6，2026-08-16 开关化）：用户上传压缩包或给出项目路径 |
| 46 | problem_gate.json | problem_gate | 6 | 113 | 问题闸（2026-08-20 用户裁定独立成闸并亲定核心逻辑决策树）。核心逻辑：①这个问题，能不能一次性根治？→ 能：直 |
| 47 | process_audit_core.json | process_audit_core | 1 | 5 | process-audit 核心五维机械门禁（2026-08-17 扳手改造）：audit_core.py 从引擎 HT |
| 48 | publish_sync_gate.json | publish_sync_gate | 1 | 5 | 技能发布同步闸（2026-08-17 存量清算落地）：对外分发/更新技能后、声称'已发布'前扳本闸。P1 两个用户根符号 |
| 49 | receipt_gate.json | receipt_gate | 1 | 2 | parallel-dispatch SLOT-RECEIPT 回报槽门禁：分身结构化回报五字段契约机械校验（status |
| 50 | reform_exit_guard.json | reform_exit_guard | 1 | 3 | 请示出口闸（2026-08-17 用户裁定，扳手性质禁软提示词）：改造方案/建议出口后或复盘审计时扳本闸——E1 会话出 |
| 51 | reform_gate.json | reform_gate | 18 | 181 | REFORM-GATE 填充完整性+层位一致性机械校验（2026-08-19 v4：从查填没填到查层位对不对；2026- |
| 52 | registry_integrity.json | registry_integrity | 1 | 12 | retro-skills-registry 新增条目完整性机械闸（2026-08-16 D 域批量开关化，retro-s |
| 53 | resume_delivery.json | resume_delivery | 1 | 6 | resume-direct 节点3 交付实证闸（对齐 ppt_delivery，2026-08-17 改造）：机械核验成 |
| 54 | resume_direct_scorecard.json | resume_direct_scorecard | 1 | 11 | resume-direct 机考分项实证（对齐 ppt_direct_scorecard，2026-08-17 改造）： |
| 55 | resume_scorecard.json | resume_scorecard | 1 | 3 | resume 96% 复刻精度门禁机考（2026-08-15 裁定，裁判运动员分离）：主线06 放行判定禁止模型自打分， |
| ~~56~~ | **2026-08-22 废止：技能命中/retro召回指标废除（用户终裁），spec 归档 abolished_skill_hitrate_20260822** |
| 57 | retro_generate_token.json | retro_generate_token | 2 | 30 | 复盘 GENERATE 嵌入执行实证：复盘启动时先 touch {marker} 标记文件；着陆检查前跑本门禁，注册表与 |
| ~~58~~ | **2026-08-22 废止：技能命中/retro召回指标废除（用户终裁），spec 归档 abolished_skill_hitrate_20260822** |
| 59 | retro_match_gate.json | retro_match_gate | 1 | 3 | 流程B retro 匹配硬证据闸（01_workflows.md 步骤1.5 + pm/SKILL.md MATCH 模 |
| 60 | retro_match_score.json | retro_match_score | 1 | 2 | retro-subagent 复盘报告 match_score 反编造机械门禁（2026-08-15 裁定）：重跑 de |
| 61 | rules_inflation_guard.json | rules_inflation_guard | 12 | 2 | 01_workflows.md 规则通胀拆分守护闸（2026-08-20 REFORM-GATE 判 A，Shard A |
| 62 | safety_cmd_audit.json | safety_cmd_audit | 1 | 13 | 安全铁律事后审计闸（2026-08-17 REFORM-GATE 判立即改落地，短板B改造）：扫 DSH 会话 json |
| 63 | scope_boundary.json | scope_boundary | 1 | 5 | 范围边界机械拦截（SV-GATE-001 重生版：git diff 变更文件集 vs 范围清单集合运算，替代旧 YAML |
| 64 | security_baseline.json | security_baseline | 6 | 5 | 安全左移基线闸（2026-08-17 REFORM-GATE 判A落地）：新项目/引擎交付前与 engine_healt |
| 65 | session_compliance_audit.json | session_compliance_audit | 3 | 12 | 会话合规审计合并闸（2026-08-19 复盘闸族瘦身，REFORM-GATE 判 A 落地）：原 first_push |
| 66 | shard_result_gate.json | shard_result_gate | 2 | 157 | 分身结果落盘核验（2026-08-17 结果落盘制落地，parallel-dispatch 三槽契约 SLOT-PRE  |
| 67 | slot_attribution.json | slot_attribution | 1 | 3 | SLOT 回链闸（2026-08-16 B 域开关化）：治「裁决铁律不归因不收尾被静默跳过」的提示词执行失效。机械核验  |
| 68 | spm_skill_entry.json | spm_skill_entry | 4 | 4 | spm 学习成果入技能表实证（2026-08-20 技能表化改造落地）：复盘学习模式声称『已入技能表』前必扳——新条目文 |
| 69 | statestore_wiring_diff.json | statestore_wiring_diff | 1 | 3 | 短板3防复发闸（2026-08-20 REFORM-GATE 判A，块文件 ~/.agents/logs/reform_ |
| 70 | sv_precheck.json | sv_precheck | 1 | 2 | sv-supervisor 步骤切换前置校验机械闸（2026-08-16 D 域批量开关化，SKILL.md 6.3 前 |
| 71 | sv_verdict.json | sv_verdict | 1 | 6 | sv-supervisor 终裁 verdict 禁止手写（2026-08-15 裁定）：终裁结论必须跑本门禁照抄输出。 |
| 72 | task_breakdown.json | task_breakdown | 1 | 7 | 任务拆解输出机械门禁（2026-08-15 裁定）：八字段齐全且非空 / size∈{S,M,L,XL} / deps  |
| 73 | tcd_baseline.json | tcd_baseline | 1 | 3 | test-case-designer 基线差异消费机械闸（2026-08-16 D 域批量开关化，SKILL.md St |
| 74 | tdd_red_evidence.json | tdd_red_evidence | 1 | 2 | TDD RED 证据门：每条技术用例必须有 .tdd_red/<case_id>.log（含失败特征）+.exit（非0 |
| 75 | te_tracker_independent.json | te_tracker_independent | 1 | 5 | test-executor 执行追踪器独立证据源门（2026-08-17 V3复检块3）：治「追踪器自报自验」结构性盲点 |
| 76 | test_executor_evidence.json | test_executor_evidence | 7 | 2 | 测试执行证据门：接件校验+证据完整性。A=证据链完整可交付；B=拒绝执行/标记证据异常，violations 即异常清单 |
| 77 | testlead_dispatch.json | testlead_dispatch | 4 | 2 | test-lead 三路下发门禁：输出三路输入齐备向量。A=三路齐全部下发；B=按 violations 识别缺口路—— |
| 78 | todo_resend_audit.json | todo_resend_audit | 1 | 10 | L2 todo_write 重发义务事后审计闸（2026-08 REFORM-GATE 判立即改落地）：DSH todo |
| 79 | trigger_corpus_alignment.json | trigger_corpus_alignment | 1 | 35 | GENERATE 出口闸（2026-08-17 REFORM-GATE 判 A，用户裁定'每次对接非概率对接'）：当日新 |
| 80 | ui_case_check.json | ui_case_check | 1 | 1 | ui-test-engineer 白名单合规：action∈11白名单、禁动态 class 选择器、首选非 xpath— |
| 81 | whitebox_html_delivery.json | whitebox_html_delivery | 3 | 3 | whitebox-coverage 终判 HTML 报告桌面交付实证闸（2026-08-17 C域开关化，块4 retr |
| 82 | whitebox_mode.json | whitebox_mode | 3 | 5 | 白盒模式门禁：有完整基线→A(diff 增量)；缺基线→B(full 全量，violations 即缺失理由) |
| 83 | whitebox_report_consistency.json | whitebox_report_consistency | 1 | 2 | 白盒报告核心数字↔JSON 证据一致性机械闸（2026-08-16 D 域批量开关化，whitebox-coverage |
| 84 | whitebox_scope.json | whitebox_scope | 1 | 2 | 白盒增量回归范围圈定单刀双掷开关（2026-08-16 用户裁定「加扳手进去」）：治「Agent 不读 diff_imp |
| 85 | zero_residual.json | zero_residual | 1 | 4 | 零残留参数化模板闸（2026-08-16 开关化，一模三绑）：机械核验 {pattern} 在 {path}（支持 gl |
| 86 | goal_gate.json | goal_gate | 4 | 4 | 长期目标创建/续轮前置闸（2026-08-20 根治误授权烧token）：objective 非空+max_goal_rounds∈[1,10]+user_requested 声明；B/CLARIFY 拒绝创建。挂点 SOFT-GOAL-GATE |
| 87 | task_launch_gate.json | task_launch_gate | 1 | 0 | 会话任务版循环熔断（2026-08-20 REFORM-GATE 判A，K3循环烧满额度触发）：任务发起前置记账，同会话同任务累计发起>3次（第4次）判B禁止加入并上报用户决定；复盘动作清空当前会话任务版。计数留痕 ~/.agents/logs/task_launch/<session>.jsonl |
| 88 | stat_citation.json | stat_citation | 1 | 0 | 统计引用口径闸（2026-08-20 问题闸+REFORM-GATE 双判A，挂 CLAIM-GATE 族）：任何统计结论（命中率/通过率/比率/占比）出口前机械三查+时效一查。注：补登记于 2026-08-20（此前遗漏于 INDEX，本次防漂移复核补齐）；尚无真实扳动记录，勾稽口径挂接待补 |
| 86 | skill_value_gate.json | skill_value_gate | 3 | 16 | GENERATE 准入价值闸（2026-08-22 块H/块K 判A：三态 A/MERGE/B + DEDUP_COUNT 晋升三段式） |
| 87 | component_freshness.json | component_freshness | 1 | 3 | 成分标定新鲜度闸（2026-08-22 块L：pipeline_hash/语料漂移判B强制重标） |
