# Examples — 可独立运行的演示（中文说明）

> 三个自带预期输出的演示。CLI 类无需 Agent 宿主；需要宿主的已标注。
>
> [English](README.md) · [← 返回 dsh-skills](../README.md)

## 1. gate-switch：30 秒看清「机械门禁」（纯 CLI）

在仓库根目录执行：

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

退出码 `0` = A 放行。然后做那个让它「咔哒」一声的实验：从 `README.md` 删掉两行 badge 重跑——判定变为 `B`，`violations` 逐条列出缺了哪几项。**判定权在脚本，不在模型**。新场景 = 写一个新 spec JSON，引擎零改动（7 个检查原语见 [`gate-switch/SKILL.md`](../gate-switch/SKILL.md)）。

## 2. archmap：任意项目的架构测绘（Agent 宿主内调用）

archmap 在 Agent 宿主（DSH / Claude Code / Kimi Code）内运行。安装后在会话中：

```
/archmap <你的项目路径>          # 零参自动分流：无基线→full 全量初始化；有基线→lite 极简增量
/archmap <你的项目路径> +diff    # 行级差异影响面 + 导入闭包 + 测试选择（零 LLM）
/archmap <你的项目路径> +sync    # 增量同步基线并刷新报告
```

预期产物：目标项目下生成 `archmap/` 目录——`full_index.json`（模块/API 资产）、`file_routes.json`（路由→文件映射）、`01~09` 系列报告与变更台账。`diff` 模式纯确定性计算，不消耗 LLM tokens。

## 3. parallel-dispatch：并行闸单刀双掷（纯 CLI 可见判定）

```bash
python3 parallel-dispatch/scripts/dispatch_switch.py --files 6 --units 3 --desc "demo"
```

预期输出：JSON 门禁声明。裸 shell 下它会**拒绝扳动**并列出原因（本 turn 任务清单未登记、无基线）——**这不是报错，是门禁在工作**：并行扇出必须先登记任务清单、过基线校验，全程留痕 `~/.agents/logs/dispatch_switch.jsonl`。在 Agent 宿主内，≥2 个无依赖子任务会自动触发同一判定。

---

方法论长文：[《给 LLM 的口头承诺装上机械门禁》](../docs/mechanical-gates-for-llm.md)（[English](../docs/mechanical-gates-for-llm.en.md)）。

许可：[自定义源码可用许可](../LICENSE)（中文对照：[LICENSE-zh.md](../LICENSE-zh.md)）——仅供个人非商用本地使用；未经书面授权禁止公开 Fork、商用分发、SaaS 服务。作者 [xu-jin-cs](https://github.com/xu-jin-cs)。
