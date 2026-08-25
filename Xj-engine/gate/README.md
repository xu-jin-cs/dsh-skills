# Xj-engine/gate — 任务完成附身闸

任务完成需要【附身闸】：新建任务时，把"完成步骤"追加到任务末尾。

**完成步骤**（不是 hook）：
```
todo_write 将该任务 status 置为 "completed" → DSH 面板打勾
```

没有此附身闸，新任务不会被追加完成步骤 → 无法完成。

## 文件

| 文件 | 职责 |
|---|---|
| `task_complete_attach_gate.py` | 附身闸（todo_write 挂点）：清单含新任务才追加完成步骤、重发豁免 |
| `attached_complete.py` | 完成步骤定义与留痕 |

## 用法

```bash
# 新建任务后触发附身闸（--tasks 为本次 todo_write 任务清单）
python3 task_complete_attach_gate.py --tasks '["任务A：sleep(5)","任务B：sleep(10)"]'
# 输出：A: 给 N 个新任务末尾追加完成步骤 / EXEMPT: 重发豁免

# 查看完成步骤定义
python3 attached_complete.py --task "任务描述"
```

## 配置（环境变量，均可选）

| 变量 | 作用 | 默认 |
|---|---|---|
| `TODO_SEAL_DIR` | 已见任务台账目录 | `~/.local/share/dsh-skills/logs/todo_seal` |
| `ATTACHED_LOG` | 完成步骤留痕文件 | `~/.local/share/dsh-skills/logs/attached_plan.jsonl` |
| `ATTACH_COMPLETE_SCRIPT` | 完成步骤脚本路径 | 同目录 `attached_complete.py` |
| `DSH_SESSION_ID` | 会话 id（用于台账隔离）| `default-session` |

## 依赖

纯 Python 标准库，无第三方依赖。
