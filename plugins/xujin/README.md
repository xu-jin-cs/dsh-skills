# xujin —— DSH Cordis 私有 Skill / 规则 / 闸 / 引擎插件 一键安装教程

> 仓库：https://github.com/xu-jin-cs/dsh-skills （插件目录 `plugins/xujin`）
> DSH Cordis 私有 Skill / 规则 / 闸 / 引擎插件（Source-Available 明文分发 · 开源小白友好版）
> 插件定位：**非独立 Agent、非完整工作流**，仅向 DeepSeek Harness 引擎提供可被调用的校验规则、闸开关、原子 Skill 与引擎机制内核（签发/状态同步）能力。

## 前置准备

本地已安装 DeepSeek Harness CLI，终端可正常执行 `dsh` 命令；Node.js ≥ 20。

## 一键安装（无需密钥、无需额外配置）

**macOS / Linux**——复制下面三行命令，粘贴到终端运行即可：

```bash
curl -LO https://github.com/xu-jin-cs/dsh-skills/releases/latest/download/xujin-1.4.0.tgz
curl -LO https://github.com/xu-jin-cs/dsh-skills/releases/latest/download/install.sh
bash install.sh
```

> 备用直链（任何时候可用）：把上面两条 URL 换为
> `https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/plugins/xujin/dist/xujin-1.4.0.tgz`
> `https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/plugins/xujin/dist/install.sh`

**Windows PowerShell**：

```powershell
Invoke-WebRequest -Uri "https://github.com/xu-jin-cs/dsh-skills/releases/latest/download/xujin-1.4.0.tgz" -OutFile "xujin-1.4.0.tgz"
Invoke-WebRequest -Uri "https://github.com/xu-jin-cs/dsh-skills/releases/latest/download/install.sh" -OutFile "install.sh"
bash install.sh   # 推荐 Git Bash / WSL 执行
```

> 安装脚本默认装入 `web` profile；装其他 profile：`bash install.sh default`。

## 安装完成校验

```bash
dsh plugin --profile web list    # 列表中出现 xujin 即安装成功
```

重启 DSH 或等待热重载后，插件自动直读明文资产并注册全部规则/技能。校验方式：会话技能目录中出现 `rule-00-root-safety` ~ `rule-13-workflow-router` 等 19 份规则技能与 gate-switch / parallel-dispatch 等 7 个原子技能（v1.3 起资产包内含 78 份闸 spec，`xujin-gate reform_gate` 等规则内扳闸指令全部可用）；终端执行 `~/.dsh/bin/xujin-engine sign --artifact '{"test":1}'` 能输出签名即引擎可用。

**v1.2 起合并查询闸焊点**：安装会一并注册 `dsh-trigger-auto` 插件（包内 `payload/dsh-trigger-auto`）。生效后 Agent 每个 turn 首个 `read`/`grep`/`glob` 检索动作前必须先过一次声明闸定性（`dual_gates.py declare`，判 not_query 也直接放行），否则被事前阻断并给出扳闸指引——这是设计本意，不是故障。

## 插件卸载

```bash
bash uninstall.sh          # 默认从 web profile 卸载
bash uninstall.sh default  # 指定 profile
```

卸载后 DSH 重载时自动注销全部技能注册。

## 使用：在你自己的工作流节点上调用闸与引擎

安装后，`~/.dsh/bin/` 下常驻两个 CLI（插件内执行，无需 Python、无需 FastAPI 服务、无数据库）：

**扳闸（校验规则开关，四态退出码 0=A放行 / 2=B阻断 / 3=CLARIFY / 4=VIOLATION）：**

```bash
~/.dsh/bin/xujin-gate <spec名> [--set 键=值 ...]
# 示例：~/.dsh/bin/xujin-gate engine_health
```

**引擎内核（内容签发 / 验签 / 状态同步 / et 六段时序执行）：**

```bash
# 节点产出交付物后签发（防篡改防伪造）
~/.dsh/bin/xujin-engine sign --trace-id proj-x-03dev --artifact '{"type":"code","ref":"src/app.js"}'

# 下游节点验收前验签
~/.dsh/bin/xujin-engine verify --trace-id proj-x-03dev --artifact '{...}' --signature <签名>

# 节点状态同步（等价原 harness-step-sync.sh 语义，本地直写无需服务）
~/.dsh/bin/xujin-engine step-sync myproj 03dev "开发完成，待测试" backend-engineer

# 完整 et() 流水线（resource_control→交付物校验→状态拦截→闸→签发→投递装配）
~/.dsh/bin/xujin-engine et payload.json
# → {"code":"success|reject|block|timeout|error", ...}
```

**接线方式**：在你自己的工作流技能节点定义中写「本节点完成后执行 `~/.dsh/bin/xujin-engine step-sync …`」即可；插件注册的规则技能已内置这些调用写法，Agent 加载规则后自然会用。

**两个前提（重要）**：

1. hmac-sha256 签发需要密钥：与原引擎设计一致，密钥**只从环境变量 `AGENT_ENGINE_SECRET` 读取**，无内置回落。未设置时 `sign` 会中文报错提示。sha256 纯哈希模式无需密钥但只有完整性校验能力（任何人可重算，不防伪）。需要防伪签发的场景，请向开发者线下获取密钥（对应 BASE_KEY 离线交付）。
2. 引擎运行时数据落盘位置：`~/.dsh/xujin-engine/state/`（实例状态 JSON）与 `~/.dsh/xujin-engine/audit.jsonl`（审计事件流）。这是运行时数据，不含规则明文。

## 常见问题（中文友好排查）

| 现象 | 原因与处理 |
|---|---|
| 提示「资产包解析失败」 | assets/rules.json 损坏（传输截断/被篡改） → 重新下载完整插件包 |
| 提示「资产包结构异常」 | 包内资产缺 skills 数组 → 重新从官方渠道下载 |
| 闸/引擎命令报「不存在 spec」 | 插件版本过旧（v1.2 及以前资产包不含闸 spec） → 升级到 v1.4.0+ |

## 📜 Source-Available 许可声明（必读）

本插件自 v1.4.0 起改为 **Source-Available（可见源）明文分发**：包内全部规则、技能、闸 spec、引擎规则均为明文，可查看、可学习、可在个人/内部环境安装使用；**禁止未经授权的商业再分发、转售或作为商业服务对外提供**。完整条款见插件根目录 `LICENSE` 文件。商业授权请联系作者线下获取。

## 开发者区（重新打包）

```bash
# 1. 生成资产清单（收集 ~/.agents/rules + 7 原子技能 + 闸 specs + 引擎规则，自动做调用路径重写）
node scripts/build_manifest.mjs    # 产出 manifest.real.json（明文中间产物，已 gitignore）
# 2. 明文打包资产（产出 assets/rules.json，自带回读自检）
node scripts/build_assets.mjs --manifest manifest.real.json
# 3. 打出分发包（零 node_modules）
npm pack
```

> v1.4.0 起加密链路（encrypt.mjs / crypto.mjs / constants.mjs / derive_salt.py）已退役归档至 `archive/`。

## 🧩 核心痛点（面向 DSH Agent 开发者，真实工程踩坑）

1. **LLM 概率性执行**：相同输入，Agent 规划、工具调用、方案生成行为不稳定；时而正常时而跑偏，全自动流水线不可靠。仅靠 System Prompt 约束，大模型经常无视提示词，文字约束容易失效。
2. **模型自由决策泛滥**：模型自主挑选实现路径，经常选出步骤冗长、高风险、高 Token 消耗方案；热修复小任务触发大范围无效代码变更。
3. **缺少执行层硬护栏**：原生 DSH 仅靠日志记录，缺少前置拦截校验；产物表面可运行，暗藏渲染缺陷、逻辑漏判，Bad Case 事后才暴露。
4. **提示词上下文臃肿**：大量架构约束、元方法规则塞进系统提示词，占用上下文窗口，会话越长规则越容易被遗忘稀释。
5. **方案对比无客观标尺**：多候选方案只能交给模型主观打分，没有统一等价步骤代价评估，无法自动选出步骤最少风险最低路径。
6. **修改 Agent 规则需要改动业务代码**：现在 RuleGate 通过 Cordis 事件总线注入，**只改外置 YAML 契约，不用修改 Harness 内核、不用 fork 源码，插件可随时挂载 / 卸载，卸载自动回滚全部效果。**
