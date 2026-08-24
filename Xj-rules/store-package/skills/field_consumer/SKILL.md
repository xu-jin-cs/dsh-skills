---
name: field_consumer
description: "字段修改前验证消费闸（01_workflows.md 规则24，2026-08-16 开关化）：修改任何配置/规则/YAML 字段前，必须实证 {field_name} 在 {engine_path}（引擎代码路径，支持 glob）内被真实读取（grep 命中 ≥1）。"
---

# field_consumer — gate-switch 实证闸

## 用途与触发

字段修改前验证消费闸（01_workflows.md 规则24，2026-08-16 开关化）：修改任何配置/规则/YAML 字段前，必须实证 {field_name} 在 {engine_path}（引擎代码路径，支持 glob）内被真实读取（grep 命中 ≥1）。治「凭字段名猜含义改装饰性配置，事后发现引擎根本不读」（ppt flow.yml parallel/execution_mode 事故）。A=消费方存在，允许改并须阅读消费代码上下文；B=0 命中=装饰性配置，修改不会改变行为，跳过或仅做文档同步。注意 field_name 按正则解释，含特殊字符须转义。

## 扳动命令

```bash
python3 ~/.agents/skills/field_consumer/scripts/gate_switch.py --spec ~/.agents/skills/field_consumer/scripts/specs/field_consumer.json --set engine_path=<engine_path> --set field_name=<field_name>
```

判定禁止手写：必须实跑上述命令并照抄输出结论，禁止凭印象声称通过/不通过。

## 退出码语义

| 退出码 | 含义 |
|--:|---|
| 0 | A：全部机械核验通过，放行 |
| 2 | B：有违例阻断，violations 即违例清单/修复指令 |
| 3 | CLARIFY：输入信号不足，先澄清再扳 |
| 4 | VIOLATION：spec 非法或前置条件缺失（按输出整改后重扳） |

留痕：`~/.agents/logs/gate_switch.jsonl`。
