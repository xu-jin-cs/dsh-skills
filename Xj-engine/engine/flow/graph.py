# ══════════════════════════════════════════════════════════════════════
# 【过渡组件 · TRANSITIONAL】2026-09-13 用户裁定：
#   本模块（langgraph FlowGraph 平迁版）暂任 Xj-Frame 图编排内核。
#   待 Xj-engine 补足图拓扑短板（depends_on 拓扑/动态并行/checkpoint 断点）后
#   整体替换本模块——替换点=本包全部节点/边/图执行调用方。
#   新代码引用本包时请注意此替换预期，编排逻辑尽量走 FlowNodeMeta 声明式。
# ══════════════════════════════════════════════════════════════════════
"""
Flow Graph — 组合 Nodes + Edges 的可执行图（2026-09-13 自 langgraph FlowGraph 平迁）。

设计（来自全局融合方案）：
  FlowGraph 定位：实时任务运行内核（自研，零框架依赖）
  agent-harness 定位：宿主镜像存证与可视化（可选平台，非引擎）

数据写入顺序保障：
  1. Node 执行（纯 State 操作，无 DB 依赖）
  2. 保存本地 Checkpoint（第一优先级）
  3. 触发回调（第二优先级，失败不阻塞）

融合后完整数据流转（2026-11-17 headless 执行通道废除后）：
  编译器 build_flow_graph() 注册 stage/fanout 节点 → FlowGraph.execute()
    ├─ checkpoint.load() — 断点恢复（如存在）
    ├─ Node 循环：
    │   ├─ step() — 执行 Node → 检查 Edge
    │   └─ checkpoint.save() — 本地持久化
    └─ 完成 → 状态经宿主通道（state_wiring / audit）上报
  历史 callback→Harness HTTP 上报件已随 headless 通道废除（见 CHANGES.md 2026-11-17）
"""

import copy
import logging
from typing import Any, Callable, Optional

from engine.flow.state import FlowState, FlowStatus, NodeType
from engine.flow.edges import (
    CONDITIONAL_EDGES, get_linear_next,
)
from engine.flow.checkpoint import (
    SqliteCheckpointer, get_checkpointer,
)
from engine.flow.integration import (
    state_to_json,
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

logger = logging.getLogger(__name__)

# 节点函数签名（原 nodes.py 定义，2026-11-17 headless 通道废除后本地重定义）
NodeFn = Callable[[FlowState], tuple[FlowState, Optional[str]]]


class FlowGraph:
    """
    完整流程图。

    使用方法（2026-11-17 起：无内置节点体，节点经 register_node 显式注册）：
      # 通用路径：workflow_compiler.build_flow_graph() 组装 stage/fanout 节点后执行
      graph = build_flow_graph(compiled, artifacts_root, plugin_bin, runner)
      state = graph.execute(build_initial_state(...), thread_id="ins_001")

      # 历史 PM 全流程编译图（compile()）已随 headless 通道废除（2026-11-17）
    """

    def __init__(self):
        self.nodes: dict[str, NodeFn] = {}
        self.linear_sequence: list[str] = []
        self.conditional_routes: dict[str, str] = {}
        self.loop_nodes: dict[str, str] = {}
        self._compiled = False

        # 运行时组件（构建时注入）
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
        **node_kwargs,
    ) -> tuple[FlowState, Optional[str], str]:
        """
        单步执行一个 Node（无 DB 依赖，纯 State 操作）。

        返回 (new_state, next_node_key, reason)

        每步动作：
          1. 深拷贝 State
          2. 执行 Node
          3. 保存本地 Checkpoint（如已配置）
          4. Edge 条件路由 → 下一节点
        """
        if current_node_key not in self.nodes:
            raise ValueError(f"未知节点: {current_node_key}，请先 register_node 注册该节点")

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

        # 4. Edge 条件路由
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

    @property
    def has_checkpointer(self) -> bool:
        return self._checkpointer is not None

    @property
    def has_governance(self) -> bool:
        """是否已注册治理子图节点"""
        return "gov_input" in self.nodes

    def judge_parallel_fanout(self, branch_keys: list[str]) -> dict:
        """动态并行判定接线（2026-09-13 用户裁定：并行判定复用 dispatch_switch 闸）。

        分支数 >1 时先扳 parallel-dispatch 的 dispatch_switch 机械判定
        （母体可控时机 DIM-031——判定权在闸，执行权在引擎）；
        闸不可用/路径缺失时降级为本地并行放行并 WARN 留痕（不阻断图执行）。
        返回 {"verdict": "parallel"|"serial"|"degraded", "via": ..., "detail": ...}。
        """
        if len(branch_keys) <= 1:
            return {"verdict": "serial", "via": "engine.flow.graph", "detail": "单分支无需并行判定"}
        import os
        import subprocess
        switch = os.path.expanduser(
            "~/.agents/skills/parallel-dispatch/scripts/dispatch_switch.py")
        if not os.path.isfile(switch):
            logger.warning("dispatch_switch 不在 %s——降级本地并行放行（WARN 留痕）", switch)
            return {"verdict": "degraded", "via": "engine.flow.graph", "detail": "闸脚本缺失"}
        try:
            r = subprocess.run(
                ["python3", switch, "--files", str(len(branch_keys)),
                 "--units", str(len(branch_keys)),
                 "--desc", f"Xj-flow 并行分支判定: {','.join(branch_keys[:8])}"],
                capture_output=True, text=True, timeout=60)
            verdict = "parallel" if r.returncode == 0 else "serial"
            return {"verdict": verdict, "via": f"dispatch_switch(exit={r.returncode})",
                    "detail": (r.stdout or r.stderr)[-300:]}
        except Exception as exc:  # noqa: BLE001
            logger.warning("dispatch_switch 扳动异常，降级本地并行放行: %s", exc)
            return {"verdict": "degraded", "via": "engine.flow.graph", "detail": str(exc)}

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


# ═══════════════════════════════════════════════════════════════
# 说明（2026-11-17）：原模块级单例 get_flow_graph() 已随 headless
# 通道废除移除——全局编译图不再存在，图一律由 build_flow_graph() 按次构建。
# ═══════════════════════════════════════════════════════════════
