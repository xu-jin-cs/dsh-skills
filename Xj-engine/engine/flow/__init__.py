# ══════════════════════════════════════════════════════════════════════
# 【Xj-engine 图层 · ENGINE.FLOW】2026-09-13 替换落地：
#   本层=langgraph FlowGraph 迁入 Xj-engine 的正式图编排层（用户裁定）。
#   2026-11-17 headless 图执行通道废除：内置 PM 节点体（nodes.py）、
#   平台上报件（callback/harness_client）、并行分支执行器（parallel 执行件）
#   全部移除——引擎不做执行，只负责契约编译/校验、节点调度与控制、
#   交付物签发、事件上报；执行一律经宿主通道（assemble → spawn → snapshot）。
# ══════════════════════════════════════════════════════════════════════
"""
Xj-engine 图编排层（ENGINE.FLOW）— 契约编译/校验与节点调度的控制面。

架构（2026-11-17 headless 通道废除后）：
  引擎（本层）                                       agent-harness（宿主）
  ┌─────────────────────────────────────┐          ┌──────────────┐
  │ workflow_compiler / validator       │          │ assemble     │
  │ FlowGraph（节点注册容器+调度控制）    │          │   ↓ spawn    │
  │ Checkpoint（本地 SQLite 快照）       │          │   ↓ snapshot │
  └─────────────────────────────────────┘          │ 状态迁移留痕  │
                                                   └──────────────┘
  执行体=宿主会话（模型即当前会话）；引擎不内置模型、不推演节点体。

原则：
  1. 引擎不做执行（2026-11-13 执行载体边界裁定；2026-11-17 废除 headless 通道落实）
  2. agent-harness = 宿主（可选平台，不是引擎），状态迁移留痕经宿主通道
  3. 唯一数据源 = FlowState（运行时），宿主仅镜像备份
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
from engine.flow.edges import (
    edge_after_smoke_test, edge_after_full_test,
    edge_after_code_review, edge_bug_fix_loop,
    edge_rollback_route, edge_gov_compress_route,
    GOVERNANCE_EDGES,
)
from engine.flow.graph import FlowGraph
from engine.flow.checkpoint import (
    SqliteCheckpointer, get_checkpointer,
)
from engine.flow.integration import (
    state_to_json, state_from_json, json_to_state,
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
    # Edges（PM 图拓扑数据，compile 已废除，仅作遗留定义保留）
    "edge_after_smoke_test", "edge_after_full_test",
    "edge_after_code_review", "edge_bug_fix_loop",
    "edge_rollback_route", "edge_gov_compress_route",
    "GOVERNANCE_EDGES",
    # Graph
    "FlowGraph",
    # Checkpoint
    "SqliteCheckpointer", "get_checkpointer",
    # Integration
    "state_to_json", "state_from_json", "json_to_state",
    "assign_thread_id", "build_initial_state",
    "state_to_file_cache",
]
