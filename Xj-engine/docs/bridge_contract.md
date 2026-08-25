# Xj-engine 桥接契约

## 目标

引擎内核负责“任务完成/取消/归档”的权威状态流转、证据校验、审计、签名和桥接事件分发；
具体前端同步（DSH todo_write、Kimi TodoList、Claude 面板等）由外部 adapter 实现，不写入内核。

## 架构

```text
内核
  ├── task.complete / task.cancel / task.archive
  ├── StateStore 状态流转
  ├── 完成证据校验
  ├── audit
  ├── content_issue 签名
  └── BridgeExecutor 分发 BridgeEvent
        ↓
外部 adapter
  ├── adapter_dsh.py
  ├── adapter_kimi.py
  └── adapter_claude.py
```

## BridgeEvent

```json
{
  "event_type": "task_complete_event | task_cancel_event | task_archive_event",
  "task_id": "任务ID",
  "action": "complete | cancel | archive",
  "state": "completed | cancelled | archived",
  "trace_id": "引擎 trace_id",
  "payload": {
    "artifact": "...",
    "signed_artifact": "...",
    "evidence": {},
    "transition": {}
  },
  "targets": ["dsh", "kimi", "claude"],
  "require_ack": false
}
```

## Adapter 接口

```python
def adapter_dsh(event: BridgeEvent) -> dict:
    # 调用 DSH todo_write 将 task_id 对应项标记 completed
    return {"ok": True}
```

注册方式：

```python
from engine.task import get_bridge_executor

executor = get_bridge_executor()
executor.register_adapter("dsh", adapter_dsh)
```

## Payload 中的 task 块

```json
{
  "task": {
    "action": "complete",
    "task_id": "task-001",
    "from_state": "in_progress",
    "to_state": "completed",
    "evidence": {
      "output_file": "/path/to/result.json",
      "test_pass": true
    },
    "targets": ["dsh", "kimi"],
    "require_bridge_ack": false
  }
}
```

## 状态映射

| action | 默认 to_state |
|---|---|
| complete | completed |
| cancel | cancelled |
| archive | archived |

## 完成证据校验

- `complete` 必须携带非空 `evidence` dict
- `cancel` / `archive` 不强制 evidence
- 后续可扩展为 `artifact_validate` 同一套机械校验

## 桥接失败处理

- adapter 未注册：状态为 `skipped`，不阻塞引擎
- adapter 抛出异常：状态为 `failed`，记录错误，不阻塞引擎
- `require_bridge_ack=true` 时，adapter 应返回回执；未实现回执时按成功处理
