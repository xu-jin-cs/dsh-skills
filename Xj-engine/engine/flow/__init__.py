# ══════════════════════════════════════════════════════════════════════
# 【Xj-engine 图层 · ENGINE.FLOW】2026-09-13 替换落地：
#   本层=langgraph FlowGraph 迁入 Xj-engine 的正式图编排层（用户裁定）。
#   相对原过渡组件的新增能力：①checkpoint StateStore 桥接（断点进引擎
#   状态版本体系，乐观锁+历史审计，核心零改动）；②动态并行接
#   dispatch_switch 机械判定（judge_parallel_fanout）；③et_test_gates 门禁
#   与 audit 审计为引擎内建通道。
#   原 langgraph 过渡组件（xjframe_flow）按双跑一致性验收后退役。
# ══════════════════════════════════════════════════════════════════════
"""
Xj-engine 图编排层（ENGINE.FLOW）— 组合 Nodes + Edges 的可执行状态机。

架构（2026-11-01 通道正名后的现状）：
  FlowGraph Orchestration Layer                     agent-harness（宿主）
  ┌─────────────────────────────────────┐          ┌──────────────┐
  │ Node(Agent) ←→ State(唯一数据源)     │  callback  │ HTTP API     │
  │         ↓ Edge(条件路由)             │ ────────→ │ 镜像存证      │
  │         ↓ Checkpoint(本地 SQLite)    │           │ 状态迁移留痕  │
  │         ↓ Callback(全局钩子)         │           │ 可视化面板    │
  └─────────────────────────────────────┘          └──────────────┘

原则：
  1. FlowGraph = 实时任务运行内核（2026-09-13 自 langgraph FlowGraph 平迁，依赖已清零）
  2. agent-harness = 宿主（可选平台，不是引擎），仅镜像存证与可视化
  3. 数据桥接 = 统一事件回调；上报失败重试 3 次后留 sync_failed 痕迹，不阻塞执行
  4. 唯一数据源 = FlowState（运行时），宿主仅镜像备份
  5. 2026-11-01 起：图执行通道为 headless 备用；pm 正通道 = 宿主 stage 隔离 spawn
"""

import os as _os

from engine.flow.state import (
    FlowState, FlowStatus, BugLevel, NodeType,
    TestResult, DeliverableRecord, BugRecord, ViolationRecord,
    FilePathRef,
)
from engine.flow.file_utils import (
    write_evidence_file, read_file_ref, verify_file_ref,
)
from engine.flow.nodes import (
    PMNode, SPMNode, DPMNode, UIDesignerNode,
    TestCaseDesignerNode, FrontendDevNode, BackendDevNode,
    TestExecutorNode, TestSupervisorNode, CodeReviewNode,
    OpsDeployNode, AcceptanceNode, RetrospectiveNode,
    SVSupervisorNode,
    InputHookNode, DeepSeekInferNode, OutputHookNode,
    SnapshotBackupNode, SnapshotRestoreNode, ContextCompressNode,
    ALL_NODES,
)
from engine.flow.edges import (
    edge_after_smoke_test, edge_after_full_test,
    edge_after_code_review, edge_bug_fix_loop,
    edge_rollback_route, edge_gov_compress_route,
    GOVERNANCE_EDGES,
)
from engine.flow.graph import FlowGraph, get_flow_graph
if _os.environ.get("XJFRAME_STRICT_NO_HOST") != "1":
    try:
        from engine.flow.callback import (
            harness_sync_callback, CallbackManager,
        )
    except Exception:  # noqa: BLE001 — 无宿主时降级
        harness_sync_callback = None
        CallbackManager = None
else:
    harness_sync_callback = None
    CallbackManager = None
from engine.flow.checkpoint import (
    SqliteCheckpointer, get_checkpointer,
)
if _os.environ.get("XJFRAME_STRICT_NO_HOST") != "1":
    try:
        from engine.flow.harness_client import (
            HarnessClient, get_harness_client,
        )
    except Exception:  # noqa: BLE001
        HarnessClient = None
        get_harness_client = None
else:
    HarnessClient = None
    get_harness_client = None
from engine.flow.integration import (
    state_to_json, json_to_state,
    assign_thread_id, build_initial_state,
    state_to_file_cache,
)

__all__ = [
    # State
    "FlowState", "FlowStatus", "BugLevel", "NodeType",
    "TestResult", "DeliverableRecord", "BugRecord", "ViolationRecord",
    "FilePathRef",
    # File utils
    "write_evidence_file", "read_file_ref", "verify_file_ref",
    # Nodes
    "PMNode", "SPMNode", "DPMNode", "UIDesignerNode",
    "TestCaseDesignerNode", "FrontendDevNode", "BackendDevNode",
    "TestExecutorNode", "TestSupervisorNode", "CodeReviewNode",
    "OpsDeployNode", "AcceptanceNode", "RetrospectiveNode",
    "SVSupervisorNode",
    "InputHookNode", "DeepSeekInferNode", "OutputHookNode",
    "SnapshotBackupNode", "SnapshotRestoreNode", "ContextCompressNode",
    "ALL_NODES",
    # Edges
    "edge_after_smoke_test", "edge_after_full_test",
    "edge_after_code_review", "edge_bug_fix_loop",
    "edge_rollback_route", "edge_gov_compress_route",
    "GOVERNANCE_EDGES",
    # Graph
    "FlowGraph", "get_flow_graph",
    # Callback
    "harness_sync_callback", "CallbackManager",
    # Checkpoint
    "SqliteCheckpointer", "get_checkpointer",
    # Harness Client
    "HarnessClient", "get_harness_client",
    # Integration
    "state_to_json", "json_to_state",
    "assign_thread_id", "build_initial_state",
    "state_to_file_cache",
]
