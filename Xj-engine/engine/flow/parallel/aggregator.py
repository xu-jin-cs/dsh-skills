"""并行 Aggregator 节点：等待分支收敛并决定循环/退出。"""

import logging
from typing import Optional

from engine.flow.state import FlowState, FlowStatus
from engine.flow.node_defs import PARALLEL_START_NODE
from engine.flow.parallel.branch_store import list_instance_branches_sync
from engine.flow.parallel.topology import get_ready_parallel_nodes

logger = logging.getLogger("langgraph.parallel.aggregator")


def parallel_aggregator(state: FlowState) -> tuple[FlowState, Optional[str]]:
    """
    并行聚合节点。

    逻辑：
      1. 查询 instance_branch_status 全部分支状态；
      2. 存在失败/取消 → 保持 WAIT_BRANCH_AGGREGATE（主线已在 Dispatcher 冻结，此处幂等）；
      3. 仍有运行中/待执行 → 保持等待；
      4. 全部成功 → 更新 finished_nodes，检查是否还有下一批候选。
    """
    instance_id = state.instance_id
    branches = list_instance_branches_sync(instance_id)

    if not branches:
        # 无分支记录说明当前实例未进入并行区间，直接退出
        state.current_status = FlowStatus.EXIT_PARALLEL_ZONE
        return state, None

    status_map = {b.branch_node_key: b.status for b in branches}
    terminal_failed = {"failed", "cancel"}
    active = {"pending", "running"}

    any_failed = any(s in terminal_failed for s in status_map.values())
    has_active = any(s in active for s in status_map.values())

    if any_failed:
        state.current_status = FlowStatus.WAIT_BRANCH_AGGREGATE
        return state, None

    if has_active:
        state.current_status = FlowStatus.WAIT_BRANCH_AGGREGATE
        return state, None

    # 全部分支成功：更新 finished_nodes 与 active_branch_keys
    for node_key in status_map:
        state.finished_nodes.add(node_key)
    state.active_branch_keys.clear()

    # 检查是否还有下一批就绪节点
    next_candidates = get_ready_parallel_nodes(set(state.finished_nodes) | {PARALLEL_START_NODE})
    if next_candidates:
        logger.info(
            "ParallelAggregator: instance=%s 本轮完成 %s，继续扫描下一批 %s",
            instance_id, list(status_map.keys()), [n.node_key for n in next_candidates],
        )
        state.current_status = FlowStatus.SCAN_NEXT_BATCH
        return state, None

    logger.info("ParallelAggregator: instance=%s 全部分支完成，退出并行区间", instance_id)
    state.current_status = FlowStatus.EXIT_PARALLEL_ZONE
    return state, None
