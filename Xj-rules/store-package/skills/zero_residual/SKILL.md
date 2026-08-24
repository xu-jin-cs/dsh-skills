---
name: zero_residual
description: "零残留参数化模板闸（2026-08-16 开关化，一模三绑）：机械核验 {pattern} 在 {path}（支持 glob）内命中数==0。"
---

# zero_residual — gate-switch 实证闸

## 用途与触发

零残留参数化模板闸（2026-08-16 开关化，一模三绑）：机械核验 {pattern} 在 {path}（支持 glob）内命中数==0。三处本源禁令共用：① 01_workflows.md 规则12 改名零残留——pattern=旧函数/类/文件名，path=项目源码目录；② 01_workflows.md 规则26 回滚零残留——pattern=修改前记录的特征字符串，path=所有相关文件；③ 04_dev_standard.md 钩子脚本禁止静默执行——pattern=">/dev/null"，path=目标脚本。注意 pattern 按正则解释，含特殊字符须转义。A=0 残留放行；B=命中数即残留实证，violations 列出继续清理。

## 扳动命令

```bash
python3 ~/.agents/skills/zero_residual/scripts/gate_switch.py --spec ~/.agents/skills/zero_residual/scripts/specs/zero_residual.json --set path=<path> --set pattern=<pattern>
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
