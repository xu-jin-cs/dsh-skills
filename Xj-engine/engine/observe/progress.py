"""observe 进度派生 · **唯一实现（引擎侧）**。

原先这条口径有 5 处副本（list_tasks / get_task_detail / rerun_task / replace_service /
_maybe_complete_task），P-22 修过一次只落 2 处就复发。2026-11-08 统一上收到这里，
backend 一律 import 本模块，禁止本地再抄一份。

纯函数：不碰 DB、不读环境变量，便于单测。
"""
from __future__ import annotations

TASK_NODE = "__task__"
# 兼容历史：observe_agent 旧版用 node_id="task" 记任务级行（同义，必须一并排除）
TASK_LEVEL_NODES = ("__task__", "task")


def node_seq_maps(nodes: list[dict]) -> tuple[dict, dict]:
    """声明节点 → 序号映射。**nodeId 优先、agentId 兜底**。

    skill 资产所有节点共用 agentId=main，只按 agentId 建映射会被末节点覆盖，
    导致"跑了 2/3 就判完成 / 进度虚高"。
    """
    seq_of_node = {n.get("nodeId"): n.get("seq") for n in nodes if n.get("nodeId")}
    seq_of_agent: dict = {}
    for n in nodes:
        seq_of_agent.setdefault(n.get("agentId"), n.get("seq"))
    return seq_of_node, seq_of_agent


def derive_progress(nodes: list[dict], runtime: list[dict]) -> dict:
    """进度/终态派生（唯一实现）。

    - `node_id='__task__'` 的任务级行只驱动任务状态，**不参与**节点进度
      （否则 agentId=main 会经兜底映射把第一个 main 节点误判成 running/completed）
    - 每行先按 nodeId 精确映射回声明序号，映射不到再按 agentId 兜底
    - frontier = 已执行（completed/running/failed）的最大声明序号
    - done = 末声明节点已完成
    """
    seq_of_node, seq_of_agent = node_seq_maps(nodes)
    last_seq = max((n.get("seq") or 0 for n in nodes), default=0)
    ords, completed = [], set()
    for x in runtime:
        if x.get("nodeId") in TASK_LEVEL_NODES:
            continue
        o = seq_of_node.get(x.get("nodeId")) or seq_of_agent.get(x.get("agentId"))
        if not o:
            continue
        if x.get("status") in ("completed", "running", "failed"):
            ords.append(o)
        if x.get("status") == "completed":
            completed.add(o)
    frontier = max(ords) if ords else 0
    return {"frontier": frontier, "completedSeqs": completed,
            "lastSeq": last_seq, "done": bool(last_seq) and last_seq in completed}


def next_rerun_target(nodes: list[dict], runtime: list[dict]) -> str | None:
    """续跑起点：第一个未完成（非 completed/skipped）的声明节点；全完成为 None。"""
    prog = derive_progress(nodes, runtime)
    for n in nodes:
        st = "pending"
        for x in runtime:
            if x.get("nodeId") == n.get("nodeId"):
                st = x.get("status") or st
                break
        if (n.get("seq") or 0) < prog["frontier"] and st == "pending":
            st = "completed"
        if st not in ("completed", "skipped"):
            return n.get("nodeId")
    return None
