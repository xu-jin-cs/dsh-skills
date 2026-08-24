---
name: be_api_schema
description: "backend-engineer 交付物 .api-schema.json 机械自检（REFORM-GATE 改造 P5a）：契约权威=消费方 api-test-engineer 唯一权威输入契约（schema 2.0）。"
---

# be_api_schema — gate-switch 实证闸

## 用途与触发

backend-engineer 交付物 .api-schema.json 机械自检（REFORM-GATE 改造 P5a）：契约权威=消费方 api-test-engineer 唯一权威输入契约（schema 2.0）。文件存在 + 接口数组非空 + 首接口必填字段（path/method/module三级/fields/scenes_applicable/response_schema_ref）+ 顶层 schema_version/response_schemas。async_pattern 仅异步接口声明（polling/callback），条件必填不在本闸；逐接口全量字段深校验由下游 api_scene_matrix.py 收口，本闸做交付点存在性拦截

## 扳动命令

```bash
python3 ~/.agents/skills/be_api_schema/scripts/gate_switch.py --spec ~/.agents/skills/be_api_schema/scripts/specs/be_api_schema.json --set schema_path=<schema_path>
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
