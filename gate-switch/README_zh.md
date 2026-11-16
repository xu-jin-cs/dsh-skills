# gate-switch — 通用概率执行门禁骨架（中文说明）

> 把「声称已满足」变成可核验的事实。spec 驱动的机械核验引擎：**掷点 A 放行 / B 阻断，判定权在脚本，不在模型。**
>
> [English](README.md) · [← 返回 dsh-skills](../README.md)

## 是什么 / 治什么痛点

LLM 的三类顽疾：**该做的没做、缺斤短两、伪造声称**。提示词写得再狠也治不了——判定权必须移出模型。

gate-switch 把「该做什么」写成 **spec JSON**，引擎逐项机械核验：

- 全过 → **掷点 A 放行**；任一失败 → **掷点 B 阻断**，违例逐条列出（B 档理由自动生成）。
- 四态退出码 `0=A / 2=B / 3=CLARIFY / 4=VIOLATION`，全程 JSONL 留痕。
- 新场景 = 写新 spec JSON，**引擎零改动**。

## 30 秒安装

```bash
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install gate-switch
```

已 clone 本仓：`./install.sh gate-switch`（符号链接装入 `~/.dsh/skills`，DSH watcher 热加载；Claude Code / Kimi Code / Codex 技能根同样可用）。

## 5 分钟上手

在仓库根目录跑演示闸（核验本仓 README 第一屏）：

```bash
python3 gate-switch/scripts/gate_switch.py --spec examples/gate-switch/demo_spec.json --set target=README.md
```

预期输出（节录）：

```json
{
  "verdict": "A",
  "gate": "demo_release_hygiene",
  "passed": ["README 至少 3 枚 shields.io badges: 命中=4 ...", "..."]
}
```

退出码 `0` = A。然后做那个让它「咔哒」一声的实验：从 `README.md` 删掉两行 badge 再跑——判定翻成 `B`，`violations` 逐条列出缺了哪几项。**判定权在脚本，不在模型**——这就是 gate-switch 的全部要义。

## 输入 / 输出

- **输入**：spec JSON——由 **7 个冻结检查原语** 组成：`file_exists` / `file_min_size` / `json_field` / `glob_count` / `grep_count` / `mtime_after` / `script_exit`。路径字段支持 `~`、cmd 字段支持 `$HOME` 展开，规格跨机可移植。运行时取值经 `--set key=value` 注入。
- **输出**：JSON 判定（`passed[]` / `violations[]`，B 档理由自动生成）+ JSONL 留痕。
- **目录构成**：`scripts/`（引擎 + 21 个实例闸检查器）· `specs/`（门禁规格，含 archive/fixtures）· `data/`（扳机信号注册表与词表）· `templates/`（L3 框架闸模板）。会话运行态（`runtime/`、`council/`）每台机器自产，**不随仓分发**。

## 能力与边界

- 典型闸：发布前门禁（`publish_sync_check`：符号链接/仓库干净/无未推送，一门三查）、验收闸、测试证据闸、部署准入闸、模式分流闸。
- **边界**：只做机械可判的 0/1 事实；需要品味与开放语义的判断不在射程内——那部分请写成人读检查清单，别写成 spec。

## 组合用法

- **[parallel-dispatch](../parallel-dispatch/README_zh.md)**：掷点前置条件（任务清单、基线文件）都可用 gate-switch spec 看守。
- **[archmap](../archmap/README_zh.md)**：消费 `diff_impact.json` 前用 `mtime_after` 核验新鲜度。
- **[Xj-engine](../Xj-engine/README_zh.md)**：`et_test_gates` 把门禁语义装进引擎 ET 契约。

## FAQ

**Q：检查逻辑是定制的，必须改引擎吗？**
不用——`script_exit` 原语可执行任意命令，退出码 0 = 过，其余 = 违例，stdout/stderr 即证据。

**Q：会话状态放哪？**
`gate-switch/runtime/`（判定状态）与 `council/`（会诊报告）每机自产，不入仓。

**Q：我写的 spec 能分享吗？**
spec 就是普通 JSON——放进你本地安装的 `specs/` 即可，引擎在哪都能跑。

---

许可：[自定义源码可用许可](../LICENSE)（中文对照：[LICENSE-zh.md](../LICENSE-zh.md)）——仅供个人非商用本地使用；未经书面授权禁止公开 Fork、商用分发、SaaS 服务。作者 [xu-jin-cs](https://github.com/xu-jin-cs)。
