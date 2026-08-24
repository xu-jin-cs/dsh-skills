---
name: bug_fix_gate
description: "bug-fix-strategy 修复级别机械门禁（2026-08-15 裁定）：script_exit 包装 bug_fix_switch.py，机械核验禁止跳级/重构重复次数闸/>3文件确认闸；占位符 {bug_id} {level} 由 --set 注入，expect 0（判 A 才许动手，判"
---

# bug_fix_gate — gate-switch 实证闸

## 用途与触发

bug-fix-strategy 修复级别机械门禁（2026-08-15 裁定）：script_exit 包装 bug_fix_switch.py，机械核验禁止跳级/重构重复次数闸/>3文件确认闸；占位符 {bug_id} {level} 由 --set 注入，expect 0（判 A 才许动手，判 B 照抄理由）

## 扳动命令

```bash
python3 ~/.agents/skills/bug_fix_gate/scripts/gate_switch.py --spec ~/.agents/skills/bug_fix_gate/scripts/specs/bug_fix_gate.json --set bug_id=<bug_id> --set level=<level>
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

## 依赖

本闸的检查脚本引用以下同商店技能（需一并安装到 `~/.agents/skills/`）：`bug-fix-strategy`。
