# ══════════════════════════════════════════════════════════════════════
# 【过渡组件 · TRANSITIONAL】2026-09-13 用户裁定：
#   本模块（langgraph FlowGraph 平迁版）暂任 Xj-Frame 图编排内核。
#   待 Xj-engine 补足图拓扑短板（depends_on 拓扑/动态并行/checkpoint 断点）后
#   整体替换本模块——替换点=本包全部节点/边/图执行调用方。
#   新代码引用本包时请注意此替换预期，编排逻辑尽量走 FlowNodeMeta 声明式。
# ══════════════════════════════════════════════════════════════════════
"""
LangGraph Graph — 组合 Nodes + Edges 的可执行图。

设计（来自全局融合方案）：
  LangGraph 定位：实时任务运行内核
  Agent-Harness 定位：持久化存证与可视化管控平台

数据写入顺序保障：
  1. Node 执行（纯 State 操作，无 DB 依赖）
  2. 保存本地 Checkpoint（第一优先级）
  3. 触发回调（第二优先级，失败不阻塞）

融合后完整数据流转：
  用户发起任务 → FlowGraph.execute()
    ├─ checkpoint.load() — 断点恢复（如存在）
    ├─ Node 循环：
    │   ├─ step() — 执行 Node → 检查 Edge
    │   ├─ checkpoint.save() — 本地持久化
    │   └─ callback.trigger() → Harness HTTP 上报
    └─ 完成 → 回调触发 Harness 批量导入
"""

import copy
import logging
from typing import Any, Callable, Optional

from engine.flow.state import FlowState, FlowStatus, NodeType
from engine.flow.nodes import ALL_NODES, NodeFn
from engine.flow.edges import (
    CONDITIONAL_EDGES, LINEAR_EDGES, GOVERNANCE_EDGES, get_linear_next,
)
from engine.flow.callback import (
    SyncCallback, CallbackManager, noop_callback,
)
from engine.flow.checkpoint import (
    SqliteCheckpointer, get_checkpointer,
)
from engine.flow.integration import (
    state_to_json, json_to_state,
)
try:  # 宿主门禁（NodeGateET）：有 backend 时启用；无宿主降级为空门禁（2026-09-13 钩子化）
    from backend.services.node_gate_et import get_node_gate  # type: ignore
except Exception:  # noqa: BLE001
    class _NullNodeGate:
        def run_pre(self, payload): return {"code": "success", "via": "null_gate_no_host"}
        def run_post(self, payload): return {"code": "success", "via": "null_gate_no_host"}
    def get_node_gate(): return _NullNodeGate()
# RETIRED-2026-08-17: 旧 orchestrator_gate 门控已退役，节点门禁由节点侧 ET 组装 Payload 调 kernel.et() 承接（见 docs/HANDOFF_engine_et.md §5-3）。
# 原 SupervisorGuard / OrchestratorGate / validate_deliverable_state 导入与 USE_LAYERED_RULES 开关一并移除，
# 旧模块归档于 _backups/20260817_legacy_engine_retirement/engine/。

logger = logging.getLogger("langgraph.graph")


class FlowGraph:
    """
    完整 LangGraph 流程图。

    使用方法：
      # 阶段1：独立运行（无 Harness）
      graph = FlowGraph().compile()
      state = graph.execute(state)

      # 阶段2：带回调（低耦合对接 Harness）
      from engine.flow.callback import harness_sync_callback
      graph = FlowGraph().compile(callbacks=[harness_sync_callback])
      state = graph.execute(state)

      # 阶段2+：带 Checkpoint（断点恢复）
      graph = FlowGraph().compile(
          callbacks=[harness_sync_callback],
          checkpointer=SqliteCheckpointer(),
      )
      state = graph.execute(state, thread_id="ins_001")
    """

    def __init__(self):
        self.nodes: dict[str, NodeFn] = {}
        self.linear_sequence: list[str] = []
        self.conditional_routes: dict[str, str] = {}
        self.loop_nodes: dict[str, str] = {}
        self._compiled = False

        # 运行时组件（compile 时注入）
        self._callback_mgr: Optional[CallbackManager] = None
        self._checkpointer: Optional[SqliteCheckpointer] = None

    # ─── 图构建 ───────────────────────────────────────────────

    def register_node(self, key: str, node: NodeFn) -> "FlowGraph":
        self.nodes[key] = node
        return self

    def add_conditional(self, node_key: str, edge_name: str) -> "FlowGraph":
        self.conditional_routes[node_key] = edge_name
        return self

    def add_loop(self, loop_source: str, loop_handler: str) -> "FlowGraph":
        self.loop_nodes[loop_source] = loop_handler
        return self

    def compile(
        self,
        callbacks: Optional[list[SyncCallback]] = None,
        checkpointer: Optional[SqliteCheckpointer] = None,
    ) -> "FlowGraph":
        """
        编译图（不可逆，编译后只读）。

        Args:
            callbacks: Node 执行后触发的回调列表
                       None = 不启用外部同步（阶段1）
                       [harness_sync_callback] = 启用 Harness 同步（阶段2+）
            checkpointer: 本地 SQLite Checkpoint
                          None = 不启用断点（内存模式）
        """
        # 1. 注册所有节点
        for key, node_fn in ALL_NODES.items():
            self.register_node(key, node_fn)

        self.register_node("executor_smoke", lambda s: ALL_NODES["executor"](s, mode="smoke"))
        self.register_node("executor_full", lambda s: ALL_NODES["executor"](s, mode="full"))
        self.register_node("supervisor_pre", lambda s: ALL_NODES["supervisor"](s, audit_phase="pre"))
        self.register_node("supervisor_post", lambda s: ALL_NODES["supervisor"](s, audit_phase="post"))
        self.register_node("bug_fix", ALL_NODES["pm"])
        self.register_node("pm_confirm", ALL_NODES["pm_confirm"])  # PM确认节点

        # 2. 注册线性序列
        for from_key, to_key, _ in LINEAR_EDGES:
            if from_key not in self.linear_sequence:
                self.linear_sequence.append(from_key)
            if to_key not in self.linear_sequence:
                self.linear_sequence.append(to_key)

        # 3. 治理流程条件边
        self.add_conditional("gov_input", "rollback_route")
        self.add_conditional("gov_compress", "gov_compress_route")

        # 3.5 增量优化202607：SV 前置审计边（PM/SPM/DPM/FE/BE 节点前审计）
        sv_pre_audit_nodes = [
            ("sv_pre_pm", "sv_pre_pm"),
            ("sv_pre_spm", "sv_pre_spm"),
            ("sv_pre_dpm", "sv_pre_dpm"),
            ("sv_pre_fe", "sv_pre_fe"),
            ("sv_pre_be", "sv_pre_be"),
        ]
        for audited_node, edge_name in sv_pre_audit_nodes:
            self.register_node(audited_node, ALL_NODES["sv"])
            self.add_conditional(audited_node, edge_name)

        # 4. 原有业务条件边
        self.add_conditional("executor_smoke", "smoke_after")
        self.add_conditional("supervisor_pre", "supervisor_pre")
        self.add_conditional("executor_full", "full_after")
        self.add_conditional("supervisor_post", "supervisor_post")
        self.add_conditional("code_review", "code_review_after")
        self.add_conditional("ops", "deploy_after")
        self.add_conditional("qa", "acceptance_after")
        self.add_conditional("retro", "retro_after")
        self.add_conditional("sv", "sv_audit")

        # 5. Phase2 并行区间条件边
        self.add_conditional("parallel_dispatcher", "parallel_dispatcher_route")
        self.add_conditional("parallel_aggregator", "parallel_aggregator_route")

        # 6. 循环边
        self.add_loop("bug_fix", "bug_fix_loop")

        # 5. 回调管理器
        self._callback_mgr = CallbackManager(callbacks or [])

        # 6. Checkpointer
        self._checkpointer = checkpointer

        self._compiled = True
        return self

    # ─── 运行时 ───────────────────────────────────────────────

    def get_next_node(self, state: FlowState, current_key: str) -> tuple[Optional[str], str]:
        """从当前节点通过 Edge 条件路由获取下一节点"""
        # 1. 条件边
        if current_key in self.conditional_routes:
            edge_name = self.conditional_routes[current_key]
            edge_fn = CONDITIONAL_EDGES.get(edge_name)
            if edge_fn:
                _, next_key, reason = edge_fn(state)
                return next_key, reason

        # 2. 循环边
        if current_key in self.loop_nodes:
            loop_fn_name = self.loop_nodes[current_key]
            loop_fn = CONDITIONAL_EDGES.get(loop_fn_name)
            if loop_fn:
                _, next_key, reason = loop_fn(state)
                return next_key, reason

        # 3. 线性边
        next_key = get_linear_next(current_key)
        if next_key:
            return next_key, f"线性流转: {current_key} → {next_key}"

        return None, "流程结束（无后续节点）"

    def step(
        self,
        state: FlowState,
        current_node_key: str,
        thread_id: Optional[str] = None,
        skip_callbacks: bool = False,
        **node_kwargs,
    ) -> tuple[FlowState, Optional[str], str]:
        """
        单步执行一个 Node（无 DB 依赖，纯 State 操作）。

        返回 (new_state, next_node_key, reason)

        每步动作：
          1. 深拷贝 State（供 callback 差分使用）
          2. 执行 Node
          3. 保存本地 Checkpoint（如已配置）
          4. 触发回调（如已注册）
          5. Edge 条件路由 → 下一节点
        """
        if current_node_key not in self.nodes:
            raise ValueError(f"未知节点: {current_node_key}，请先 compile()")

        node_fn = self.nodes[current_node_key]

        # RETIRED-2026-08-17: 旧 orchestrator_gate 门控已退役，节点门禁由节点侧 ET 组装 Payload 调 kernel.et() 承接（见 docs/HANDOFF_engine_et.md §5-3）。
        # 原 L1 调度层硬规则前置门禁（OrchestratorGate.check_entry，USE_LAYERED_RULES 开关下）已移除。
        # P0 回填（2026-08-17，分身C，docs/reform_gate_blocks/block1_gate_vacuum.md）：
        # NodeGateET 前置三门（前置交付物 + 状态机跃迁 + SV 审批），规则源 config/node_gates.yaml；
        # 无规则节点跳过；拦截（code != success）按既有失败范式冻结流程，禁止静默吞 block。
        pre_gate_out = get_node_gate().run_pre({
            "channel": "graph",
            "node": current_node_key,
            "from_state": getattr(state.current_status, "value", state.current_status),
            "sv_verdict": state.metadata.get("sv_verdict") or state.task_meta.get("sv_verdict"),
            "project_root": state.task_meta.get("project_root"),
            "trace_id": (
                f"nodegate-{state.instance_id}-{current_node_key}"
                f"-pre-{len(state.execution_trace)}"
            ),
        })
        if pre_gate_out is not None and pre_gate_out.get("code") != "success":
            err_msg = "节点前置门禁拦截 [{}]: {}".format(
                current_node_key,
                (pre_gate_out.get("failure_info") or {}).get(
                    "error_msg", pre_gate_out.get("code")),
            )
            logger.warning(err_msg)
            state.is_frozen = True
            state.freeze_reason = err_msg
            state.record_node_execution(NodeType.PM, "failed", error=err_msg)
            if self._checkpointer:
                self._checkpointer.save(
                    state, node_key=current_node_key,
                    task_title=state.project_name,
                    task_status="frozen",
                    thread_id=thread_id,
                )
            return state, "frozen", err_msg

        # 1. 快照执行前状态（供 callback 差分使用）
        state_before = state.model_copy(deep=True)

        # 2. 执行 Node
        try:
            new_state, routing_key = node_fn(state, **node_kwargs)
        except Exception as e:
            state.record_node_execution(
                NodeType.PM, "failed",
                error=f"Node [{current_node_key}] 异常: {e}",
            )
            logger.error("Node [%s] 异常: %s", current_node_key, e)
            # 异常自动快照：记录故障状态
            if self._checkpointer:
                self._checkpointer.save(
                    state, node_key=current_node_key,
                    task_title=state.project_name,
                    task_status="error",
                    thread_id=thread_id,
                )
            return state, "frozen", f"Node 异常: {e}"

        # RETIRED-2026-08-17: 旧 orchestrator_gate 门控已退役，节点门禁由节点侧 ET 组装 Payload 调 kernel.et() 承接（见 docs/HANDOFF_engine_et.md §5-3）。
        # 原执行链路内嵌 SupervisorGuard 三道实时校验（①validate_flow_transition 状态转换合法性 /
        # ②check_deliverable_gate 交付物门禁 / ③check_violation_gate 违规积分熔断）
        # 与 L3 后置硬规则（OrchestratorGate.check_output + validate_deliverable_state）已一并移除。
        # P0 回填（2026-08-17，分身C）：NodeGateET 后置门（L3：本节点应产出交付物存在性 +
        # 实际跃迁 (from→to) 合法性）；无规则/无启用钩子节点跳过；拦截按既有失败范式冻结。
        post_gate_out = get_node_gate().run_post({
            "channel": "graph",
            "node": current_node_key,
            "from_state": getattr(state.current_status, "value", state.current_status),
            "to_state": getattr(new_state.current_status, "value", new_state.current_status),
            "project_root": new_state.task_meta.get("project_root"),
            "trace_id": (
                f"nodegate-{state.instance_id}-{current_node_key}"
                f"-post-{len(new_state.execution_trace)}"
            ),
        })
        if post_gate_out is not None and post_gate_out.get("code") != "success":
            err_msg = "节点后置门禁拦截 [{}]: {}".format(
                current_node_key,
                (post_gate_out.get("failure_info") or {}).get(
                    "error_msg", post_gate_out.get("code")),
            )
            logger.warning(err_msg)
            new_state.is_frozen = True
            new_state.freeze_reason = err_msg
            new_state.record_node_execution(NodeType.PM, "failed", error=err_msg)
            if self._checkpointer:
                self._checkpointer.save(
                    new_state, node_key=current_node_key,
                    task_title=new_state.project_name,
                    task_status="frozen",
                    thread_id=thread_id,
                )
            return new_state, "frozen", err_msg

        # 3. 保存本地 Checkpoint（第一优先级写入，自动生成 snap_id）
        if self._checkpointer:
            snap_id = self._checkpointer.save(
                new_state, node_key=current_node_key,
                task_title=state.project_name,
                task_status=state.current_status.value,
                thread_id=thread_id,
            )
            if snap_id:
                logger.debug("Step checkpoint: thread=%s snap=%s node=%s",
                             new_state.instance_id, snap_id, current_node_key)

        # 4. 触发回调（第二优先级写入，失败不阻塞）
        if self._callback_mgr and not skip_callbacks:
            try:
                self._callback_mgr.trigger(
                    state_before, new_state, current_node_key, node_kwargs,
                )
            except Exception as cb_err:
                err_msg = f"回调同步失败: {cb_err}"
                logger.error("回调阻断: %s", err_msg)

                # 如果已冻结（Guard 熔断已触发）→ 不重复处理
                if new_state.is_frozen:
                    return new_state, "frozen", err_msg

                # 未冻结 → 同步失败时冻结流程（不额外加违规，Guard 已处理）
                new_state.is_frozen = True
                new_state.freeze_reason = err_msg
                new_state.record_node_execution(
                    NodeType.PM, "failed",
                    error=err_msg,
                )
                if self._checkpointer:
                    self._checkpointer.save(
                        new_state, node_key=current_node_key,
                        task_title=new_state.project_name,
                        task_status="frozen",
                        thread_id=thread_id,
                    )
                return new_state, "frozen", err_msg

        # 5. Edge 条件路由
        next_key, reason = self.get_next_node(new_state, current_node_key)

        # Node 显式 routing_key 覆盖 Edge 结果
        if routing_key:
            next_key = routing_key
            reason = f"Node 显式路由: {current_node_key} → {routing_key}"

        return new_state, next_key, reason

    def execute(
        self,
        state: FlowState,
        start_node: str = "pm",
        max_steps: int = 50,
        thread_id: Optional[str] = None,
    ) -> FlowState:
        """
        完整执行所有节点直到 __end__ 或冻结。

        Args:
            state: 初始 FlowState
            start_node: 起始节点 key
            max_steps: 最大执行步数（防死循环）
            thread_id: Checkpoint 恢复用 thread_id（如已配置 checkpointer）

        Returns:
            执行结束后的 FlowState
        """
        if not self._compiled:
            raise RuntimeError("Graph 未编译，请先调用 compile()")

        # Checkpoint 断点恢复
        if thread_id and self._checkpointer:
            checkpoint = self._checkpointer.load(thread_id)
            if checkpoint:
                logger.info("从 Checkpoint 恢复 [%s] status=%s", thread_id, checkpoint.current_status.value)
                state = checkpoint
                # 从 Checkpoint 保存的 node_key 恢复
                # 实际 node_key 通过 metadata 记录

        # 执行开始时自动打基线快照（标记任务启动）
        if thread_id and self._checkpointer:
            self._checkpointer.save(
                state, node_key="exec_start",
                task_title=state.project_name,
                task_status="running",
            )

        current_key = start_node
        step_count = 0

        while current_key and current_key != "__end__" and step_count < max_steps:
            step_count += 1

            if state.is_frozen:
                logger.warning("流程已冻结（第 %d 步），原因: %s", step_count, state.freeze_reason)
                state.error_log.append(f"流程已冻结（第 {step_count} 步），原因: {state.freeze_reason}")
                break

            state, next_key, reason = self.step(state, current_key, thread_id=thread_id)

            if next_key == "frozen":
                logger.warning("流程冻结于第 %d 步: %s", step_count, reason)
                state.error_log.append(f"流程冻结于第 {step_count} 步: {reason}")
                break

            current_key = next_key

        if step_count >= max_steps:
            state.error_log.append(f"达到最大执行步数 {max_steps}，流程强制暂停")

        # 场景 1: flow_finish — 会话正常执行完成所有节点后自动基线快照
        if current_key == "__end__" and not state.is_frozen and step_count < max_steps:
            try:
                from engine.flow.checkpoint import auto_create_baseline_snapshot
                auto_create_baseline_snapshot(
                    state.instance_id,
                    memo_suffix="会话完整执行完成",
                    task_status="finished",
                    state=state,
                )
            except Exception as e:
                logger.warning("flow_finish 自动基线快照失败: %s", e)

        return state

    # ─── 查询 ────────────────────────────────────────────────

    def get_execution_plan(self) -> list[str]:
        """获取执行计划（节点顺序）"""
        return list(dict.fromkeys(
            from_key for from_key, to_key, _ in LINEAR_EDGES
        ))

    @property
    def callback_count(self) -> int:
        return self._callback_mgr.count if self._callback_mgr else 0

    @property
    def has_checkpointer(self) -> bool:
        return self._checkpointer is not None

    @property
    def has_governance(self) -> bool:
        """是否已注册治理子图节点"""
        return "gov_input" in self.nodes

    def execute_branch(
        self,
        node_key: str,
        state: FlowState,
        thread_id: str,
    ) -> FlowState:
        """
        执行单个分支节点，使用独立 thread_id 保存 checkpoint，但保留主 instance_id 用于回调。

        Args:
            node_key: 要执行的分支节点 key
            state: 分支 State 副本
            thread_id: 分支 checkpoint thread_id（通常 {instance_id}_{node_key}）
        Returns:
            执行后的 State
        """
        if not self._compiled:
            raise RuntimeError("Graph 未编译，请先调用 compile()")
        if node_key not in self.nodes:
            raise ValueError(f"未知分支节点: {node_key}")

        new_state, next_key, reason = self.step(
            state, node_key, thread_id=thread_id
        )
        logger.info(
            "分支执行完成: node=%s thread=%s next=%s reason=%s",
            node_key, thread_id, next_key, reason,
        )
        return new_state

    def execute_with_governance(
        self,
        state: FlowState,
        max_steps: int = 50,
        thread_id: Optional[str] = None,
    ) -> FlowState:
        """
        从治理子图开始完整执行（治理 → 业务流程）。
        治理子图自动处理回滚分流、长文本检测，结束后按 need_deepseek_forward 路由到 pm 或结束。
        """
        return self.execute(
            state=state,
            start_node="gov_input",
            max_steps=max_steps,
            thread_id=thread_id,
        )


# ═══════════════════════════════════════════════════════════════
# 单例
# ═══════════════════════════════════════════════════════════════

_compiled_graph: Optional[FlowGraph] = None


def get_flow_graph(
    callbacks: Optional[list[SyncCallback]] = None,
    checkpointer: Optional[SqliteCheckpointer] = None,
) -> FlowGraph:
    """
    获取全局编译后的流程图（单例）。

    首次调用时注册回调。
    后续调用忽略 callbacks/checkpointer 参数（单例已固定）。
    """
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = FlowGraph().compile(
            callbacks=callbacks,
            checkpointer=checkpointer,
        )
    return _compiled_graph
