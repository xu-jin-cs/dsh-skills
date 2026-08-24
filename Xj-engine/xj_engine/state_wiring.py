"""
StateStore 双写统一收口（短板3修复，2026-08-20）。

背景：StateStore 双写此前仅 instances.py:761 一处接入，engine_state_history
渗透不足。本模块把"增量双写"（乐观锁版本轨迹 + engine_state_history 历史行 +
标准审计事件）收口为两个函数，供全部引擎状态迁移路径复用：

- wire_state_transition    一次真实状态迁移的双写（含存量滞后 resync 对齐）
- wire_state_registration  实例创建时的初始状态登记（幂等，为后续迁移建立版本基线）

行为约定（与 instances.py:761 既有范式一致）：
- 失败只 logger.warning 告警，绝不阻断主流程（返回 False）；
- 同状态（from_state == to_state）视为无迁移，直接跳过；
- SqliteStateStore / emit_audit 惰性 import 并默认接本地 database.engine，
  测试可通过重绑本地 database.engine + audit.set_engine 指向临时库。

resync 说明：若 StateStore 追踪状态滞后于调用方声明的 from_state（历史窗口期
未接线的迁移所致），先补一行 resync 追赶轨迹再记录本次迁移，保证历史链连续
可复现；这是机械对齐逻辑，不含任何业务规则。
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def wire_state_transition(
    instance_id: str,
    from_state: Optional[str],
    to_state: str,
    operator: str,
    *,
    source: str,
    meta: Optional[dict] = None,
) -> bool:
    """增量双写一次状态迁移。返回 True=已落账，False=跳过或接线失败（已告警）。

    - instance_id 非法 / 同状态 → 返回 False（无迁移，不算失败）
    - 任何接线异常 → 告警并返回 False，不影响主流程
    """
    if not isinstance(instance_id, str) or not instance_id:
        return False
    if from_state is not None and from_state == to_state:
        return False  # 同状态无迁移（对齐 same-state 语义：不推版本、不落历史行）
    try:
        from .state_store import SqliteStateStore
        from .audit import emit_audit, AuditEventType

        store = SqliteStateStore()
        store.ensure_instance(instance_id, from_state or to_state)
        cur_state, cur_ver = store.get_state(instance_id)

        if from_state is not None and cur_state != from_state:
            # 存量滞后对齐：StateStore 追踪状态落后于声明的源状态时，
            # 先补一行 resync 追赶轨迹，保证历史链连续可复现。
            store.transition(
                instance_id, cur_state, from_state, operator,
                expected_version=cur_ver,
                meta={"source": source, "resync": True},
                trace_id=f"{source}-{instance_id}-v{cur_ver}-resync",
            )
            _, cur_ver = store.get_state(instance_id)

        trace_id = f"{source}-{instance_id}-v{cur_ver}"
        store.transition(
            instance_id, from_state, to_state, operator,
            expected_version=cur_ver,
            meta={"source": source, **(meta or {})},
            trace_id=trace_id,
        )
        emit_audit(
            AuditEventType.STATE_INTERCEPT, trace_id=trace_id,
            instance_id=instance_id, decision="pass",
            rule_hits=[f"{from_state}->{to_state}"],
            reason=f"{source} 接线落账",
            extra={"operator": operator, **(meta or {})},
        )
        return True
    except Exception as wire_e:
        logger.warning("StateStore 双写接线失败（不影响主流程）[%s]: %s", instance_id, wire_e)
        return False


def wire_state_registration(instance_id: str, initial_state: str, *, source: str) -> bool:
    """实例创建时登记初始状态（幂等）。已存在则不动，返回 True。"""
    if not isinstance(instance_id, str) or not instance_id:
        return False
    try:
        from .state_store import SqliteStateStore

        SqliteStateStore().ensure_instance(instance_id, initial_state)
        return True
    except Exception as wire_e:
        logger.warning("StateStore 实例登记失败（不影响主流程）[%s] source=%s: %s",
                       instance_id, source, wire_e)
        return False
