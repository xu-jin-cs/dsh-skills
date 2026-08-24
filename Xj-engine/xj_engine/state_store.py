"""
StateStore — 引擎状态持久化收口（P2-5，2026-08-17）。

定位：引擎外围平台层。内核（backend/engine/kernel.py）保持无状态，
由母体把 transition 端点接线到本模块。

- StateStore          抽象接口：get_state / transition
- SqliteStateStore    SQLite 实现：engine_state_versions（当前状态+版本）
                      + engine_state_history（全量变更历史），乐观锁防并发撕裂
- StateStoreError     非法参数 / 实例不存在 / 源状态不匹配（不可重试）
- StateConflictError  乐观锁版本冲突（可重试，StateStoreError 子类）

表创建走 Base.metadata.create_all(tables=[...], checkfirst) 幂等；
生产默认接 backend.database.engine，测试传临时 sqlite 的 db_url/engine。
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    JSON,
    String,
    create_engine,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════
# 异常
# ═══════════════════════════════════════════════════════════════

class StateStoreError(Exception):
    """非法参数 / 实例不存在 / 源状态不匹配等不可重试错误。"""


class StateConflictError(StateStoreError):
    """乐观锁冲突：expected_version 与当前版本不一致（调用方应重读后重试）。"""


# ═══════════════════════════════════════════════════════════════
# 表模型
# ═══════════════════════════════════════════════════════════════

class EngineStateVersion(Base):
    """实例当前状态 + 乐观锁版本号。"""

    __tablename__ = "engine_state_versions"

    instance_id = Column(String(64), primary_key=True)
    state = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class EngineStateHistory(Base):
    """状态变更全量历史（支撑任意一次流转可复现）。"""

    __tablename__ = "engine_state_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instance_id = Column(String(64), nullable=False, index=True)
    from_state = Column(String(64), nullable=False)
    to_state = Column(String(64), nullable=False)
    operator = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False)          # 变更后的版本号
    trace_id = Column(String(64), default="", index=True)
    created_at = Column(DateTime, default=_utcnow)
    meta = Column(JSON, default=dict)


_STATE_TABLES = [EngineStateVersion.__table__, EngineStateHistory.__table__]


# ═══════════════════════════════════════════════════════════════
# 抽象接口
# ═══════════════════════════════════════════════════════════════

class StateStore(ABC):
    """状态持久化抽象接口（供母体接线 transition 端点）。"""

    @abstractmethod
    def get_state(self, instance_id: str) -> tuple[str, int]:
        """返回 (当前状态, 版本号)；实例不存在抛 StateStoreError。"""

    @abstractmethod
    def transition(
        self,
        instance_id: str,
        from_state: Optional[str],
        to_state: str,
        operator: str,
        expected_version: int,
        meta: Optional[dict] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        """
        乐观锁状态流转。成功返回 {"state": to_state, "version": 新版本号}。
        - expected_version 与当前版本不一致 → StateConflictError（并发撕裂保护）
        - from_state 非 None 且与当前状态不一致 → StateStoreError
        - 实例不存在 / 参数非法 → StateStoreError
        成功时同事务写 engine_state_history 一行。
        """


# ═══════════════════════════════════════════════════════════════
# SQLite 实现
# ═══════════════════════════════════════════════════════════════

class SqliteStateStore(StateStore):
    """
    SQLite StateStore。

    用法：
        store = SqliteStateStore()                    # 生产：backend.database.engine
        store = SqliteStateStore(db_url="sqlite:////tmp/x.db")   # 测试：临时库
        store = SqliteStateStore(engine=my_engine)    # 复用已有 engine
    """

    def __init__(self, db_url: Optional[str] = None, engine: Optional[Engine] = None):
        if engine is not None:
            self._engine = engine
        elif db_url is not None:
            kwargs = {"connect_args": {"check_same_thread": False}} if db_url.startswith("sqlite") else {}
            self._engine = create_engine(db_url, **kwargs)
        else:
            from backend.database import engine as default_engine
            self._engine = default_engine
        # 幂等建表（仅本模块的两张表，不触碰其他 Base 模型）
        Base.metadata.create_all(bind=self._engine, tables=_STATE_TABLES)
        self._Session = sessionmaker(bind=self._engine, autoflush=False, expire_on_commit=False)

    # ── 校验 ─────────────────────────────────────────────────

    @staticmethod
    def _validate(instance_id, from_state, to_state, operator, expected_version, meta):
        if not isinstance(instance_id, str) or not instance_id:
            raise StateStoreError(f"instance_id 非法: {instance_id!r}")
        if from_state is not None and (not isinstance(from_state, str) or not from_state):
            raise StateStoreError(f"from_state 非法: {from_state!r}")
        if not isinstance(to_state, str) or not to_state:
            raise StateStoreError(f"to_state 非法: {to_state!r}")
        if not isinstance(operator, str) or not operator:
            raise StateStoreError(f"operator 非法: {operator!r}")
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 0:
            raise StateStoreError(f"expected_version 非法: {expected_version!r}")
        if meta is not None:
            if not isinstance(meta, dict):
                raise StateStoreError(f"meta 必须是 dict 或 None: {type(meta).__name__}")
            try:
                json.dumps(meta)
            except (TypeError, ValueError) as exc:
                raise StateStoreError(f"meta 不可 JSON 序列化: {exc}") from exc

    # ── 接口实现 ──────────────────────────────────────────────

    def get_state(self, instance_id: str) -> tuple[str, int]:
        if not isinstance(instance_id, str) or not instance_id:
            raise StateStoreError(f"instance_id 非法: {instance_id!r}")
        with self._Session() as s:
            row = s.get(EngineStateVersion, instance_id)
            if row is None:
                raise StateStoreError(f"实例不存在: {instance_id}")
            return row.state, row.version

    def ensure_instance(self, instance_id: str, initial_state: str) -> dict:
        """登记实例初始状态（幂等）。已存在则返回当前 (state, version)。"""
        if not isinstance(instance_id, str) or not instance_id:
            raise StateStoreError(f"instance_id 非法: {instance_id!r}")
        if not isinstance(initial_state, str) or not initial_state:
            raise StateStoreError(f"initial_state 非法: {initial_state!r}")
        with self._Session() as s:
            with s.begin():
                row = s.get(EngineStateVersion, instance_id)
                if row is None:
                    row = EngineStateVersion(instance_id=instance_id, state=initial_state, version=0)
                    s.add(row)
                    s.flush()
                return {"state": row.state, "version": row.version}

    def transition(
        self,
        instance_id: str,
        from_state: Optional[str],
        to_state: str,
        operator: str,
        expected_version: int,
        meta: Optional[dict] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        self._validate(instance_id, from_state, to_state, operator, expected_version, meta)
        if trace_id is None and isinstance(meta, dict):
            trace_id = meta.get("trace_id") or ""
        new_version = expected_version + 1
        with self._Session() as s:
            with s.begin():
                row = s.get(EngineStateVersion, instance_id)
                if row is None:
                    raise StateStoreError(f"实例不存在: {instance_id}")
                if row.version != expected_version:
                    raise StateConflictError(
                        f"版本冲突: 实例 [{instance_id}] 当前版本 {row.version}，"
                        f"期望 {expected_version}（状态未变更，请重读后重试）"
                    )
                if from_state is not None and row.state != from_state:
                    raise StateStoreError(
                        f"源状态不匹配: 实例 [{instance_id}] 当前状态 [{row.state}]，"
                        f"声明 from_state [{from_state}]"
                    )
                prev_state = row.state  # CAS update 会同步会话内对象，先捕获旧状态
                # CAS 单语句更新：WHERE 带版本号，防读取-更新之间的并发撕裂
                res = s.execute(
                    update(EngineStateVersion)
                    .where(
                        EngineStateVersion.instance_id == instance_id,
                        EngineStateVersion.version == expected_version,
                    )
                    .values(state=to_state, version=new_version, updated_at=_utcnow())
                )
                if res.rowcount != 1:
                    raise StateConflictError(
                        f"版本冲突（并发更新）: 实例 [{instance_id}] 期望版本 {expected_version}"
                    )
                s.add(EngineStateHistory(
                    instance_id=instance_id,
                    from_state=prev_state,
                    to_state=to_state,
                    operator=operator,
                    version=new_version,
                    trace_id=trace_id or "",
                    meta=meta or {},
                ))
        return {"state": to_state, "version": new_version}

    def history(self, instance_id: str) -> list[dict]:
        """按时间序返回实例的全部变更历史（辅助接线/排障，不在抽象接口内）。"""
        with self._Session() as s:
            rows = (
                s.query(EngineStateHistory)
                .filter(EngineStateHistory.instance_id == instance_id)
                .order_by(EngineStateHistory.id.asc())
                .all()
            )
            return [
                {
                    "id": r.id,
                    "instance_id": r.instance_id,
                    "from_state": r.from_state,
                    "to_state": r.to_state,
                    "operator": r.operator,
                    "version": r.version,
                    "trace_id": r.trace_id,
                    "meta": r.meta or {},
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
