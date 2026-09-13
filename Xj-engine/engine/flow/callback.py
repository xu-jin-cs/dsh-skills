"""
LangGraph 全局回调钩子系统。

设计（来自全局融合方案）：
  LangGraph 状态变更后自动触发回调 → 调用 Harness HTTP 接口上报数据。
  不修改两套系统底层逻辑，通过回调钩子解耦。

回调签名：
  def callback(runnable, config, output) -> None:
      ...

集成方式：
  graph = FlowGraph()
  graph.compile(callbacks=[harness_sync_callback])
  graph.execute(state, callbacks=[harness_sync_callback])

写入顺序保障：
  1. LangGraph 先更新本地 Checkpoint（第一优先级）
  2. 再异步上报 Harness（第二优先级，失败不阻塞）
"""

import logging
import time
from typing import Any, Callable, Optional

from engine.flow.state import FlowState, FlowStatus, NodeType
from engine.flow.harness_client import HarnessClient, get_harness_client

logger = logging.getLogger("langgraph.callback")

# Callback 类型：接收 (state_before, state_after, node_key, node_kwargs)
# 返回 None（纯副作用，不修改 State）
SyncCallback = Callable[
    [FlowState, FlowState, str, dict],
    None,
]


# 增量优化202607：Harness 上报指数退避重试封装
def _harness_call_with_retry(call_fn, max_retries: int = 3, initial_delay: float = 0.5):
    """
    使用指数退避重试调用 Harness API。
    Args:
        call_fn: 无参数的可调用对象（闭包包好入参）
        max_retries: 最大重试次数
        initial_delay: 初始退避秒数
    Returns:
        call_fn 的返回值
    Raises:
        最后一次异常（重试耗尽后）
    """
    last_exc = None
    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        try:
            return call_fn()
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                logger.warning("Harness 同步重试 [%d/%d]: %s", attempt, max_retries, e)
                time.sleep(delay)
                delay *= 2  # 指数退避
            else:
                logger.error("Harness 同步重试耗尽 [%d/%d]: %s", attempt, max_retries, e)
    raise last_exc  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════
# 内置回调函数
# ═══════════════════════════════════════════════════════════════

def harness_sync_callback(
    state_before: FlowState,
    state_after: FlowState,
    node_key: str,
    node_kwargs: dict,
) -> None:
    """
    全局同步回调 — 每个 Node 执行完成后自动触发。

    自动判断变更类型并调用 HarnessClient 对应方法：
      - 状态变更 → transition()
      - 新增交付物 → add_deliverable()
      - 新增违规 → report_violation()
      - 测试结果变更 → report_test_result()

    2026-07-05 增强：
      - 每步强制同步「节点执行进度」心跳事件（harness 可追踪执行流）
      - 心跳事件含 execution_trace 最新条目

    增量优化202607：
      - 所有 HarnessClient 调用使用指数退避重试
      - 同步失败时写入 execution_trace 标记待同步
    """
    client = get_harness_client()
    instance_id = state_after.instance_id

    def _safe_sync(sync_name: str, call_fn):
        """安全的同步调用（含重试 + 失败标记）"""
        try:
            _harness_call_with_retry(call_fn)
        except Exception as e:
            logger.error("Harness %s 同步失败 [%s]: %s", sync_name, instance_id, e)
            state_after.execution_trace.append(
                type('ExecTrace', (), {
                    'node_type': type('NT', (), {'value': 'callback'})(),
                    'status': 'sync_failed',
                    'summary': f"[callback] {sync_name} 同步失败: {e}",
                    'error': str(e),
                    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                })()
            )

    # 1. 状态变更
    if state_before.current_status != state_after.current_status:
        to_status = state_after.current_status.value if hasattr(state_after.current_status, 'value') else str(state_after.current_status)
        _safe_sync("transition", lambda: client.transition(
            instance_id=instance_id,
            to_state=to_status,
            operator=node_key,
            comment=f"Node [{node_key}] 执行完成",
        ))

    # 2. 新增交付物
    new_deliverables = _diff_deliverables(state_before, state_after)
    for d in new_deliverables:
        curr_status = state_after.current_status.value if hasattr(state_after.current_status, 'value') else str(state_after.current_status)
        _safe_sync("add_deliverable", lambda dd=d: client.add_deliverable(
            instance_id=instance_id,
            step=curr_status,
            content_type=dd.content_type,
            summary=dd.summary,
            agent_role=dd.agent_role.value,
            file_path=dd.file_path,
        ))

    # 3. 新增违规
    new_violations = _diff_violations(state_before, state_after)
    for v in new_violations:
        _safe_sync("report_violation", lambda vv=v: client.report_violation(
            instance_id=instance_id,
            violation_type=vv.violation_type.value,
            description=vv.description,
            operator=node_key,
        ))

    # 4. 测试结果变更
    _sync_test_results(client, instance_id, state_before, state_after, node_key)

    # 5. 冻结变更
    if not state_before.is_frozen and state_after.is_frozen:
        _safe_sync("freeze", lambda: client.freeze(
            instance_id=instance_id,
            reason=state_after.freeze_reason or "流程违规熔断",
            operator="sv-supervisor",
            violation_type="COMPLIANCE_FAILURE",
        ))

    # 6. 全量同步心跳
    latest_exec = None
    if state_after.execution_trace:
        latest_exec = state_after.execution_trace[-1]
    heartbeat_payload = {
        "node_key": node_key,
        "execution_trace_count": len(state_after.execution_trace),
        "latest_node": latest_exec.node_type.value if latest_exec else "",
        "latest_status": latest_exec.status if latest_exec else "",
        "deliverable_count": len(state_after.deliverables),
        "violation_count": len(state_after.violations),
        "total_points": state_after.total_points,
    }
    _safe_sync("send_event", lambda: client.send_event(
        instance_id=instance_id,
        event_type="NODE_HEARTBEAT",
        operator=node_key,
        payload=heartbeat_payload,
    ))


def noop_callback(
    state_before: FlowState,
    state_after: FlowState,
    node_key: str,
    node_kwargs: dict,
) -> None:
    """空回调（默认禁用 Harness 同步时使用）"""
    pass


# ═══════════════════════════════════════════════════════════════
# 差分检测函数
# ═══════════════════════════════════════════════════════════════

def _diff_deliverables(before: FlowState, after: FlowState) -> list:
    """检测新增的交付物"""
    if len(after.deliverables) <= len(before.deliverables):
        return []
    return after.deliverables[len(before.deliverables):]


def _diff_violations(before: FlowState, after: FlowState) -> list:
    """检测新增的违规"""
    if len(after.violations) <= len(before.violations):
        return []
    return after.violations[len(before.violations):]


def _diff_bugs(before: FlowState, after: FlowState) -> list:
    """检测新增的缺陷"""
    if len(after.bugs) <= len(before.bugs):
        return []
    return after.bugs[len(before.bugs):]


def _sync_test_results(
    client: HarnessClient,
    instance_id: str,
    before: FlowState,
    after: FlowState,
    node_key: str,
) -> None:
    """同步测试结果变更（增量优化202607：增加重试）"""
    # Smoketest 结果
    if after.smoke_test and (not before.smoke_test or
                             before.smoke_test.pass_count != after.smoke_test.pass_count):
        t = after.smoke_test
        try:
            _harness_call_with_retry(lambda: client.report_test_result(
                instance_id=instance_id,
                agent_role="exec-smoke",
                skill_name="冒烟测试 Skill",
                status="passed" if not t.has_p0 else "failed",
                pass_count=t.pass_count,
                fail_count=t.fail_count,
                summary=t.summary,
                report_data={"batch_id": t.batch_id, "total_steps": t.total_steps},
            ))
        except Exception as e:
            logger.warning("冒烟测试结果同步失败 [%s]: %s", instance_id, e)

    # Full test 结果
    if after.full_test and (not before.full_test or
                            before.full_test.pass_count != after.full_test.pass_count):
        t = after.full_test
        try:
            _harness_call_with_retry(lambda: client.report_test_result(
                instance_id=instance_id,
                agent_role="exec-full",
                skill_name="全量测试 Skill",
                status="passed" if not t.has_p0 and not t.has_p1 else "failed",
                pass_count=t.pass_count,
                fail_count=t.fail_count,
                summary=t.summary,
                report_data={"batch_id": t.batch_id, "total_steps": t.total_steps},
            ))
        except Exception as e:
            logger.warning("全量测试结果同步失败 [%s]: %s", instance_id, e)


# ═══════════════════════════════════════════════════════════════
# 回调管理器
# ═══════════════════════════════════════════════════════════════

class CallbackManager:
    """
    回调管理器 — 统一管理和触发所有回调。

    每个 Node 执行完成后：
      1. FlowGraph.step() 调用 manager.trigger()
      2. manager 依次执行所有注册的回调
    """

    def __init__(self, callbacks: Optional[list[SyncCallback]] = None):
        self.callbacks: list[SyncCallback] = callbacks or []
        self._enabled = True

    def register(self, callback: SyncCallback) -> None:
        """注册一个回调"""
        self.callbacks.append(callback)

    def enable(self) -> None:
        """启用回调"""
        self._enabled = True

    def disable(self) -> None:
        """禁用回调（临时关闭 Harness 同步）"""
        self._enabled = False

    def trigger(
        self,
        state_before: FlowState,
        state_after: FlowState,
        node_key: str,
        node_kwargs: dict,
    ) -> None:
        """
        触发所有已注册回调。

        规则变更（2026-07-05）：
          - HarnessSyncError → 向上传播（阻断流程、冻结实例）
          - 其他异常 → 记录 warning，不阻塞（非关键回调）
        """
        if not self._enabled or not self.callbacks:
            return

        for cb in self.callbacks:
            try:
                cb(state_before, state_after, node_key, node_kwargs)
            except Exception as e:
                # HarnessSyncError → 阻断流程（关键同步失败）
                if e.__class__.__name__ == "HarnessSyncError":
                    raise
                # 其他异常 → 记录 warning，不阻塞
                logger.warning("回调异常 [%s]: %s", getattr(cb, "__name__", str(cb)), e)

    @property
    def count(self) -> int:
        return len(self.callbacks)


# ═══════════════════════════════════════════════════════════════
# 默认回调配置
# ═══════════════════════════════════════════════════════════════

def default_callbacks() -> list[SyncCallback]:
    """返回默认回调集合（阶段2+启用）"""
    return [harness_sync_callback]
