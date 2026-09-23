# gate-switch — 通用概率执行门禁骨架

> 功能与用途 · 安装 · 协议

## 功能

把「声称 X 已满足 / 已写入 / 已生成 / 已验收」写成**检查项 spec JSON**，引擎逐项机械核验：

- **全过 → 掷点 A 放行**；**任一失败 → 掷点 B 阻断**并逐条列出违例（B 档理由自动生成）。
- 治 LLM 三类顽疾：**该做的没做、缺斤短两、伪造声称**——判定权从模型移交脚本。

## 用途

- 发布前门禁（如本仓 `publish_sync_check`：符号链接/仓库干净/无未推送 一门三查）；
- 验收闸、测试证据闸、部署准入闸、模式分流闸——新场景 = 写新 spec JSON，**引擎零改动**；
- 7 个冻结检查原语：`file_exists` / `file_min_size` / `json_field` / `glob_count` / `grep_count` / `mtime_after` / `script_exit`（路径字段支持 `~`，cmd 字段支持 `$HOME` 展开，规格可跨机移植）。

## 快速开始

```bash
# 在仓库根目录跑演示闸（核验本仓 README 的第一屏要素）
python3 gate-switch/scripts/gate_switch.py --spec examples/gate-switch/demo_spec.json --set target=README.md
```

目录构成：`scripts/` 引擎与 21 个实例闸检查器 · `specs/` 门禁规格（含 archive/fixtures）· `data/` 扳机信号注册表与词表 · `templates/` L3 框架闸模板。

> 本地运行态（`runtime/`、`council/`、会话校准例句）不随仓分发——那是每台机器自己产生的状态。

## 协议

[CC BY-NC-SA 4.0](../LICENSE)——禁止商用；二次开发与转载须署名作者 [xu-jin-cs](https://github.com/xu-jin-cs/dsh-skills) 并保持同协议。
