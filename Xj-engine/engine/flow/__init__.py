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
LangGraph 状态机融合层 — 自研 agent-harness 的 LangGraph 嵌入方案。

架构层（来自全局融合方案）：
  LangGraph Orchestration Layer                    Agent-Harness
  ┌─────────────────────────────────────┐          ┌──────────────┐
  │ Node(Agent) ←→ State(唯一数据源)     │  callback  │ HTTP API     │
  │         ↓ Edge(条件路由)             │ ────────→ │ DB 持久化     │
  │         ↓ Checkpoint(本地 SQLite)    │           │ HMAC 签名    │
  │         ↓ Callback(全局钩子)         │           │ 可视化面板    │
  └─────────────────────────────────────┘          └──────────────┘

融合原则：
  1. LangGraph = 实时任务运行内核
  2. Agent-Harness = 持久化存证与可视化管控平台
  3. 数据桥接 = 统一事件回调（不修改两套底层逻辑）
  4. 唯一数据源 = LangGraph State（运行时），Harness 仅镜像备份
"""

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
from engine.flow.callback import (
    harness_sync_callback, CallbackManager,
)
from engine.flow.checkpoint import (
    SqliteCheckpointer, get_checkpointer,
)
from engine.flow.harness_client import (
    HarnessClient, get_harness_client,
)
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
