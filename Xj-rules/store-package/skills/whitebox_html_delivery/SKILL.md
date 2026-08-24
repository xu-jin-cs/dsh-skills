---
name: whitebox_html_delivery
description: "whitebox-coverage 终判 HTML 报告桌面交付实证闸（2026-08-17 C域开关化，块4 retro-pm-129 同类）：机械核验 HTML 报告已复制到 ~/Desktop/{project}_白盒测试报告_{batch}.html——仅文字提及路径不构成有效交付，桌面副本"
---

# whitebox_html_delivery — gate-switch 实证闸

## 用途与触发

whitebox-coverage 终判 HTML 报告桌面交付实证闸（2026-08-17 C域开关化，块4 retro-pm-129 同类）：机械核验 HTML 报告已复制到 ~/Desktop/{project}_白盒测试报告_{batch}.html——仅文字提及路径不构成有效交付，桌面副本缺失即终判步骤未完成（B 档）。file_exists+file_min_size+mtime_after 三原语，与 ppt_delivery 同构、零脚本。扳动时机：渲染成功并 cp Desktop 后、输出终判汇报回执前。用法：--set project=<项目名> --set batch=<批次> --set project_path=<项目路径（evidence 归档原件所在工程根）>

## 扳动命令

```bash
python3 ~/.agents/skills/whitebox_html_delivery/scripts/gate_switch.py --spec ~/.agents/skills/whitebox_html_delivery/scripts/specs/whitebox_html_delivery.json --set batch=<batch> --set project=<project> --set project_path=<project_path>
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
