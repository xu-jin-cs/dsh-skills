"""并行 Dispatcher 节点：动态拓扑计算并启动分支执行。"""

import logging
from typing import Optional

from engine.flow.state import FlowState, FlowStatus
from engine.flow.node_defs import PARALLEL_START_NODE
from engine.flow.parallel.topology import get_ready_parallel_nodes
from engine.flow.parallel.branch_executor import (
    spawn_branch_tasks,
    merge_branch_state_delta,
)

logger = logging.getLogger("langgraph.parallel.dispatcher")


def parallel_dispatcher(state: FlowState) -> tuple[FlowState, Optional[str]]:
    """
    动态并行分发节点。

    逻辑：
      1. 根据 finished_nodes 计算本轮可并行节点；
      2. 无候选节点 → 退出并行区间；
      3. 有候选节点 → 线程池并发执行，等待全部完成；
      4. 合并分支产出到主线 State；
      5. 任一失败 → 冻结流程，等待人工重试。
    """
    candidates = get_ready_parallel_nodes(set(state.finished_nodes) | {PARALLEL_START_NODE})
    if not candidates:
        state.current_status = FlowStatus.EXIT_PARALLEL_ZONE
        return state, None

    instance_id = state.instance_id
    node_keys = [n.node_key for n in candidates]
    artifact_root_prefix = f"{instance_id}/branches"

    logger.info(
        "ParallelDispatcher: instance=%s 启动分支 %s",
        instance_id, node_keys,
    )

    results = spawn_branch_tasks(instance_id, node_keys, state, artifact_root_prefix)

    failed = [r for r in results if r["status"] != "success"]
    if failed:
        reasons = "; ".join(f"{r['node_key']}: {r.get('error', 'unknown')}" for r in failed)
        logger.error("ParallelDispatcher: 分支失败 %s", reasons)
        state.is_frozen = True
        state.freeze_reason = f"并行分支失败: {reasons}"
        state.current_status = FlowStatus.FROZEN
        return state, None

    for r in results:
        branch_state = r.get("branch_state")
        if branch_state:
            merge_branch_state_delta(state, branch_state)
            state.active_branch_keys.add(r["node_key"])

    state.current_status = FlowStatus.WAIT_BRANCH_AGGREGATE
    return state, None
