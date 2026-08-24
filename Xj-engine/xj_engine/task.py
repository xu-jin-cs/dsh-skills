"""task.py — 任务生命周期 + 桥接执行层。

设计：
- 内核只负责在成功钩子链后调用 run_task_action()
- 任务状态流转、完成证据校验、审计、桥接通知都在本模块执行
- 具体前端桥接 adapter 不写死在内核，通过 BridgeExecutor 注册
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import audit as _audit
from .state_store import SqliteStateStore

# action → 目标状态
ACTION_TO_STATE = {
    "complete": "completed",
    "cancel": "cancelled",
    "archive": "archived",
}

# action → 审计事件类型
ACTION_TO_AUDIT = {
    "complete": _audit.AuditEventType.TASK_COMPLETE,
    "cancel": _audit.AuditEventType.TASK_CANCEL,
    "archive": _audit.AuditEventType.TASK_ARCHIVE,
}


def validate_task_evidence(action: str, evidence: Any) -> tuple[bool, str]:
    """完成证据校验（任务语义）。

    目前规则：
    - complete 必须携带非空 evidence dict
    - cancel / archive 不强制证据
    后续可扩展为 artifact_validate 同一套机械校验。
    """
    if action == "complete":
        if not isinstance(evidence, dict) or not evidence:
            return False, "task.complete 必须携带非空 evidence（完成证据）"
    return True, ""


@dataclass
class BridgeEvent:
    """桥接事件：内核/任务层发出，由 BridgeExecutor 分发给前端 adapter。"""

    event_type: str
    task_id: str
    action: str
    state: str
    trace_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    targets: list[str] = field(default_factory=list)
    require_ack: bool = False


class BridgeExecutor:
    """通用桥接执行器。

    用法：
        executor = BridgeExecutor()
        executor.register_adapter("dsh", my_dsh_adapter)
        executor.dispatch(event)
    """

    def __init__(self) -> None:
        self._adapters: dict[str, Callable[[BridgeEvent], dict]] = {}

    def register_adapter(self, name: str, fn: Callable[[BridgeEvent], dict]) -> None:
        self._adapters[name] = fn

    def dispatch(self, event: BridgeEvent) -> list[dict]:
        results = []
        for target in event.targets:
            fn = self._adapters.get(target)
            if fn is None:
                results.append({
                    "target": target,
                    "status": "skipped",
                    "reason": "adapter 未注册，跳过（可按契约实现 bridge adapter）",
                })
                continue
            try:
                r = fn(event)
                results.append({"target": target, "status": "ok", "result": r})
            except Exception as exc:
                results.append({"target": target, "status": "failed", "error": str(exc)})
        return results


# 全局默认桥接执行器（内核使用；外部可替换）
_default_executor = BridgeExecutor()


def get_bridge_executor() -> BridgeExecutor:
    return _default_executor


def run_task_action(
    task: dict[str, Any],
    trace_id: str,
    *,
    artifact: Any = None,
    signed_artifact: Any = None,
) -> dict[str, Any]:
    """执行任务生命周期动作。

    返回：
    {
      "task_id": ...,
      "action": ...,
      "to_state": ...,
      "audit": {...},
      "bridge": [...],
    }
    """
    action = task["action"]
    task_id = task["task_id"]
    to_state = task.get("to_state") or ACTION_TO_STATE[action]
    evidence = task.get("evidence")
    targets = task.get("targets") or []
    require_ack = bool(task.get("require_bridge_ack", False))

    # 1. 完成证据校验
    ok, reason = validate_task_evidence(action, evidence)
    if not ok:
        return {"code": "reject", "reason": reason,
                "task_id": task_id, "action": action, "to_state": to_state}

    # 2. 状态流转（StateStore）
    store = SqliteStateStore()
    from_state = task.get("from_state")
    try:
        store.ensure_instance(task_id, from_state or "pending")
        cur_state, cur_ver = store.get_state(task_id)
        if from_state is not None and cur_state != from_state:
            return {"code": "block", "reason": f"源状态不匹配: current={cur_state}, expected={from_state}",
                    "task_id": task_id, "action": action, "to_state": to_state}
        transition = store.transition(
            instance_id=task_id,
            from_state=from_state,
            to_state=to_state,
            operator="xj-engine",
            expected_version=cur_ver,
            meta={"action": action, "evidence": evidence or {}, "trace_id": trace_id},
            trace_id=trace_id,
        )
    except Exception as exc:
        return {"code": "error", "reason": f"状态流转失败: {exc}",
                "task_id": task_id, "action": action, "to_state": to_state}

    # 3. 审计
    audit_event = ACTION_TO_AUDIT[action]
    audit_out = _audit.emit_audit(
        audit_event,
        trace_id=trace_id,
        instance_id=task_id,
        decision="pass",
        rule_hits=[f"task.{action}"],
        reason=f"task {action} -> {to_state}",
        extra={"evidence": evidence or {}, "targets": targets, "to_state": to_state},
    )

    # 4. 桥接通知
    bridge_event = BridgeEvent(
        event_type=audit_event.value,
        task_id=task_id,
        action=action,
        state=to_state,
        trace_id=trace_id,
        payload={"artifact": artifact, "signed_artifact": signed_artifact,
                 "evidence": evidence or {}, "transition": transition},
        targets=targets,
        require_ack=require_ack,
    )
    bridge_results = get_bridge_executor().dispatch(bridge_event)

    return {
        "code": "success",
        "task_id": task_id,
        "action": action,
        "to_state": to_state,
        "transition": transition,
        "audit": audit_out,
        "bridge": bridge_results,
    }
