---
name: deploy_admission
description: "部署启动准入（DEPLOY-001 重生版：交付物缺失阻塞部署）。"
---

# deploy_admission — gate-switch 实证闸

## 用途与触发

部署启动准入（DEPLOY-001 重生版：交付物缺失阻塞部署）。A=三项全满足放行 Step1；B=拒绝启动，violations 即缺项清单。PM 指令项无法机械判，留软层由 sv-supervisor 终裁

## 扳动命令

```bash
python3 ~/.agents/skills/deploy_admission/scripts/gate_switch.py --spec ~/.agents/skills/deploy_admission/scripts/specs/deploy_admission.json --set backend=<backend> --set bugs=<bugs> --set frontend=<frontend> --set report=<report>
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
