"""动态拓扑计算：根据节点依赖声明计算本轮可并行执行集合。"""

from typing import List, Set

from engine.flow.node_defs import FlowNodeMeta, get_all_parallel_zone_nodes


def compute_parallel_candidates(
    all_zone_nodes: List[FlowNodeMeta],
    finished_nodes: Set[str],
) -> List[FlowNodeMeta]:
    """
    动态计算本轮可并行执行节点。

    规则：
      1. 节点所有强依赖全部在 finished_nodes 内；
      2. 节点自身尚未完成；
      3. 候选集合内任意两个节点互不互为依赖。
    """
    ready = [
        n for n in all_zone_nodes
        if n.node_key not in finished_nodes and set(n.depends_on).issubset(finished_nodes)
    ]
    if not ready:
        return []

    final_batch: List[FlowNodeMeta] = []
    for candidate in ready:
        conflict = any(
            candidate.node_key in exist.depends_on or exist.node_key in candidate.depends_on
            for exist in final_batch
        )
        if not conflict:
            final_batch.append(candidate)
    return final_batch


def get_ready_parallel_nodes(finished_nodes: Set[str]) -> List[FlowNodeMeta]:
    """便捷入口：基于默认并行区间节点计算候选集合。"""
    return compute_parallel_candidates(get_all_parallel_zone_nodes(), finished_nodes)
