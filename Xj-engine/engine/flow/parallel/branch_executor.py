"""分支执行器：在独立线程中执行单个并行分支节点。"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from engine.flow.parallel.branch_store import (
    get_db_session,
    init_branch_record,
    set_branch_running,
    set_branch_final,
)
from engine.flow.state import FlowState

logger = logging.getLogger("langgraph.parallel.branch_executor")


def run_branch_node(
    instance_id: str,
    node_key: str,
    base_state: FlowState,
    artifact_root: str,
) -> dict:
    """
    同步执行单个分支节点，返回包含完整分支状态的结果字典。

    每个分支：
      - 使用独立 DB Session 与 Checkpoint thread_id
      - 保留主 instance_id 用于 Harness 回调
      - 执行单个目标节点后保存 checkpoint
    """
    sub_thread_id = f"{instance_id}_{node_key}"
    db = get_db_session()
    try:
        init_branch_record(db, instance_id, node_key, sub_thread_id, artifact_root)
        set_branch_running(db, sub_thread_id)

        # 深拷贝 State；保留主 instance_id 用于回调，checkpoint 使用 sub_thread_id
        branch_state = base_state.model_copy(deep=True)

        from engine.flow.graph import get_flow_graph
        graph = get_flow_graph()
        result_state = graph.execute_branch(
            node_key=node_key,
            state=branch_state,
            thread_id=sub_thread_id,
        )

        set_branch_final(db, sub_thread_id, "success")
        logger.info("分支完成: instance=%s node=%s thread=%s", instance_id, node_key, sub_thread_id)
        return {
            "node_key": node_key,
            "sub_thread_id": sub_thread_id,
            "status": "success",
            "branch_state": result_state,
            "error": None,
        }
    except Exception as e:
        logger.exception("分支失败: instance=%s node=%s", instance_id, node_key)
        set_branch_final(db, sub_thread_id, "failed", error_msg=str(e))
        return {
            "node_key": node_key,
            "sub_thread_id": sub_thread_id,
            "status": "failed",
            "branch_state": None,
            "error": str(e),
        }
    finally:
        db.close()


def spawn_branch_tasks(
    instance_id: str,
    node_keys: list[str],
    base_state: FlowState,
    artifact_root_prefix: str,
) -> list[dict]:
    """在本地线程池中并发启动多个分支节点并等待全部完成。"""
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, len(node_keys))) as executor:
        futures = {
            executor.submit(
                run_branch_node,
                instance_id,
                node_key,
                base_state,
                f"{artifact_root_prefix}/{node_key}/",
            ): node_key
            for node_key in node_keys
        }
        for future in as_completed(futures):
            results.append(future.result())
    return results


def merge_branch_state_delta(state: FlowState, branch_state: FlowState) -> None:
    """将分支执行产生的新交付物/Bug/违规合并到主线 State（按索引差量，避免重复）。"""
    base_deliverables_len = len(state.deliverables)
    base_bugs_len = len(state.bugs)
    base_violations_len = len(state.violations)
    base_total_points = state.total_points

    state.deliverables.extend(branch_state.deliverables[base_deliverables_len:])
    state.bugs.extend(branch_state.bugs[base_bugs_len:])
    state.violations.extend(branch_state.violations[base_violations_len:])

    state.unresolved_bug_count = sum(1 for b in state.bugs if not b.resolved)
    state.total_points = base_total_points + (branch_state.total_points - base_total_points)
