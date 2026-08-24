"""
引擎标准审计事件（P2-6，2026-08-17）。

定位：引擎外围平台层。内核无状态，钩子判定明细由母体/接线层调用
emit_audit 落库；query_by_trace 按 trace_id 全链检索，支撑
"任意一次流转可复现全部判定明细"。

事件类型枚举 AuditEventType：
  state_intercept_event / gate_guard_event /
  content_issue_event / artifact_validate_event

表：engine_audit_events（trace_id 索引），create_all 幂等。
生产默认接 backend.database.engine（首次使用时惰性建表）；
测试用 set_engine(tmp_engine) 或 emit_audit(..., engine=tmp_engine) 指向临时库。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════
# 事件类型枚举
# ═══════════════════════════════════════════════════════════════

class AuditEventType(str, Enum):
    STATE_INTERCEPT = "state_intercept_event"      # state_intercept 钩子判定
    GATE_GUARD = "gate_guard_event"                # gate_guard 门禁判定
    CONTENT_ISSUE = "content_issue_event"          # content_issue 签发
    ARTIFACT_VALIDATE = "artifact_validate_event"  # artifact_validate 交付物校验
    TASK_COMPLETE = "task_complete_event"          # 任务完成
    TASK_CANCEL = "task_cancel_event"              # 任务取消
    TASK_ARCHIVE = "task_archive_event"            # 任务注销归档


# ═══════════════════════════════════════════════════════════════
# 表模型
# ═══════════════════════════════════════════════════════════════

class EngineAuditEvent(Base):
    __tablename__ = "engine_audit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(64), nullable=False, index=True)
    trace_id = Column(String(64), nullable=False, index=True)
    instance_id = Column(String(64), default="")
    decision = Column(String(32), default="")       # 如 pass/block/reject/success
    rule_hits = Column(JSON, default=list)          # 命中的规则明细
    reason = Column(Text, default="")
    extra = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_utcnow)


_AUDIT_TABLES = [EngineAuditEvent.__table__]


# ═══════════════════════════════════════════════════════════════
# 引擎绑定（默认 backend.database.engine，可注入临时库）
# ═══════════════════════════════════════════════════════════════

_engine: Optional[Engine] = None
_Session: Optional[sessionmaker] = None


def _ensure_tables(engine: Engine) -> None:
    """幂等建表（仅审计表，不触碰其他 Base 模型）。"""
    Base.metadata.create_all(bind=engine, tables=_AUDIT_TABLES)


def set_engine(engine: Engine) -> None:
    """切换审计存储引擎（母体接线 / 测试临时库用）。幂等建表。"""
    global _engine, _Session
    _ensure_tables(engine)
    _engine = engine
    _Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def is_bound() -> bool:
    """审计存储是否已绑定（set_engine 已调用）。

    内核钩子审计接线据此判定：未绑定（如内核单元测试直跑）则跳过落库，
    避免测试流量污染生产库；生产由 main.py lifespan 启动时绑定。
    """
    return _Session is not None


def _open_session(engine: Optional[Engine]):
    """优先用显式 engine；其次 set_engine 注入的；最后默认 backend.database.engine。"""
    global _engine, _Session
    if engine is not None:
        _ensure_tables(engine)
        return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    if _Session is None:
        from backend.database import engine as default_engine
        set_engine(default_engine)
    return _Session()


# ═══════════════════════════════════════════════════════════════
# 公共接口
# ═══════════════════════════════════════════════════════════════

def _normalize_event_type(event_type) -> str:
    if isinstance(event_type, AuditEventType):
        return event_type.value
    if isinstance(event_type, str):
        try:
            return AuditEventType(event_type).value
        except ValueError:
            pass
    allowed = [e.value for e in AuditEventType]
    raise ValueError(f"非法 event_type: {event_type!r}，允许值: {allowed}")


def _jsonable(value, field: str):
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 不可 JSON 序列化: {exc}") from exc
    return value


def _row_to_dict(r: EngineAuditEvent) -> dict:
    return {
        "id": r.id,
        "event_type": r.event_type,
        "trace_id": r.trace_id,
        "instance_id": r.instance_id,
        "decision": r.decision,
        "rule_hits": r.rule_hits or [],
        "reason": r.reason,
        "extra": r.extra or {},
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def emit_audit(
    event_type,
    trace_id: str,
    instance_id: Optional[str] = None,
    decision: Optional[str] = None,
    rule_hits: Optional[list] = None,
    reason: Optional[str] = None,
    extra: Optional[dict] = None,
    *,
    engine: Optional[Engine] = None,
) -> dict:
    """
    构造并持久化一条标准审计事件，返回完整事件 dict。

    - event_type 非法 / trace_id 为空 / JSON 字段不可序列化 → ValueError
    - engine 可选：传入则写入该库（测试临时库），否则走全局绑定引擎
    """
    et_value = _normalize_event_type(event_type)
    if not isinstance(trace_id, str) or not trace_id:
        raise ValueError(f"trace_id 非法: {trace_id!r}")
    rule_hits = _jsonable(list(rule_hits) if rule_hits is not None else [], "rule_hits")
    extra = _jsonable(dict(extra) if extra is not None else {}, "extra")

    with _open_session(engine) as s:
        with s.begin():
            row = EngineAuditEvent(
                event_type=et_value,
                trace_id=trace_id,
                instance_id=instance_id or "",
                decision=decision or "",
                rule_hits=rule_hits,
                reason=reason or "",
                extra=extra,
            )
            s.add(row)
            s.flush()
            return _row_to_dict(row)


_HOOK_EVENT_MAP = {
    "artifact_validate": AuditEventType.ARTIFACT_VALIDATE,
    "state_intercept": AuditEventType.STATE_INTERCEPT,
    "gate_guard": AuditEventType.GATE_GUARD,
    "content_issue": AuditEventType.CONTENT_ISSUE,
}


def emit_hook_event(
    hook: str,
    trace_id: str,
    decision: Optional[str] = None,
    rule_hits: Optional[list] = None,
    reason: Optional[str] = None,
    extra: Optional[dict] = None,
    *,
    engine: Optional[Engine] = None,
) -> dict:
    """内核四钩子判定事件便捷写入（hook 名 → 事件类型机械映射）。

    hook 必须为 artifact_validate / state_intercept / gate_guard / content_issue
    之一，其余值抛 ValueError。其余语义同 emit_audit。
    """
    if hook not in _HOOK_EVENT_MAP:
        raise ValueError(f"非法 hook: {hook!r}，允许值: {sorted(_HOOK_EVENT_MAP)}")
    return emit_audit(
        _HOOK_EVENT_MAP[hook], trace_id,
        decision=decision, rule_hits=rule_hits, reason=reason, extra=extra,
        engine=engine,
    )


def query_by_trace(trace_id: str, *, engine: Optional[Engine] = None) -> list[dict]:
    """按 trace_id 全链检索，按时间序（created_at, id 升序）返回全部事件。"""
    if not isinstance(trace_id, str) or not trace_id:
        raise ValueError(f"trace_id 非法: {trace_id!r}")
    with _open_session(engine) as s:
        rows = (
            s.query(EngineAuditEvent)
            .filter(EngineAuditEvent.trace_id == trace_id)
            .order_by(EngineAuditEvent.created_at.asc(), EngineAuditEvent.id.asc())
            .all()
        )
        return [_row_to_dict(r) for r in rows]
