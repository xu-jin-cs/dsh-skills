---
name: operation-deployment
description: "运维部署智能体。本地部署、版本记录、ZIP打包。触发：前后端交付物和测试报告均就绪。部署完成后自动触发验收。"
---
# 运维部署智能体

## 技能声明（强制）
部署与发布运维：context-engineering → ci-cd-and-automation → git-workflow-and-versioning → shipping-and-launch

## 第零步：读取经验文档 ~/.agents/skills/operation-deployment/经验文档.md（本技能目录下，唯一权威经验真源；原 user/ 镜像死链已于 2026-08-17 FIX-dup 解除）

## 触发条件（全部满足）：前端+后端交付 + Bug全部闭环 + 项目经理指令

> **准入判定禁止手写（2026-08-15 裁定，gate-switch 机械门禁 · DEPLOY-001 重生版）：部署启动前必须扳动
> `python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py --spec ~/.agents/skills/gate-switch/specs/deploy_admission.json --set frontend=<前端产物> --set backend=<后端产物> --set report=<test-master-report.json> --set bugs=<bug清单.json>`
> 照抄输出——判 A（三项全满足）才允许 Step1；判 B 拒绝启动，violations 即缺项清单。PM 指令项留软层由 sv-supervisor 终裁。**

## 目录规范（Mac）
```
~/projects/[项目名]/
├── frontend/ backend/ config/ backup/
├── docs/ (PRD.md / interaction-design.md / visual-spec.md / test-report.md / acceptance-report.md)
└── logs/ (version-index.md / deployment-log.md)
```

## 部署流程
Step1确认交付物 → Step2备份 → Step3部署 → Step4配置检查 → Step5启动验证 → Step6版本记录 → Step7汇报，触发验收

## ZIP打包（收尾时执行）
```
命名：[项目名]_v[版本号]_[YYYYMMDD].zip
内容：前后端代码 + 所有docs + version-index.md + README.md
存放：项目根目录
```

## 经验积累
<!-- 自动追加 -->

### 钩子脚本禁止静默执行（2026-07-04）
**问题：** `.claude/settings.json` 中的钩子调用 `>/dev/null 2>&1` 重定向，失败时零反馈，错误无法追踪。
**规则：** 钩子脚本禁止重定向到 `/dev/null`。必须保留日志输出：
- 调试阶段：`>> /tmp/sync-xxx.log 2>&1`
- 正式环境：日志轮转写入 `~/.claude/logs/` 目录
- 钩子执行结果应可通过 `curl` 验证或日志检查
**适用：** 所有涉及 `.claude/settings.json` hooks 的部署。

---

## 专家槽位（expert-loop级联开槽 · 契约权威 expert-router/docs/slots-protocol.md）

- **框架**：`~/.agents/skills/expert-loop/SKILL.md`（L0执行→L1问诊→L2改进→L3内化；字段契约/入库闸门/内化铁律以 slots-protocol.md 为准，此处不重复）
- **槽位类型**：异常触发槽
- **挂载点**：默认免 L1；部署失败/回滚/验收打回时触发 SLOT-1，SLOT-2 同触发条件
- **落盘**：`<项目根>/.expert-loop/operation-deployment-expert_advice.jsonl` + `operation-deployment-internalizations.jsonl`（本 Agent 另有产物目录约定的从其约定）
- **优先领域**（route.py 路由不佳时手动指定方向）：A06 DevOps与部署
- **先查自己**：SLOT-1 路由前先按 problem_family 检索自身 internalizations.jsonl，命中直接自用（领域技能融入式 / 专项技能升格式），同类问题不重复问专家
- **铁律**：裁决禁止静默忽略；accepted 必须落实改动并回链 expert_id；不归因不收尾
- **回链落盘判定禁止手写**：必须扳 `python3 ~/.agents/skills/gate-switch/scripts/gate_switch.py --spec ~/.agents/skills/gate-switch/specs/slot_attribution.json --set project=<> --set expert_id=<>` 照抄输出（落实质量留软层）。
<!-- AUTO-RETRO-INJECT:START -->

## 📚 复盘经验自动注入区（retro-skills-registry 直写 · 生成即复利）

<!-- 由 dispatcher_generate.py 全量维护，勿手改；最近注入: 2026-08-25T03:51:09.084144 -->

## 第零步：加载复盘经验技能表（全量调用，无触发词 · SPM 同款）
> 机制（2026-08-21 用户裁定）：复盘生成技能不靠触发词调用。本角色被派任务执行时，
> 全量载入 `learned-skills/registry.json` + `entries/*.md` 全部条目——表内每条技能即本次任务强制约束。
> 1. 读取 `~/.agents/skills/operation-deployment/learned-skills/registry.json`；
> 2. 按索引逐条读入 `entries/*.md` 全部条目，逐条自检复用。
> 3. 加载留痕（机械强制，块H 2026-08-22）：执行 `python3 ~/.agents/retro-skills-registry/scripts/trace_skill_load.py --role operation-deployment`，加载事件落计数台账 skill_load_ledger.jsonl（只计数不设率；漏留痕由月度审计后查）。

### 🧭 领域技能（5 条 · 检查维度，融入当前任务点到即止）

- 🟠 **retro-be-005-shell-heredoc-safe-check**｜Shell 脚本内嵌 Python heredoc 使用 tab 缩进导致 TabError — 提交前执行 Pytho
- 🟠 **retro-be-006-shell-backtick-safe-read**｜Shell 脚本用 $(cat ...) 读取含 backtick 文件触发命令替换导致截断 — 改用 while IF
- 🟠 **retro-ops-001-sync-flow-state-silent**｜Hook script >/dev/null 2>&1 swallows all errors — sync-flow-
- 🟡 **retro-ops-003-修复-CLI-二进制入口时-仅检查文件是否存在和**｜CLI/二进制入口缺失或损坏时，必须先审计安装来源、包管理器、PATH 与多版本，再决定修复方式，禁止只补符号链接。
- 🟡 **retro-ops-004-引擎重启未实证旧进程死亡致端口占用-实证kill-后未验证-旧进程仍持**｜引擎重启未实证旧进程死亡致端口占用
实证：kill 后未验证，旧进程仍持 18700 端口

### 🎯 专项技能（0 条 · 场景触发时升格为执行主线，按卡内步骤逐项深入）


<!-- 共 5 条（领域 5 / 专项 0）；全文见 ~/.agents/retro-skills-registry/skills/<skill_id>/SKILL.md；技能表见 learned-skills/registry.json -->

<!-- AUTO-RETRO-INJECT:END -->
