# 扳手 Skill Cordis 插件 一键安装教程

> DSH Cordis 私有 Skill / 规则插件（内置种子二道混淆加密分发 · 开源小白友好版）
> 插件定位：**非独立 Agent、非完整工作流**，仅向 DeepSeek Harness 引擎提供可被调用的校验规则与原子 Skill 能力。

## 前置准备

本地已安装 DeepSeek Harness CLI，终端可正常执行 `dsh` 命令；Node.js ≥ 20。

## 一键安装（无需密钥、无需额外配置）

**macOS / Linux**——复制下面三行命令，粘贴到终端运行即可：

```bash
curl -O https://你的公开CDN地址/wrench-skill-1.0.0.tgz
curl -O https://你的公开CDN地址/install.sh
bash install.sh
```

**Windows PowerShell**：

```powershell
Invoke-WebRequest -Uri "https://你的公开CDN地址/wrench-skill-1.0.0.tgz" -OutFile "wrench-skill-1.0.0.tgz"
dsh plugin --profile web add .\wrench-skill-1.0.0.tgz
```

> Windows 用户推荐使用 Git Bash / WSL 执行 `bash install.sh` 完成全自动安装（含 patch 注册）。

## 安装完成校验

```bash
dsh plugin --profile web list
```

列表中出现 `@xu-jin-cs/dsh-cordis-wrench-skill` 即安装成功。重启 DSH 或等待热重载后，在会话中输入 `/wrench-demo` 或「扳手自检」，看到自检回执即证明解密注册链路正常。

## 插件卸载

```bash
bash uninstall.sh          # 默认从 web profile 卸载
bash uninstall.sh default  # 指定 profile
```

卸载后 DSH 重载时自动注销全部技能注册，并清空内存中的派生密钥与明文缓存，本地无任何明文残留。

## 常见问题（中文友好排查）

| 现象 | 原因与处理 |
|---|---|
| 首次加载较慢 | 插件需下载冻结版 Embedding 模型（约百 MB），仅首次，之后走本地缓存 |
| 提示「密文校验未通过」 | 插件包传输损坏或被篡改 → 重新下载完整插件包 |
| 提示「版本不匹配」 | 插件与资产包非同一批次 → 联系开发者获取匹配版本 |
| 提示「Embedding 输出维度异常」 | Embedding 模型版本漂移 → 核对依赖版本，或联系开发者重新加密资产 |

## ⚠️ 安全边界声明（必读）

本方案仅用于基础防裸奔，阻挡新手直接提取明文规则。由于插件开源分发，具备逆向能力的人员可解析源码获取内置种子并完成解密，**不具备高强度防破解能力**；若为商业私有化交付、高保密场景，请联系开发者使用独立 BASE_KEY 离线交付方案。

插件不支持设备绑定，一份插件包可在多台设备安装使用。

---

## 开发者区（重新打包私有规则）

```bash
# 1. 复制 manifest.example.json 为 my-manifest.json，填入你的技能清单
# 2. 安装依赖（首次）
npm install
# 3. 加密打包（产出 assets/rules.enc.json，自带 roundtrip + 明文泄露双自检）
node scripts/encrypt.mjs --manifest my-manifest.json
# 4. 打出分发包
npm pack
```

> 版本冻结铁律：`lib/constants.mjs` 中任何字段（种子/盐源文本/模型/info）变更后，必须重新执行第 3 步全量重新加密资产，否则解密必失败。
