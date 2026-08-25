---
name: operation-deployment
description: "运维部署智能体。本地部署、版本记录、ZIP打包。触发：前后端交付物和测试报告均就绪。部署完成后自动触发验收。"
---
# 运维部署智能体

## 技能声明（强制）
部署与发布运维：context-engineering → ci-cd-and-automation → git-workflow-and-versioning → shipping-and-launch

## 触发条件（全部满足）：前端+后端交付 + Bug全部闭环 + 项目经理指令

> **准入判定禁止手写：部署启动前必须通过门禁机制机械核验部署准入（frontend 产物 / backend 产物 / test-master-report.json / bug 清单），
> 判 A（全部满足）才允许部署；判 B 拒绝启动，violations 即缺项清单。项目经理指令项留软层由监督角色终裁。**

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

## 专家槽位（expert-loop 级联开槽）

- **框架**：expert-loop 专家循环框架（L0执行→L1问诊→L2改进→L3内化；字段契约/入库闸门/内化铁律以 slots-protocol 为准，此处不重复）
- **槽位类型**：异常触发槽
- **挂载点**：默认免 L1；部署失败/回滚/验收打回时触发 SLOT-1，SLOT-2 同触发条件
- **落盘**：`<项目根>/.expert-loop/operation-deployment-expert_advice.jsonl` + `operation-deployment-internalizations.jsonl`（本 Agent 另有产物目录约定的从其约定）
- **优先领域**（route 路由不佳时手动指定方向）：A06 DevOps与部署
- **先查自己**：SLOT-1 路由前先按 problem_family 检索自身 internalizations.jsonl，命中直接自用（领域技能融入式 / 专项技能升格式），同类问题不重复问专家
- **铁律**：裁决禁止静默忽略；accepted 必须落实改动并回链 expert_id；不归因不收尾
- **回链落盘判定禁止手写**：必须通过门禁机制机械核验（slot_attribution：project + expert_id），照抄输出（落实质量留软层）。

## 经验机制（通用）
- **第零步：加载本角色经验条目**（通用经验库机制，任务执行时按需全量调用）——逐条自检复用，每条经验即本次任务的强制约束。
- 复盘产生的经验由宿主经验机制统一收录、维护与注入；本技能不绑定任何私有注册表。
- **通用经验条目**（检查维度，融入当前任务点到即止）：
  - Shell 脚本内嵌 Python heredoc 使用 tab 缩进会触发 TabError——提交前执行 Python 语法检查。
  - Shell 脚本用 `$(cat ...)` 读取含 backtick 的文件会触发命令替换导致截断——改用 `while read` 逐行读取。
  - 钩子脚本 `>/dev/null 2>&1` 会吞掉全部错误——必须保留日志输出便于追踪（见上节）。
  - CLI/二进制入口缺失或损坏时，必须先审计安装来源、包管理器、PATH 与多版本，再决定修复方式，禁止只补符号链接。
  - 引擎重启后必须实证旧进程已死亡（kill 后验证端口释放），否则旧进程仍持端口导致新进程启动失败。


## 引擎接线（Xj-engine）

本技能为通用公开版，已剥离私有宿主依赖。需要机械门禁 / 状态裁决 / 校验时，接同仓库 `Xj-engine`：
- 安装：`pip install -e <Xj-engine 路径>`（或 `pip install -r <Xj-engine>/requirements.txt`）
- 健康检查：`xj-engine health`
- 按 ET 契约调用：`xj-engine run --payload '<ET Payload>'`，或 `from engine.kernel import et`
- 引擎离线 → 流程冻结并提示启动，禁止静默降级为软执行
引擎为可插拔：如接入其它引擎，通过环境变量切换；本技能不硬编码引擎、不携带私有依赖。
