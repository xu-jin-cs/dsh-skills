# 扳手 Skill Cordis 插件 一键安装教程

> DSH Cordis 私有 Skill / 规则插件（内置种子二道混淆加密分发 · 开源小白友好版）
> 插件定位：**非独立 Agent、非完整工作流**，仅向 DeepSeek Harness 引擎提供可被调用的校验规则与原子 Skill 能力。

## 前置准备

本地已安装 DeepSeek Harness CLI，终端可正常执行 `dsh` 命令；Node.js ≥ 20。

## 一键安装（无需密钥、无需额外配置）

**macOS / Linux**——复制下面三行命令，粘贴到终端运行即可：

```bash
curl -O https://你的公开CDN地址/xujin-1.0.0.tgz
curl -O https://你的公开CDN地址/install.sh
bash install.sh
```

**Windows PowerShell**：

```powershell
Invoke-WebRequest -Uri "https://你的公开CDN地址/xujin-1.0.0.tgz" -OutFile "xujin-1.0.0.tgz"
dsh plugin --profile web add .\xujin-1.0.0.tgz
```

> Windows 用户推荐使用 Git Bash / WSL 执行 `bash install.sh` 完成全自动安装（含 patch 注册）。

## 安装完成校验

```bash
dsh plugin --profile web list
```

列表中出现 `@xu-jin-cs/dsh-cordis-xujin` 即安装成功。重启 DSH 或等待热重载后，在会话中输入 `/xujin-demo` 或「扳手自检」，看到自检回执即证明解密注册链路正常。

## 插件卸载

```bash
bash uninstall.sh          # 默认从 web profile 卸载
bash uninstall.sh default  # 指定 profile
```

卸载后 DSH 重载时自动注销全部技能注册，并清空内存中的派生密钥与明文缓存，本地无任何明文残留。

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
| 提示「密文校验未通过」 | 插件包传输损坏或被篡改 → 重新下载完整插件包 |
| 提示「版本不匹配」 | 插件与资产包非同一批次 → 联系开发者获取匹配版本 |
| 提示「未注入派生 Salt」 | 插件包被二次打包破坏了内置常量 → 重新从官方渠道下载 |

## ⚠️ 安全边界声明（必读）

本方案仅用于基础防裸奔，阻挡新手直接提取明文规则。由于插件开源分发，具备逆向能力的人员可解析源码获取内置种子并完成解密，**不具备高强度防破解能力**；若为商业私有化交付、高保密场景，请联系开发者使用独立 BASE_KEY 离线交付方案。

插件不支持设备绑定，一份插件包可在多台设备安装使用。

---

## 开发者区（重新打包私有规则）

```bash
# 0. 仅首次/常量变更后：用本地冻结 BGE-M3（1024 维，HF 缓存离线加载）派生 Salt 并写回 constants
python3 scripts/derive_salt.py
#    日常体检（模型/盐源文本漂移检测）：python3 scripts/derive_salt.py --check
# 1. 生成真实资产清单（收集 ~/.agents/rules + 7 原子技能 + 闸 specs + 引擎规则，自动做调用路径重写）
node scripts/build_manifest.mjs    # 产出 manifest.real.json（明文中间产物，已 gitignore）
# 2. 加密打包（产出 assets/rules.enc.json，自带 roundtrip + 明文泄露双自检，零依赖零网络）
node scripts/encrypt.mjs --manifest manifest.real.json
# 3. 打出分发包（零 node_modules）
npm pack
```

> 架构说明：Embedding 派生只在开发期执行一次，派生结果（16 字节 Salt）以常量内置；
> 插件运行时零模型、零依赖、零网络，仅 node:crypto 完成 HKDF 派生 + AES-256-GCM 内存解密。
>
> 版本冻结铁律：`lib/constants.mjs` 中任何字段（种子/盐源文本/Salt/info）变更后，必须重新执行第 2 步全量重新加密资产，否则解密必失败。

## 🧩 核心痛点（面向 DSH Agent 开发者，真实工程踩坑）

1. **LLM 概率性执行**：相同输入，Agent 规划、工具调用、方案生成行为不稳定；时而正常时而跑偏，全自动流水线不可靠。仅靠 System Prompt 约束，大模型经常无视提示词，文字约束容易失效。
2. **模型自由决策泛滥**：模型自主挑选实现路径，经常选出步骤冗长、高风险、高 Token 消耗方案；热修复小任务触发大范围无效代码变更。
3. **缺少执行层硬护栏**：原生 DSH 仅靠日志记录，缺少前置拦截校验；产物表面可运行，暗藏渲染缺陷、逻辑漏判，Bad Case 事后才暴露。
4. **提示词上下文臃肿**：大量架构约束、元方法规则塞进系统提示词，占用上下文窗口，会话越长规则越容易被遗忘稀释。
5. **方案对比无客观标尺**：多候选方案只能交给模型主观打分，没有统一等价步骤代价评估，无法自动选出步骤最少风险最低路径。
6. **修改 Agent 规则需要改动业务代码**：现在 RuleGate 通过 Cordis 事件总线注入，**只改外置 YAML 契约，不用修改 Harness 内核、不用 fork 源码，插件可随时挂载 / 卸载，卸载自动回滚全部效果。**
