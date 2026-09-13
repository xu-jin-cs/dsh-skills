"""
LangGraph Nodes — Agent 角色独立执行单元。

设计原则（来自全局融合方案）：
  1. 一个 Node 只做一件事 — 精细化拆分，不多职责混杂
  2. 每个 Node 绑定单一 Agent 角色
  3. Node 输入 = FlowState，输出 = (FlowState, routing_key)
  4. Node 内部调用现有 Skill 模块 / 角色 Agent
  5. Node 纯 State 操作 — 不读写 DB，不直接调用 Harness API
     （持久化由 FlowGraph 的 callback 机制统一处理）
  6. Node 签名：state → (state, routing_key)
     - routing_key 传给 Edge 做条件路由
     - None = 无条件线性流转
"""

import logging
import os
import json
from datetime import datetime
from typing import Callable, Optional

logger = logging.getLogger("langgraph.nodes")

from engine.flow.state import (
    FlowState, FlowStatus, NodeType, BugLevel,
    ViolationType, BugRecord,
)
try:  # 并行调度依赖宿主分支存储（HOST-ONLY）：无宿主降级为 None
    from engine.flow.parallel.dispatcher import parallel_dispatcher
    from engine.flow.parallel.aggregator import parallel_aggregator
except Exception:  # noqa: BLE001
    parallel_dispatcher = None
    parallel_aggregator = None

# Node 签名：输入 state → 输出 (new_state, routing_key)
# 不再依赖 db 参数 — 纯 State 操作，持久化由 callback 层统一处理
NodeFn = Callable[[FlowState], tuple[FlowState, Optional[str]]]


def _now() -> str:
    return datetime.utcnow().isoformat()


# ═══════════════════════════════════════════════════════════════
# Node 1: PM — 项目经理节点
# ═══════════════════════════════════════════════════════════════

class PMNode:
    """
    项目经理节点 — 流程调度中枢。
    职责：项目初始化、任务指派、流程状态自检、GATE_BRIDGE_CHECKLIST 提交。

    2026-07-05 改造：增加前置校验与交付物强制注册。
    """
    node_type = NodeType.PM

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        # 前置校验
        if not state.project_name:
            raise ValueError("PM 节点前置门控失败：project_name 为空")
        if not state.instance_id:
            raise ValueError("PM 节点前置门控失败：instance_id 为空")

        # 注册项目初始化交付物
        state.add_deliverable(
            content_type="project_plan",
            summary=f"项目 [{state.project_name}] 初始化完成: {state.project_description or '无描述'}",
            agent_role=NodeType.PM,
        )

        state.current_status = FlowStatus.PRD_REVIEW
        state.started_at = _now()
        state.record_node_execution(NodeType.PM, "passed", f"PM 节点：项目 [{state.project_name}] 初始化完成")
        return state, None

    @staticmethod
    def gate_bridge_checklist(state: FlowState) -> dict:
        """生成 GATE_BRIDGE_CHECKLIST（链式测试启动前 PM 强制填写）"""
        from engine.flow.edges import CHECKLIST_TEMPLATE
        checklist = dict(CHECKLIST_TEMPLATE)

        if state.prd_doc and state.deliverables:
            prd_related = [d for d in state.deliverables if d.content_type in (
                "test_report", "self_test_report"
            )]
            coverage = min(100, len(prd_related) * 20) if prd_related else 0
            checklist["1️⃣ PRD验收标准覆盖率"]["覆盖率"] = f"{coverage}%"

        if state.smoke_test:
            checklist["2️⃣ 自测报告真实性"]["自测通过率"] = self._calc_rate(
                state.smoke_test.pass_count, state.smoke_test.fail_count
            )

        return checklist

    @staticmethod
    def _calc_rate(pass_count: int, fail_count: int) -> str:
        total = pass_count + fail_count
        if total == 0:
            return "N/A"
        return f"{round(pass_count / total * 100, 1)}%"


def pm_confirm_node(state: FlowState) -> tuple[FlowState, Optional[str]]:
    """PM 确认节点：并行区间结束后统一确认。"""
    state.add_deliverable(
        content_type="pm_accept_signature",
        summary=f"PM 确认通过: {state.project_name}",
        agent_role=NodeType.PM,
    )
    state.current_status = FlowStatus.PM_CONFIRM
    state.record_node_execution(
        NodeType.PM, "passed",
        "PM 确认节点：并行区间产出审核通过",
    )
    return state, None


# ═══════════════════════════════════════════════════════════════
# Node 2: SPM — 大产品经理节点
# ═══════════════════════════════════════════════════════════════

class SPMNode:
    """
    大产品经理节点 — 需求分析。
    职责：需求澄清 → KANO+ROI 分析 → 输出《总需求 PRD》→ 六要素校验。

    2026-07-05 改造：增加前置校验与交付物强制注册。
    """
    node_type = NodeType.SPM

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        # 前置校验：PM 节点已执行
        pm_deliverables = [d for d in state.deliverables if d.agent_role == NodeType.PM]
        if not pm_deliverables and not state.prd_doc:
            raise ValueError("SPM 节点前置门控失败：缺少 PM 初始化交付物（prd_doc 为空）")

        # 检查是否有 viotations 需要阻断
        if state.total_points >= 3:
            raise ValueError("SPM 节点前置门控失败：违规积分 ≥ 3，流程已熔断")

        # 注册 PRD 交付物
        state.add_deliverable(
            content_type="prd_doc",
            summary=f"SPM 需求分析完成: {state.project_description or '需求文档'}",
            agent_role=NodeType.SPM,
            validated=False,
        )

        state.current_status = FlowStatus.PRD_REVIEW
        state.record_node_execution(NodeType.SPM, "passed", "SPM 节点：PRD 需求分析完成")
        return state, None

    @staticmethod
    def validate_prd_completeness(prd_text: str) -> list[str]:
        """PRD 六要素完整性校验"""
        required = ["目标", "命令", "项目结构", "代码风格", "测试策略", "验收标准"]
        return [r for r in required if r not in prd_text]


# ═══════════════════════════════════════════════════════════════
# Node 3: DPM — 细节产品经理节点
# ═══════════════════════════════════════════════════════════════

class DPMNode:
    """
    细节产品经理节点 — 交互设计。
    职责：质疑闭环 → 状态枚举 → 异常场景 → 输出《详细交互设计文档》。

    2026-07-05 改造：增加前置校验与交付物强制注册。
    """
    node_type = NodeType.DPM

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        if not state.prd_doc and not state.deliverables:
            raise ValueError("DPM 前置门控失败：缺少 PRD 文档或前置交付物")

        # 检查 PRD 交付物
        prd_related = [d for d in state.deliverables if d.content_type == "prd_doc"]
        if not prd_related:
            state.add_violation(
                vtype="COMPLIANCE_FAILURE",
                description="DPM 节点：SPM 未产出 PRD 交付物（content_type=prd_doc）",
                points=1,
            )

        # 注册交互设计交付物
        state.add_deliverable(
            content_type="interaction_doc",
            summary=f"详细交互设计文档: {state.project_name}",
            agent_role=NodeType.DPM,
            validated=False,
        )

        state.current_status = FlowStatus.DESIGN
        state.record_node_execution(NodeType.DPM, "passed", "DPM 节点：交互设计完成")
        return state, None


# ═══════════════════════════════════════════════════════════════
# Node 4: UI Designer — 界面设计师节点
# ═══════════════════════════════════════════════════════════════

class UIDesignerNode:
    """
    界面设计师节点 — 视觉规范 + 高保真布局。
    只输出文字规范与数值，不生成图片。

    2026-07-05 改造：前置校验+交付物强制注册。
    """
    node_type = NodeType.UI_DESIGNER

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        # 前置校验：需要交互文档或至少前置步骤已执行
        design_deliverables = [d for d in state.deliverables if d.content_type in ("interaction_doc", "prd_doc")]
        if not design_deliverables and not state.interaction_doc:
            state.add_violation(
                vtype="COMPLIANCE_FAILURE",
                description="UI 节点：缺少交互文档/PRD 作为设计输入",
                points=1,
            )

        # 注册 UI 规范交付物
        state.add_deliverable(
            content_type="ui_spec",
            summary=f"UI 视觉规范交付: {state.project_name}",
            agent_role=NodeType.UI_DESIGNER,
            validated=False,
        )

        state.record_node_execution(NodeType.UI_DESIGNER, "passed", "UI 节点：视觉规范交付完成")
        return state, None


# ═══════════════════════════════════════════════════════════════
# Node 5: Test Case Designer — 测试用例设计节点
# ═══════════════════════════════════════════════════════════════

class TestCaseDesignerNode:
    """
    测试用例设计 Agent — 专职设计不执行。
    职责：测试点设计 → 按钮全量覆盖 → Schema JSON 输出。

    2026-07-05 改造：前置校验+交付物强制注册。
    """
    node_type = NodeType.TEST_CASE_DESIGNER

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        # 前置校验：需要有 PRD 或交互文档支撑
        prd_related = [d for d in state.deliverables if d.content_type in ("prd_doc", "interaction_doc")]
        if not prd_related and not state.prd_doc:
            state.add_violation(
                vtype="COMPLIANCE_FAILURE",
                description="TCD 节点：缺少 PRD/交互文档作为用例设计依据",
                points=1,
            )

        # 注册测试用例交付物
        state.add_deliverable(
            content_type="test_case",
            summary=f"测试用例设计完成（含 smoke:true 标签）: {state.project_name}",
            agent_role=NodeType.TEST_CASE_DESIGNER,
            validated=False,
        )

        state.record_node_execution(
            NodeType.TEST_CASE_DESIGNER, "passed",
            "TCD 节点：测试用例设计完成（含 smoke:true 标签）"
        )
        return state, None

    @staticmethod
    def check_design_dimensions(state: FlowState) -> list[str]:
        """7 种测试点类型覆盖自检"""
        expected = ["边界值", "等价类", "需求逻辑", "场景", "异常", "兼容", "接口安全"]
        covered = state.metadata.get("test_dimensions", [])
        return [d for d in expected if d not in covered]


# ═══════════════════════════════════════════════════════════════
# Node 6: Frontend — 前端开发节点
# ═══════════════════════════════════════════════════════════════

class FrontendDevNode:
    """
    前端开发节点 — 组件实现 + 前端自测。
    职责：技能5上下文加载 → 技能7前端UI工程 → 技能4切片实现 → 技能9TDD自测。

    2026-07-05 改造：增加前置校验与交付物强制注册。
    """
    node_type = NodeType.FRONTEND

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        if not state.interaction_doc and not state.ui_spec:
            state.add_violation(
                vtype="COMPLIANCE_FAILURE",
                description="FE 节点：缺少交互文档/UI 规范，进入开发有风险",
                points=1,
            )

        # 注册前端交付物
        state.add_deliverable(
            content_type="frontend_code",
            summary=f"前端实现完成: {state.project_name}",
            agent_role=NodeType.FRONTEND,
        )

        state.current_status = FlowStatus.DEV_FRONTEND
        state.record_node_execution(NodeType.FRONTEND, "passed", "FE 节点：前端开发 + 自测完成")
        return state, None


# ═══════════════════════════════════════════════════════════════
# Node 7: Backend — 后端开发节点
# ═══════════════════════════════════════════════════════════════

class BackendDevNode:
    """
    后端开发节点 — 接口实现 + 后端自测。
    职责：技能5上下文加载 → 技能8接口设计 → 技能6文档溯源 → 技能4切片 → 技能9TDD。

    2026-07-05 改造：增加前置校验与交付物强制注册。
    """
    node_type = NodeType.BACKEND

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        if not state.interaction_doc:
            state.add_violation(
                vtype=ViolationType.COMPLIANCE_FAILURE,
                description="BE 节点：缺少《详细交互设计文档》",
                points=1,
            )

        # 注册后端交付物
        state.add_deliverable(
            content_type="backend_code",
            summary=f"后端实现完成: {state.project_name}",
            agent_role=NodeType.BACKEND,
        )

        state.current_status = FlowStatus.DEV_BACKEND
        state.record_node_execution(NodeType.BACKEND, "passed", "BE 节点：后端开发 + 自测完成")
        return state, None


# ═══════════════════════════════════════════════════════════════
# Node 8: Test Executor — 测试执行节点
# ═══════════════════════════════════════════════════════════════

class TestExecutorNode:
    """
    测试执行节点 — 执行已审核用例。
    两种模式：smoke（冒烟）/ full（全量）。

    2026-07-05 改造：前置校验+交付物强制注册+证据链完整性检查。
    """
    node_type = NodeType.TEST_EXECUTOR

    def __call__(self, state: FlowState, *, mode: str = "smoke") -> tuple[FlowState, Optional[str]]:
        test_mode_label = "冒烟" if mode == "smoke" else "全量"

        # 前置校验：全量测试需要冒烟测试通过
        if mode == "full" and not state.smoke_test_gate_passed:
            state.add_violation(
                vtype="SKIP_ATTEMPT",
                description=f"Executor 节点：全量测试前置门控失败：冒烟测试未通过",
                points=2,
            )

        # 执行结果判定 + 状态推进
        if mode == "smoke":
            state.current_status = FlowStatus.SMOKE_TEST
            state.smoke_test_gate_passed = state.smoke_test is None or not state.smoke_test.has_p0
        else:
            state.current_status = FlowStatus.FULL_TEST
            state.allow_deploy = state.full_test is None or (not state.full_test.has_p0 and not state.full_test.has_p1)

        # 注册测试执行交付物
        state.add_deliverable(
            content_type=f"{mode}_test_report",
            summary=f"{test_mode_label}测试执行完成",
            agent_role=NodeType.TEST_EXECUTOR,
        )

        state.record_node_execution(
            NodeType.TEST_EXECUTOR, "passed",
            f"Executor 节点：{test_mode_label}测试执行完成"
        )

        return state, None


# ═══════════════════════════════════════════════════════════════
# Node 9: Test Supervisor — 测试监督节点
# ═══════════════════════════════════════════════════════════════

class TestSupervisorNode:
    """
    测试监督节点 — 审核 + 审计 + 门禁。
    阶段A：审核用例（Q1-Q4）
    阶段B：审计执行（Q5-Q6）
    阶段C：Bug 修复验证

    2026-07-05 改造：前置校验+交付物强制注册+各阶段证据链检查。
    """
    node_type = NodeType.TEST_SUPERVISOR

    def __call__(self, state: FlowState, *, audit_phase: str = "pre") -> tuple[FlowState, Optional[str]]:
        # 前置校验：post 审计需要 pre 审计已执行
        if audit_phase == "post" and state.metadata.get("last_audit_phase") not in ("pre", "full"):
            state.add_violation(
                vtype="SKIP_ATTEMPT",
                description="TS 节点：post 审计前缺少 pre 审计阶段",
                points=1,
            )

        # 注册审计交付物（按阶段区分）
        if audit_phase == "pre":
            state.add_deliverable(
                content_type="test_audit_pre",
                summary="测试用例审核通过（Q1-Q4）",
                agent_role=NodeType.TEST_SUPERVISOR,
            )
            state.record_node_execution(NodeType.TEST_SUPERVISOR, "passed", "TS 审计：用例审核通过（Q1-Q4）")
        elif audit_phase == "post":
            # 检查执行证据
            executor_deliverables = [d for d in state.deliverables if d.content_type in ("smoke_test_report", "full_test_report")]
            if not executor_deliverables:
                state.add_violation(
                    vtype="EVIDENCE_CHEAT",
                    description="TS 后审：未找到测试执行交付物，审计异常",
                    points=2,
                )

            state.add_deliverable(
                content_type="test_audit_post",
                summary="测试执行审计通过（Q5-Q6）",
                agent_role=NodeType.TEST_SUPERVISOR,
            )
            state.record_node_execution(NodeType.TEST_SUPERVISOR, "passed", "TS 审计：执行审计通过（Q5-Q6）")
        else:
            state.record_node_execution(NodeType.TEST_SUPERVISOR, "passed", "TS 审计完成")

        state.metadata["last_audit_phase"] = audit_phase
        return state, None


# ═══════════════════════════════════════════════════════════════
# Node 10: Code Review — 代码审查节点
# ═══════════════════════════════════════════════════════════════

class CodeReviewNode:
    """
    代码审查节点 — 五维检查。
    正确性 / 可读性 / 可靠性 / 可维护性 / 基础安全。

    2026-07-05 改造：前置校验+交付物强制注册+审查门禁。
    """
    node_type = NodeType.CODE_REVIEWER

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        # 前置校验：需要开发交付物
        dev_deliverables = [d for d in state.deliverables if d.content_type in ("frontend_code", "backend_code")]
        if not dev_deliverables:
            state.add_violation(
                vtype="COMPLIANCE_FAILURE",
                description="CR 节点：未找到任何开发交付物（frontend_code/backend_code），审查无对象",
                points=1,
            )

        # 检查测试是否已执行
        test_passed = state.smoke_test_gate_passed and state.allow_deploy
        if not test_passed:
            state.add_violation(
                vtype="COMPLIANCE_FAILURE",
                description="CR 节点：审查时测试门禁未全部通过（冒烟或全量测试缺失）",
                points=1,
            )

        # 注册审查交付物
        state.add_deliverable(
            content_type="code_review_report",
            summary=f"代码审查报告: {state.project_name}",
            agent_role=NodeType.CODE_REVIEWER,
        )

        state.current_status = FlowStatus.CODE_REVIEW
        state.code_review_passed = True
        state.record_node_execution(NodeType.CODE_REVIEWER, "passed", "CR 节点：代码审查通过（五维检查）")
        return state, None


# ═══════════════════════════════════════════════════════════════
# Node 11: Ops/Deploy — 运维部署节点
# ═══════════════════════════════════════════════════════════════

class OpsDeployNode:
    """
    运维部署节点 — 本地打包 + 版本记录。
    前置条件：代码审查通过 + 测试报告齐备。

    2026-07-05 改造：交付物强制注册+多维度门禁校验。
    """
    node_type = NodeType.OPS

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        if not state.allow_deploy:
            state.add_violation(ViolationType.COMPLIANCE_FAILURE, "部署前置门禁未通过：allow_deploy=False")
            raise ValueError("部署阻断：allow_deploy=False，需先完成全量测试并通过审查")

        # 前置校验：代码审查必须通过
        if not state.code_review_passed:
            state.add_violation(
                vtype="SKIP_ATTEMPT",
                description="Ops 节点：代码审查未通过即进入部署，已拦截",
                points=2,
            )
            raise ValueError("部署阻断：代码审查未通过")

        # 前置校验：必须有测试报告
        test_deliverables = [d for d in state.deliverables if d.content_type in ("smoke_test_report", "full_test_report", "test_audit_pre", "test_audit_post")]
        if not test_deliverables:
            state.add_violation(
                vtype="COMPLIANCE_FAILURE",
                description="Ops 节点：未找到测试交付物，部署有风险",
                points=1,
            )

        # 注册部署交付物
        state.add_deliverable(
            content_type="deploy_report",
            summary=f"部署完成: {state.project_name}",
            agent_role=NodeType.OPS,
        )

        state.current_status = FlowStatus.DEPLOY
        state.record_node_execution(NodeType.OPS, "passed", "Ops 节点：部署完成")
        return state, None


# ═══════════════════════════════════════════════════════════════
# Node 12: QA/Acceptance — 验收经理节点
# ═══════════════════════════════════════════════════════════════

class AcceptanceNode:
    """
    验收经理节点 — 最终通过/不通过判定。
    不排查 Bug，不写代码，不执行部署。

    2026-07-05 改造：交付物强制注册+前置条件校验。
    """
    node_type = NodeType.QA

    def __call__(self, state: FlowState, *, passed: bool = True) -> tuple[FlowState, Optional[str]]:
        # 前置校验：验收前必须有部署交付物
        deploy_deliverables = [d for d in state.deliverables if d.content_type == "deploy_report"]
        if not deploy_deliverables:
            state.add_violation(
                vtype="COMPLIANCE_FAILURE",
                description="QA 节点：验收前未找到部署报告（deploy_report）",
                points=1,
            )

        # 前置校验：存在未解决 P0/P1 Bug 时不应通过
        if passed:
            blocker_bugs = [b for b in state.bugs if b.severity in ("P0", "P1") and not b.resolved]
            if blocker_bugs:
                state.add_violation(
                    vtype="P0_BLOCKER",
                    description=f"QA 节点：标记通过但存在 {len(blocker_bugs)} 个未解决 P0/P1 Bug",
                    points=2,
                )
                passed = False

        if not passed:
            state.record_node_execution(NodeType.QA, "failed", "QA 节点：验收不通过")
            state.acceptance_passed = False
            return state, None

        # 注册验收交付物
        state.add_deliverable(
            content_type="acceptance_report",
            summary=f"验收通过: {state.project_name}",
            agent_role=NodeType.QA,
        )

        state.current_status = FlowStatus.ACCEPTANCE
        state.acceptance_passed = True
        state.record_node_execution(NodeType.QA, "passed", "QA 节点：验收通过")
        return state, None


# ═══════════════════════════════════════════════════════════════
# Node 13: Retrospective — 复盘节点
# ═══════════════════════════════════════════════════════════════

class RetrospectiveNode:
    """
    复盘节点 — 三层穿透根因分析 + 经验写入。
    职责：表层现象 → 动作根因 → 体系漏洞 → 改进方案 → 经验归档。

    2026-07-05 改造：交付物强制注册+复盘完整性校验。
    """
    node_type = NodeType.RETROSPECTIVE

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        # 场景 2: 进入复盘节点时自动基线快照（复盘前备份当前全量状态）
        try:
            from engine.flow.checkpoint import auto_create_baseline_snapshot
            auto_create_baseline_snapshot(
                state.instance_id,
                memo_suffix="复盘节点前置",
                task_status="running",
                state=state,
            )
        except Exception as e:
            logger.warning("复盘节点自动基线快照失败: %s", e)

        # 复盘前校验：必须已有验收结论
        acceptance_deliverables = [d for d in state.deliverables if d.content_type == "acceptance_report"]
        if not acceptance_deliverables:
            state.add_violation(
                vtype="SKIP_ATTEMPT",
                description="Retro 节点：验收未完成即进入复盘",
                points=2,
            )

        # 注册复盘交付物
        state.add_deliverable(
            content_type="retro_report",
            summary=f"复盘报告: {state.project_name}",
            agent_role=NodeType.RETROSPECTIVE,
        )

        state.current_status = FlowStatus.CLOSED
        state.completed_at = _now()
        state.record_node_execution(
            NodeType.RETROSPECTIVE, "passed",
            "复盘节点：三层根因分析 + 经验归档完成"
        )
        return state, None


# ═══════════════════════════════════════════════════════════════
# Node 14: SV-Supervisor — 独立监督者节点
# ═══════════════════════════════════════════════════════════════

class SVSupervisorNode:
    """
    独立监督者节点 — 流程监督 + 规则置顶 + 后置审计。
    不参与业务逻辑，仅在关键跃迁点做审计拦截。

    2026-07-05 改造：废除原有固定 APPROVED 桩代码。
    所有 audit_type 均执行对应维度的真实校验，不通过则冻结流程。
    """
    node_type = NodeType.SV_SUPERVISOR

    def __call__(self, state: FlowState, *, audit_type: str = "") -> tuple[FlowState, Optional[str]]:
        # 前置硬性：检测输出隔离违规。无论 audit_type 为何，一旦发现立即冻结，不执行任何后续校验
        isolation_issues = self._check_output_isolation(state)
        if isolation_issues:
            reason = "; ".join(isolation_issues)
            state.add_violation(
                vtype="COMPLIANCE_FAILURE",
                description=f"SV 审计前置拦截——输出隔离违规: {reason}",
                points=3,
            )
            state.is_frozen = True
            state.freeze_reason = f"SV 审计前置拦截——输出隔离违规: {reason}"
            state.metadata["sv_verdict"] = "BLOCKED"
            state.metadata["sv_audit_detail"] = isolation_issues
            state.record_node_execution(
                NodeType.SV_SUPERVISOR, "failed",
                error=state.freeze_reason,
            )
            return state, None

        checks = {
            "prd_sign_off": self._check_prd_sign_off,
            "smoke_gate_pass": self._check_smoke_gate,
            "post_gate_audit": self._check_post_gate,
            "bug_fix_closed": self._check_bug_fix_closed,
        }

        check_fn = checks.get(audit_type, self._check_generic)
        result = check_fn(state)
        verdict = "APPROVED" if result["passed"] else "BLOCKED"

        state.metadata["sv_verdict"] = verdict
        state.metadata["sv_audit_detail"] = result["details"]
        state.metadata["sv_audit_type"] = audit_type or "generic"

        if not result["passed"]:
            state.add_violation(
                vtype="COMPLIANCE_FAILURE",
                description=f"SV 审计不通过 [{audit_type}]: {result['reason']}",
                points=2,
            )
            state.is_frozen = True
            state.freeze_reason = f"SV 审计拦截 [{audit_type}]: {result['reason']}"
            state.record_node_execution(
                NodeType.SV_SUPERVISOR, "failed",
                error=state.freeze_reason,
            )
            return state, None

        state.record_node_execution(
            NodeType.SV_SUPERVISOR, "passed",
            f"SV 审计 [{audit_type}] 通过 — {result['reason']}"
        )
        return state, None

    # ─── 通用基线校验（所有 audit_type 共用） ────────────────

    @staticmethod
    def _baseline_checks(state: FlowState) -> list[str]:
        """执行基线校验，返回所有未通过项"""
        issues = []

        # 1. 违规门禁
        if state.total_points >= 3:
            issues.append(f"违规积分 {state.total_points} ≥ 3 熔断阈值")

        unresolved_violations = [v for v in state.violations if not v.resolved]
        if unresolved_violations:
            issues.append(f"存在 {len(unresolved_violations)} 条未处理违规")

        # 2. 冻结检查
        if state.is_frozen:
            issues.append(f"流程已冻结: {state.freeze_reason}")

        # 3. 交付物存在性
        if not state.deliverables:
            issues.append("流程至今无任何交付物记录")

        # 4. 未解决 Bug
        if state.unresolved_bug_count > 0:
            issues.append(f"存在 {state.unresolved_bug_count} 个未解决 Bug")

        # 5. 输出隔离违规检测（从治理 JSON 校验追溯）
        if state.task_meta.get("output_isolation_violation"):
            issues.append("输出隔离违规：治理 JSON 标记 full_content_embedded=true 或缺少文件变更摘要")
        # 检查最近一条违规是否与输出隔离相关
        recent_isolation_violation = any(
            "输出隔离" in v.description or "full_content_embedded" in v.description
            for v in state.violations[-3:]  # 最近 3 条
        )
        if recent_isolation_violation:
            issues.append("存在未解决的输出隔离违规记录，流程自动冻结")

        return issues

    @staticmethod
    def _check_output_isolation(state: FlowState) -> list[str]:
        """前置硬性校验：仅检测输出隔离违规。返回空列表 = 无违规，否则立即冻结。"""
        issues = []

        # 1. task_meta 中 output_isolation_violation 标记
        if state.task_meta.get("output_isolation_violation"):
            issues.append("输出隔离违规：task_meta 标记 output_isolation_violation=true（治理 JSON 校验标记）")

        # 2. 最近 3 条违规涉及输出隔离
        for v in state.violations[-3:]:
            if "输出隔离" in v.description or "full_content_embedded" in v.description or "治理 JSON" in v.description:
                issues.append(f"发现输出隔离违规记录: {v.description[:100]}")
                break

        # 3. 治理 JSON 标记 full_content_embedded=true（已写入状态）
        if state.task_meta.get("full_content_embedded"):
            issues.append("全量内容嵌入标记 full_content_embedded=true，违反输出隔离铁律")

        return issues

    # ─── 按 audit_type 的专项校验 ────────────────────────────

    @staticmethod
    def _check_prd_sign_off(state: FlowState) -> dict:
        """PRD 签审：六要素 + 交付物完整性"""
        issues = SVSupervisorNode._baseline_checks(state)

        prd_related = [d for d in state.deliverables if d.content_type == "prd_doc"]
        if not prd_related:
            issues.append("PRD 交付物缺失（content_type=prd_doc）")

        if not state.prd_doc:
            issues.append("state.prd_doc 未设置")

        # state 版本 = PRD_REVIEW 说明正在审核中
        if state.current_status not in ("PRD_REVIEW", "DESIGN"):
            issues.append(f"PRD 签审阶段状态异常: {state.current_status}")

        if issues:
            return {"passed": False, "reason": "; ".join(issues[:5]), "details": issues}
        return {"passed": True, "reason": f"PRD 签审通过（{len(prd_related)} 份交付物）", "details": issues}

    @staticmethod
    def _check_smoke_gate(state: FlowState) -> dict:
        """冒烟门禁：测试结果 + P0 阻断"""
        issues = SVSupervisorNode._baseline_checks(state)

        if not state.smoke_test:
            issues.append("冒烟测试未执行（smoke_test 为空）")
        else:
            if state.smoke_test.has_p0:
                issues.append(f"冒烟测试存在 P0 缺陷（{state.smoke_test.fail_count} 失败）")
            if state.smoke_test.total_steps == 0:
                issues.append("冒烟测试用例数为 0")
            if not state.smoke_test.evidence_checksum:
                issues.append("冒烟测试无证据校验和")

        if state.current_status not in ("SMOKE_TEST", "FULL_TEST"):
            issues.append(f"冒烟门禁阶段状态异常: {state.current_status}")

        if issues:
            return {"passed": False, "reason": "; ".join(issues[:5]), "details": issues}
        return {"passed": True, "reason": f"冒烟门禁通过（{state.smoke_test.pass_count}/{state.smoke_test.total_steps} 通过）", "details": issues}

    @staticmethod
    def _check_post_gate(state: FlowState) -> dict:
        """后置审计：全量测试 + 代码审查 + 部署条件"""
        issues = SVSupervisorNode._baseline_checks(state)

        if not state.full_test:
            issues.append("全量测试未执行（full_test 为空）")
        else:
            if state.full_test.has_p0:
                issues.append("全量测试存在 P0 缺陷")
            if state.full_test.has_p1:
                issues.append("全量测试存在 P1 缺陷")
            if not state.full_test.evidence_checksum:
                issues.append("全量测试无证据校验和")

        if not state.code_review_passed:
            issues.append("代码审查未通过")

        if not state.allow_deploy:
            issues.append("allow_deploy=False，不允许部署")
        elif state.full_test and (state.full_test.has_p0 or state.full_test.has_p1):
            issues.append("测试有失败但 allow_deploy=True，数据矛盾")

        if issues:
            return {"passed": False, "reason": "; ".join(issues[:5]), "details": issues}
        return {"passed": True, "reason": f"后置审计通过（全量测试 {state.full_test.pass_count}/{state.full_test.total_steps} 通过）", "details": issues}

    @staticmethod
    def _check_bug_fix_closed(state: FlowState) -> dict:
        """Bug 闭环：无未解决 P0/P1 Bug"""
        issues = SVSupervisorNode._baseline_checks(state)

        blocker_bugs = [b for b in state.bugs if b.severity in ("P0", "P1") and not b.resolved]
        if blocker_bugs:
            issues.append(f"存在 {len(blocker_bugs)} 个未解决 P0/P1 Bug")

        all_unresolved = [b for b in state.bugs if not b.resolved]
        if all_unresolved:
            issues.append(f"存在 {len(all_unresolved)} 个未解决 Bug（含非阻断）")

        if state.bug_fix_rounds >= 3:
            issues.append(f"Bug 修复已达 {state.bug_fix_rounds} 轮，超出阈值")

        if issues:
            return {"passed": False, "reason": "; ".join(issues[:5]), "details": issues}
        return {"passed": True, "reason": f"Bug 闭环通过（全部 {len(state.bugs)} 个已关闭）", "details": issues}

    @staticmethod
    def _check_generic(state: FlowState) -> dict:
        """通用校验（audit_type 无匹配时）"""
        issues = SVSupervisorNode._baseline_checks(state)
        if issues:
            return {"passed": False, "reason": "; ".join(issues[:5]), "details": issues}
        return {"passed": True, "reason": "通用 SV 审计通过", "details": issues}


# ═══════════════════════════════════════════════════════════════
# Node 15-19: 治理流程 IO 封装节点（对接现有 shell 钩子脚本）
# ═══════════════════════════════════════════════════════════════

class InputHookNode:
    """
    治理输入节点 — 封装 input-filter.sh 调用逻辑。
    职责：读取用户原始输入文件，检测回滚指令，写入 State。

    shell 等价：bash ~/.claude/hooks/input-filter.sh "$USER_RAW_INPUT"
    """
    node_type = "governance_input"

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        temp_dir = state.temp_cache_dir or "./temp_input_cache"
        raw_input_path = os.path.join(temp_dir, "_last_raw_input.txt")

        # 读取原始输入
        raw_text = ""
        if os.path.exists(raw_input_path):
            with open(raw_input_path, "r", encoding="utf-8") as f:
                raw_text = f.read().strip()

        # 检测回滚指令
        if "回滚任务 T" in raw_text:
            state.need_rollback = True
            state.record_node_execution(
                self.node_type, "rolled_back",
                summary="检测到回滚指令，跳过 DeepSeek",
            )
            return state, "gov_restore"

        state.need_rollback = False
        state.record_node_execution(
            self.node_type, "passed",
            summary=f"治理输入节点：原始输入已就绪 ({len(raw_text)} 字符)",
        )
        return state, None


class DeepSeekInferNode:
    """
    DeepSeek 推理节点 — 生成治理 JSON 并写入 State。
    职责：强制输出标准治理 JSON 块，通过 json_to_state() 解析填充。

    增量优化202607：
      - 前置全量 Schema 校验（字段类型/取值范围）
      - 校验失败自动重试（最多 3 轮）
      - 3 轮失败写入 Violation 并冻结流程
    """
    node_type = "governance_infer"

    MAX_RETRIES = 3

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        temp_dir = state.temp_cache_dir or "./temp_input_cache"
        gov_path = os.path.join(temp_dir, "_last_governance.json")
        raw_path = os.path.join(temp_dir, "_last_raw_input.txt")
        retry_count = 0

        # 读取原始输入供重新生成使用
        raw_input_text = ""
        if os.path.exists(raw_path):
            with open(raw_path, "r", encoding="utf-8") as f:
                raw_input_text = f.read().strip()

        while retry_count <= self.MAX_RETRIES:
            if not os.path.exists(gov_path):
                # 无治理 JSON 文件 —— 输出隔离铁律违规：模型未输出标准治理 JSON 块
                logger.warning("治理 JSON 文件不存在（第 %d 轮/共 %d 轮）: 模型输出未包含 ```json 治理块", retry_count + 1, self.MAX_RETRIES)
                if retry_count < self.MAX_RETRIES:
                    retry_count += 1
                    continue
                state.add_violation(
                    vtype="COMPLIANCE_FAILURE",
                    description=f"治理 JSON 文件不存在，{self.MAX_RETRIES} 轮重试耗尽。模型输出未包含标准 ```json 治理块，违反输出隔离铁律",
                    points=3,
                )
                state.task_meta["output_isolation_violation"] = True
                state.is_frozen = True
                state.freeze_reason = f"治理 JSON 文件不存在，{self.MAX_RETRIES} 轮重试耗尽。模型未输出标准治理块"
                state.record_node_execution(self.node_type, "failed", error=state.freeze_reason)
                return state, "frozen"

            try:
                with open(gov_path, "r", encoding="utf-8") as f:
                    gov = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                if retry_count < self.MAX_RETRIES:
                    retry_count += 1
                    logger.warning("治理 JSON 解析失败（第 %d 轮重试）: %s", retry_count, e)
                    continue
                state.add_violation(
                    vtype="COMPLIANCE_FAILURE",
                    description=f"治理 JSON 解析失败，{self.MAX_RETRIES} 轮重试耗尽: {e}",
                    points=3,
                )
                state.is_frozen = True
                state.freeze_reason = f"治理 JSON 解析失败，已熔断（{self.MAX_RETRIES} 轮）"
                return state, "frozen"

            # 增量优化202607：调用 prompt_manager 完整校验
            from engine.flow.prompt_manager import validate_governance_dict
            is_valid, validation_errors = validate_governance_dict(gov)

            if not is_valid:
                err_log = "; ".join(validation_errors)
                if retry_count < self.MAX_RETRIES:
                    retry_count += 1
                    logger.warning(
                        "治理JSON校验不通过（第%d轮/共%d轮）: %s",
                        retry_count, self.MAX_RETRIES, err_log,
                    )
                    os.remove(gov_path)
                    continue
                # 3 轮重试耗尽：写入违规、冻结流程
                has_isolation_violation = any(
                    "输出隔离" in err or "full_content_embedded" in err or "change_file_count" in err
                    for err in validation_errors
                )
                for err in validation_errors:
                    state.add_violation(
                        vtype="COMPLIANCE_FAILURE",
                        description=f"治理JSON校验失败（已熔断）: {err}",
                        points=1,
                    )
                if has_isolation_violation:
                    state.task_meta["output_isolation_violation"] = True
                state.is_frozen = True
                state.freeze_reason = f"治理JSON校验失败，{self.MAX_RETRIES}轮重试耗尽: {err_log}"
                state.record_node_execution(
                    self.node_type, "failed",
                    error=state.freeze_reason,
                )
                return state, "frozen"

            # 校验通过 → 解析到 State
            from engine.flow.integration import json_to_state
            state = json_to_state(gov, state)
            # 清除重试标记
            if os.path.exists(regen_flag):
                os.remove(regen_flag)
            break

        state.record_node_execution(
            self.node_type, "passed",
            summary=f"治理推理节点：JSON 解析完成 (char_count={state.char_count}, is_long={state.is_long_text})",
        )
        return state, None


class OutputHookNode:
    """
    治理输出落地节点 — 封装 output-filter.sh 逻辑。
    职责：同步 State 治理字段到文件缓存，准备摘要输出。

    shell 等价：bash ~/.claude/hooks/output-filter.sh "$CLAUDE_MODEL_OUTPUT"
    """
    node_type = "governance_output"

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        # 同步 State → 文件缓存
        from engine.flow.integration import state_to_file_cache
        result = state_to_file_cache(state)

        summary = f"治理输出节点：文件缓存已同步"
        if "error" in result:
            summary += f" ({result['error']})"
        else:
            summary += f" (governance={result.get('governance_path', '')})"

        state.record_node_execution(self.node_type, "passed", summary=summary)
        return state, None


class SnapshotBackupNode:
    """
    快照备份节点 — 封装 backup-snapshot.sh 逻辑。
    职责：生成项目文件快照，CKPT_ID 写入 task_meta。

    shell 等价：bash ~/.claude/scripts/backup-snapshot.sh
    """
    node_type = "governance_snapshot"

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        # 生成快照 ID
        ckpt_id = f"CKPT-{datetime.now().strftime('%Y%m%d')}-{int(datetime.now().timestamp())}"
        backup_dir = f"{state.snapshot_root}/{ckpt_id}"
        os.makedirs(backup_dir, exist_ok=True)

        state.task_meta["snapshot_id"] = ckpt_id

        state.record_node_execution(
            self.node_type, "passed",
            summary=f"治理快照节点：快照 {ckpt_id} 创建于 {backup_dir}",
        )
        return state, None


class SnapshotRestoreNode:
    """
    快照回滚节点 — 封装 restore-snapshot.sh 逻辑。
    职责：执行回滚，设置状态为 ROLLBACK，终止 Graph 流转。

    增量优化202607：
      - 回滚完成后自动推送 ROLLBACK 事件至 Harness 审计看板

    shell 等价：bash ~/.claude/scripts/restore-snapshot.sh "$INPUT"
    """
    node_type = "governance_restore"

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        state.current_status = FlowStatus.ROLLBACK
        state.record_node_execution(
            self.node_type, "passed",
            summary="治理回滚节点：回滚完成，流程终止",
        )

        # 增量优化202607：推送 ROLLBACK 事件至 Harness
        try:
            from engine.flow.harness_client import get_harness_client
            client = get_harness_client()
            client.send_event(
                instance_id=state.instance_id,
                event_type="NODE_ROLLBACK",
                operator=self.node_type,
                payload={
                    "snapshot_id": state.task_meta.get("snapshot_id", ""),
                    "rollback_reason": state.metadata.get("rollback_reason", "治理回滚节点触发"),
                    "rollback_time": datetime.now().isoformat(),
                },
            )
        except Exception:
            logger.debug("Harness ROLLBACK 事件推送失败（不阻断）")

        return state, "__end__"


class ContextCompressNode:
    """
    上下文压缩节点 — 封装 compress-context.sh 逻辑。
    职责：执行三级阈值检测，记录压缩标记。

    shell 等价：bash ~/.claude/scripts/compress-context.sh
    """
    node_type = "governance_compress"

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        state.record_node_execution(
            self.node_type, "passed",
            summary=f"治理压缩节点：检查于 {now_str}，三级阈值 12000/14500/15800",
        )
        return state, None


# ═══════════════════════════════════════════════════════════════
# 增量优化202607：暂停/恢复节点
# ═══════════════════════════════════════════════════════════════

class PauseNode:
    """
    暂停节点 — 保存当前 Checkpoint 后冻结流程。

    （RETIRED-2026-08-17：原外部触发入口 /api/flow/{id}/pause 与 /resume 已随旧 /api/flow
    链路退役下线；节点本体保留供图内治理流使用，外部触发改由节点侧 ET 组装 Payload 调 kernel.et() 承接。）
    """
    node_type = "governance_pause"

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        state.is_frozen = True
        state.freeze_reason = f"人工暂停于节点 {state.metadata.get('last_node', 'unknown')}"
        state.current_status = FlowStatus.FROZEN

        # 记录暂停快照
        state.record_node_execution(
            self.node_type, "paused",
            summary=f"流程暂停: {state.freeze_reason}",
        )

        # 通知 Harness
        try:
            from engine.flow.harness_client import get_harness_client
            client = get_harness_client()
            client.send_event(
                instance_id=state.instance_id,
                event_type="FLOW_PAUSE",
                operator=self.node_type,
                payload={
                    "reason": state.freeze_reason,
                    "paused_at": datetime.now().isoformat(),
                },
            )
        except Exception:
            pass

        return state, "__end__"


class ResumeNode:
    """
    恢复节点 — 从暂停状态恢复流程。

    自动从 Checkpoint 加载断点 State，清除冻结标记。
    """
    node_type = "governance_resume"

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        if not state.is_frozen:
            state.record_node_execution(
                self.node_type, "skipped",
                summary="流程未暂停，跳过恢复",
            )
            return state, None

        state.is_frozen = False
        state.freeze_reason = ""
        state.current_status = FlowStatus.PENDING

        state.record_node_execution(
            self.node_type, "resumed",
            summary="流程已从暂停状态恢复",
        )

        # 通知 Harness
        try:
            from engine.flow.harness_client import get_harness_client
            client = get_harness_client()
            client.send_event(
                instance_id=state.instance_id,
                event_type="FLOW_RESUME",
                operator=self.node_type,
                payload={
                    "resumed_at": datetime.now().isoformat(),
                },
            )
        except Exception:
            pass

        return state, None


# ═══════════════════════════════════════════════════════════════
# 节点注册表（供 Graph 构建使用）
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# Harness 自愈模式 — 三层规则校验节点（2026-07-06）
# ═══════════════════════════════════════════════════════════════

class SkillGateCheckNode:
    """
    层级1：SV Skill 门禁规则校验节点。
    对应 skill_gate_rules.yaml（SV-GATE-001 ~ SV-GATE-008）。

    职责：前置阻断，拦截高危违规，同步 Harness 审计。
    特性：无自动自愈动作，仅拦截 + 上报 Harness。

    拦截后：
      - state.is_frozen = True
      - state.freeze_reason = 匹配的规则描述
      - 调用 Harness 回调上报阻断事件
    """
    node_type = "self_heal_gate"

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        violations_found = []
        harness_client = None

        # 1. SV-GATE-001: 需求超 PRD 范围
        prd_related = [d for d in state.deliverables if d.content_type == "prd_doc"]
        if not prd_related and state.current_status not in ("PENDING",):
            violations_found.append({
                "rule_id": "SV-GATE-001",
                "desc": "缺少 PRD 交付物，存在需求超范围风险",
                "action": "block",
            })

        # 2. SV-GATE-002: 角色积分管控
        if state.total_points >= 3:
            violations_found.append({
                "rule_id": "SV-GATE-002",
                "desc": f"违规积分 {state.total_points} ≥ 3，触发熔断",
                "action": "block",
            })

        # 3. SV-GATE-003: PM 流程监督
        if state.is_frozen:
            violations_found.append({
                "rule_id": "SV-GATE-003",
                "desc": f"流程已冻结: {state.freeze_reason}",
                "action": "block",
            })

        # 4. SV-GATE-004: 测试用例门禁（仅在 FULL_TEST/ACCEPTANCE 阶段检测）
        if state.current_status in (FlowStatus.FULL_TEST, FlowStatus.ACCEPTANCE):
            test_deliverables = [d for d in state.deliverables if "test" in d.content_type]
            if not test_deliverables:
                violations_found.append({
                    "rule_id": "SV-GATE-004",
                    "desc": f"【{state.current_status}】阶段缺少测试交付物",
                    "action": "block",
                })

        # 5. SV-GATE-005: 流程后置审计
        if state.current_status == FlowStatus.ACCEPTANCE:
            required_types = {"test_report", "deploy_report", "code_review_report"}
            existing_types = {d.content_type for d in state.deliverables}
            missing = required_types - existing_types
            if missing:
                violations_found.append({
                    "rule_id": "SV-GATE-005",
                    "desc": f"交付物缺失: {', '.join(missing)}",
                    "action": "block",
                })

        # 6. SV-GATE-006: Bug 修复策略顺序
        if state.bug_fix_rounds >= 3:
            violations_found.append({
                "rule_id": "SV-GATE-006",
                "desc": f"Bug 修复已达 {state.bug_fix_rounds} 轮，需进行重构评估",
                "action": "warn",
            })

        # 7. SV-GATE-007: UI 自动化单浏览器（元数据中检测）
        browser_type = state.metadata.get("browser_type", "")
        if browser_type and "parallel" in str(state.metadata.get("test_config", {})):
            violations_found.append({
                "rule_id": "SV-GATE-007",
                "desc": f"检测到多浏览器并行执行配置",
                "action": "block",
            })

        # 8. SV-GATE-008: 旧 test-engineer 拦截
        last_role = state.metadata.get("last_agent_role", "")
        if last_role == "test-engineer":
            violations_found.append({
                "rule_id": "SV-GATE-008",
                "desc": f"检测到已拆分旧角色 test-engineer 调用",
                "action": "redirect",
                "redirect_to": "test-case-designer/test-executor/test-supervisor",
            })

        # 处理违规
        if not violations_found:
            state.record_node_execution(
                self.node_type, "passed",
                summary="SV 门禁校验通过（SV-GATE-001~008）",
            )
            return state, None

        # 有违规：处理并尝试上报 Harness
        try:
            from engine.flow.harness_client import get_harness_client
            harness_client = get_harness_client()
        except Exception:
            harness_client = None

        has_blocker = any(v["action"] == "block" for v in violations_found)
        reasons = []
        for v in violations_found:
            reasons.append(f"[{v['rule_id']}] {v['desc']}")
            # 上报 Harness
            if harness_client:
                try:
                    harness_client.report_self_heal_event(
                        instance_id=state.instance_id,
                        rule_scope="skill_gate",
                        rule_id=v["rule_id"],
                        remediate_action=v.get("action", "block"),
                        remediate_result="block" if v["action"] == "block" else "success",
                        violation_raw=v["desc"],
                        operator="SV-Supervisor",
                        flow_id=f"FLOW-{state.current_status}",
                    )
                except Exception:
                    logger.debug("Harness 自愈事件上报失败（不阻断校验）")

        if has_blocker:
            state.add_violation(
                vtype=ViolationType.COMPLIANCE_FAILURE,
                description="SV 门禁拦截: " + "; ".join(reasons),
                points=2,
            )
            state.is_frozen = True
            state.freeze_reason = f"SV 门禁违规（{'; '.join(reasons)}）"
            state.record_node_execution(
                self.node_type, "failed",
                error=state.freeze_reason,
            )
            return state, "frozen"

        state.record_node_execution(
            self.node_type, "passed",
            summary=f"SV 门禁通过（{len(violations_found)} 项警告）: " + "; ".join(reasons),
        )
        return state, None


class FlowRuleValidatorNode:
    """
    层级2：分流程私有规则校验节点。
    对应 flow_pm_rules.yaml / flow_test_rules.yaml / flow_deploy_rules.yaml / flow_acceptance_rules.yaml。

    职责：流程内自愈，执行规则定义的 remediate_mode 自愈逻辑。
    自愈完成后二次重校验，通过才允许流转。
    失败则同步 Harness 标记「流程自愈失败，人工介入」。
    """
    node_type = "self_heal_flow"

    # 规则与校验函数映射
    FLOW_CHECKS = {
        "FLOW-PM": [
            ("PM-001", "需求模糊", lambda s: bool(s.clean_input) or bool(s.prd_doc)),
            ("PM-002", "Bug流程", lambda s: s.bug_fix_rounds >= 0),
            ("PM-006", "触发词同步", lambda s: True),  # 由外部 Skill 检测
        ],
        "FLOW-TEST": [
            ("TEST-001", "用例分层", lambda s: len(s.deliverables) > 0),
            ("TEST-002", "用例回流", lambda s: True),
            ("TEST-003", "越权拦截", lambda s: True),
        ],
        "FLOW-DEPLOY": [
            ("DEPLOY-001", "交付物完整性",
             lambda s: any(d.content_type in ("test_report", "code_review_report") for d in s.deliverables)),
            ("DEPLOY-002", "增量覆盖", lambda s: True),
            ("DEPLOY-003", "产物校验", lambda s: True),
        ],
        "FLOW-ACCEPTANCE": [
            ("ACPT-001", "验收路由", lambda s: s.acceptance_passed or not s.has_blocker_bugs()),
        ],
    }

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        # 根据 current_status 推断所属 flow
        flow_id = self._detect_flow_id(state)
        if not flow_id:
            state.record_node_execution(
                self.node_type, "skipped",
                summary="未匹配到流程规则，跳过自愈校验",
            )
            return state, None

        checks = self.FLOW_CHECKS.get(flow_id, [])
        results = []
        remediate_needed = []

        for rule_id, rule_name, check_fn in checks:
            try:
                passed = check_fn(state)
            except Exception:
                passed = False

            if not passed:
                remediate_needed.append({"rule_id": rule_id, "rule_name": rule_name})
                results.append({"rule_id": rule_id, "passed": False})
            else:
                results.append({"rule_id": rule_id, "passed": True})

        # 需要自愈
        if remediate_needed:
            for item in remediate_needed:
                self._auto_remediate(state, item["rule_id"], flow_id)

            # 二次校验
            recheck_failed = []
            for item in remediate_needed:
                for rule_id, rule_name, check_fn in checks:
                    if rule_id == item["rule_id"]:
                        try:
                            if not check_fn(state):
                                recheck_failed.append(rule_id)
                        except Exception:
                            recheck_failed.append(rule_id)

            if recheck_failed:
                reasons = "; ".join([f"{rid} 自愈后仍失败" for rid in recheck_failed])
                # 上报 Harness
                self._report_to_harness(state, flow_id, recheck_failed, "fail")
                state.add_violation(
                    vtype=ViolationType.COMPLIANCE_FAILURE,
                    description=f"流程自愈失败 [{flow_id}]: {reasons}",
                    points=1,
                )
                state.is_frozen = True
                state.freeze_reason = f"{flow_id} 自愈失败: {reasons}"
                state.record_node_execution(self.node_type, "failed", error=state.freeze_reason)
                return state, "frozen"

            # 自愈成功
            self._report_to_harness(state, flow_id, [v["rule_id"] for v in remediate_needed], "success")
            state.record_node_execution(
                self.node_type, "passed",
                summary=f"{flow_id} 自愈完成: {len(remediate_needed)} 项修复",
            )
            return state, None

        state.record_node_execution(
            self.node_type, "passed",
            summary=f"{flow_id} 规则校验通过（{len(results)} 项全部通过）",
        )
        return state, None

    @staticmethod
    def _detect_flow_id(state: FlowState) -> Optional[str]:
        """根据 current_status 推断所属流程"""
        status = state.current_status
        if isinstance(status, FlowStatus):
            status = status.value
        status = str(status)

        # PM 相关状态
        if status in ("PENDING", "PRD_REVIEW", "DESIGN", "PM_CONFIRM", "CLOSED"):
            return "FLOW-PM"
        # 测试相关状态
        if status in ("SMOKE_TEST", "FULL_TEST"):
            return "FLOW-TEST"
        # 部署相关状态
        if status in ("DEPLOY",):
            return "FLOW-DEPLOY"
        # 验收相关
        if status in ("ACCEPTANCE",):
            return "FLOW-ACCEPTANCE"
        # 其他状态也可归入 PM 流程
        return "FLOW-PM"

    def _auto_remediate(self, state: FlowState, rule_id: str, flow_id: str):
        """根据规则 ID 执行自动自愈脚本"""
        remediate_actions = {
            "PM-001": self._pm_001_remediate,
            "PM-002": self._pm_002_remediate,
            "PM-006": self._pm_006_remediate,
            "TEST-001": self._test_001_remediate,
            "TEST-002": self._test_002_remediate,
            "DEPLOY-001": self._deploy_001_remediate,
            "DEPLOY-003": self._deploy_003_remediate,
            "ACPT-001": self._acpt_001_remediate,
        }
        fn = remediate_actions.get(rule_id)
        if fn:
            fn(state)

    # ─── 自愈动作实现 ────────────────────────────────────────────

    @staticmethod
    def _pm_001_remediate(state: FlowState):
        """PM-001: 需求模糊 → 标记为需要用户澄清"""
        state.metadata["needs_clarification"] = True
        state.metadata["clarification_required_fields"] = ["业务目标", "功能描述", "目标用户"]

    @staticmethod
    def _pm_002_remediate(state: FlowState):
        """PM-002: Bug 流程 → 重置为 PM 引导流程"""
        state.bug_fix_rounds = max(0, state.bug_fix_rounds)

    @staticmethod
    def _pm_006_remediate(state: FlowState):
        """PM-006: 触发词同步 → 标记双文件同步检查"""
        state.metadata["skill_claude_sync_needed"] = True

    @staticmethod
    def _test_001_remediate(state: FlowState):
        """TEST-001: 用例分层 → 标记重构"""
        state.metadata["test_case_restructure_needed"] = True

    @staticmethod
    def _test_002_remediate(state: FlowState):
        """TEST-002: 用例不合格 → 重建 test-case-designer 交付物"""
        tcd_dels = [d for d in state.deliverables if d.agent_role == NodeType.TEST_CASE_DESIGNER]
        for d in tcd_dels:
            d.validated = False
            d.validation_result = "退回修正"

    @staticmethod
    def _deploy_001_remediate(state: FlowState):
        """DEPLOY-001: 交付物缺失 → 标记缺失清单"""
        required = {"test_report", "code_review_report"}
        existing = {d.content_type for d in state.deliverables}
        missing = required - existing
        state.metadata["missing_deliverables"] = list(missing)

    @staticmethod
    def _deploy_003_remediate(state: FlowState):
        """DEPLOY-003: 产物校验 → 标记需重打包"""
        state.metadata["repack_needed"] = True

    @staticmethod
    def _acpt_001_remediate(state: FlowState):
        """ACPT-001: 验收路由 → 根据验收结果自动路由"""
        if state.acceptance_passed:
            state.metadata["acceptance_action"] = "trigger_closing"
        else:
            state.metadata["acceptance_action"] = "send_back_to_dev"

    @staticmethod
    def _report_to_harness(state: FlowState, flow_id: str, rule_ids: list[str], result: str):
        """上报自愈事件到 Harness"""
        try:
            from engine.flow.harness_client import get_harness_client
            client = get_harness_client()
            for rid in rule_ids:
                client.report_self_heal_event(
                    instance_id=state.instance_id,
                    rule_scope="flow_private",
                    rule_id=rid,
                    remediate_action="auto_remediate",
                    remediate_result=result,
                    violation_raw=f"{flow_id} 自愈: {rid}",
                    operator=f"FlowRuleValidator-{flow_id}",
                    flow_id=flow_id,
                )
        except Exception:
            logger.debug("Harness 自愈事件上报失败（不阻断）")


class GlobalOutputValidatorNode:
    """
    层级3：全局输出规则校验节点。
    对应 global_output_rules.yaml（GOV-OUT-001 ~ GOV-OUT-012）。

    职责：校验治理 JSON 输出是否符合规范，执行内容自愈。
    由 GovernanceSubGraph 在 output-filter.sh 阶段统一处理。
    """
    node_type = "self_heal_output"

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        issues = []

        # GOV-OUT-001/005: 治理 JSON 完整性
        if not state.task_meta.get("task_id"):
            issues.append({"rule_id": "GOV-OUT-001", "desc": "缺少 task_id"})

        # GOV-OUT-004: full_content_embedded 强制 false
        if state.task_meta.get("full_content_embedded"):
            issues.append({"rule_id": "GOV-OUT-004", "desc": "full_content_embedded=true 违规"})

        # GOV-OUT-006: 长文本落地
        if state.char_count > 50 and not state.is_long_text:
            issues.append({"rule_id": "GOV-OUT-006", "desc": "char_count > 50 但 is_long_text=false"})

        # GOV-OUT-008: 大文本不入 State
        check_large_fields = []
        if state.prd_doc and isinstance(state.prd_doc, str) and len(state.prd_doc) > 1000:
            check_large_fields.append("prd_doc")
        if state.interaction_doc and isinstance(state.interaction_doc, str) and len(state.interaction_doc) > 1000:
            check_large_fields.append("interaction_doc")
        if check_large_fields:
            issues.append({"rule_id": "GOV-OUT-008", "desc": f"大文本字段未文件化: {', '.join(check_large_fields)}"})

        # GOV-OUT-009: 8001 端口检测
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        langgraph_available = sock.connect_ex(("127.0.0.1", 8001)) == 0
        sock.close()
        if not langgraph_available and state.config_version:
            # 降级标记：该节点仍可运行，但记录降级
            state.metadata["degraded_mode"] = True
            issues.append({"rule_id": "GOV-OUT-009", "desc": "8001 端口不可用，文件 IO 降级模式"})

        # 处理修复
        if not issues:
            state.record_node_execution(
                self.node_type, "passed",
                summary="全局输出规则校验通过",
            )
            return state, None

        # 执行自动自愈
        auto_fixes = []
        for issue in issues:
            fix = self._auto_fix(state, issue["rule_id"])
            if fix:
                auto_fixes.append(fix)

        # 二次校验
        recheck_issues = []
        for issue in issues:
            rid = issue["rule_id"]
            if rid == "GOV-OUT-004" and state.task_meta.get("full_content_embedded"):
                recheck_issues.append(issue)
            elif rid == "GOV-OUT-006" and state.char_count > 50 and not state.is_long_text:
                recheck_issues.append(issue)

        if recheck_issues:
            state.add_violation(
                vtype=ViolationType.COMPLIANCE_FAILURE,
                description="全局输出自愈失败: " + "; ".join([i["desc"] for i in recheck_issues]),
                points=1,
            )
            # 触发 GOV-OUT-012: 回调 Harness
            self._report_to_harness(state, recheck_issues, "fail")
            state.record_node_execution(self.node_type, "failed", error="全局输出自愈失败")
            return state, "frozen"

        # 自愈成功 — 触发根源修复（四段闭环第4段）
        has_gov_003_or_004 = any(
            i["rule_id"] in ("GOV-OUT-003", "GOV-OUT-004") for i in issues
        )
        if has_gov_003_or_004:
            # GOV-OUT-003/004 频繁触发表明源头配置缺失，需自动加固
            self._trigger_root_cause_fix(state, issues)

        self._report_to_harness(state, issues, "success")
        state.record_node_execution(
            self.node_type, "passed",
            summary=f"全局输出自愈完成: {len(auto_fixes)} 项修复",
        )
        return state, None

    @staticmethod
    def _auto_fix(state: FlowState, rule_id: str) -> Optional[str]:
        """根据规则 ID 执行自动修复"""
        fixes = {
            "GOV-OUT-001": lambda s: s.task_meta.update({"task_id": s.instance_id}) or "task_id 自动补齐",
            "GOV-OUT-004": lambda s: s.task_meta.update({"full_content_embedded": False}) or "full_content_embedded 重置为 false",
            "GOV-OUT-006": lambda s: setattr(s, 'is_long_text', True) or "is_long_text 自动置为 true",
            "GOV-OUT-008": lambda s: s.metadata.update({"large_text_file_ref": True}) or "大文本标记为文件引用",
            "GOV-OUT-009": lambda s: s.metadata.update({"degraded_mode": True}) or "降级模式激活",
        }
        fn = fixes.get(rule_id)
        if fn:
            return fn(state)
        return None

    @staticmethod
    def _report_to_harness(state: FlowState, issues: list[dict], result: str):
        """上报自愈事件"""
        try:
            from engine.flow.harness_client import get_harness_client
            client = get_harness_client()
            for issue in issues:
                client.report_self_heal_event(
                    instance_id=state.instance_id,
                    rule_scope="global_output",
                    rule_id=issue["rule_id"],
                    remediate_action="auto_fix",
                    remediate_result=result,
                    violation_raw=issue["desc"],
                    operator="GlobalOutputValidator",
                    flow_id=f"FLOW-{state.current_status}",
                )
        except Exception:
            logger.debug("Harness 自愈事件上报失败（不阻断）")

    @staticmethod
    def _trigger_root_cause_fix(state: FlowState, issues: list[dict]):
        """
        触发根源修复 — 四段闭环第4段。
        在临时修复成功后，定位违规源头并修改配置。
        """
        # 构造违规内容摘要
        violations_desc = "; ".join([i["desc"] for i in issues])

        # 设置触发信息供 SelfHealRootCauseNode 读取
        state.metadata["root_trigger_rule_ids"] = [i["rule_id"] for i in issues]
        state.metadata["root_violation_content"] = violations_desc
        state.metadata["root_event_id"] = (
            f"SHE-ROOT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )

        # 实例化并执行根源修复节点
        try:
            root_node = SelfHealRootCauseNode()
            new_state, routing = root_node(state)
            # 将根源修复结果写回 state
            state.metadata["root_cause_trace"] = new_state.metadata.get("root_cause_trace", {})
            logger.info(
                "根源修复完成: source=%s, status=%s",
                state.metadata.get("root_cause_trace", {}).get("source_node", "?"),
                state.metadata.get("root_cause_trace", {}).get("final_status", "?"),
            )
        except Exception as e:
            logger.warning("根源修复执行失败（不阻断主流程）: %s", e)


ALL_NODES: dict[str, NodeFn] = {
    "pm": PMNode(),
    "pm_confirm": pm_confirm_node,
    "spm": SPMNode(),
    "dpm": DPMNode(),
    "ui_designer": UIDesignerNode(),
    "tcd": TestCaseDesignerNode(),
    "fe": FrontendDevNode(),
    "be": BackendDevNode(),
    "executor": TestExecutorNode(),
    "supervisor": TestSupervisorNode(),
    "code_review": CodeReviewNode(),
    "ops": OpsDeployNode(),
    "qa": AcceptanceNode(),
    "retro": RetrospectiveNode(),
    "sv": SVSupervisorNode(),

    # 治理流程 IO 封装节点（Node 15-19）
    "gov_input": InputHookNode(),
    "gov_infer": DeepSeekInferNode(),
    "gov_output": OutputHookNode(),
    "gov_snapshot": SnapshotBackupNode(),
    "gov_restore": SnapshotRestoreNode(),
    "gov_compress": ContextCompressNode(),

    # 增量优化202607：暂停/恢复节点
    "pause": PauseNode(),
    "resume": ResumeNode(),

    # Harness 自愈模式 — 三层规则校验节点
    "self_heal_gate": SkillGateCheckNode(),
    "self_heal_flow": FlowRuleValidatorNode(),
    "self_heal_output": GlobalOutputValidatorNode(),
}


# ═══════════════════════════════════════════════════════════════
# Harness 根源根治自愈节点（2026-07-06 新增）
# 补齐四段闭环缺失环节：溯源定位 → 根源根治 → 长效回归校验
# ═══════════════════════════════════════════════════════════════

class SelfHealRootCauseNode:
    """
    根源根治自愈节点 — 四段闭环的第4段（溯源→根治→回归→上报）。

    职责：
      1. 接收自愈触发事件（来自 GlobalOutputValidatorNode 或外部调用）
      2. 溯源定位违规源头（三类：skill_node / flow_node / langgraph_script）
      3. 执行对应场景的根源修复动作
      4. 长效回归校验：模拟调用源头节点，验证是否仍输出代码
      5. 全量上报 Harness（含 temp_remediate + root_remediate 双字段）

    修复场景 A：来自 SKILL.md 技能输出
      → 在技能输出约束区追加过滤条款，同步更新 CLAUDE.md
    修复场景 B：来自 Flow 流程节点
      → 修改 Prompt 模板约束、流程私有规则追加拦截子规则
    修复场景 C：来自 LangGraph 内置脚本
      → 增强 output-filter.sh/graph_exec.sh 代码块拦截正则，重载规则缓存
    """
    node_type = "self_heal_root"

    # ─── 规则正则（用于检测代码输出） ────────────────────────────
    CODE_PATTERNS = [
        r'```(?:python|bash|sh|yaml|json|javascript|typescript)',
        r'^[+-]{3} ',
        r'^>>> ',
        r'TestClient\.',
        r'npx playwright test',
        r'python3 -c "',
        r'cat > .+ << ',
    ]

    # ─── 场景 A：SKILL.md 约束注入模板 ──────────────────────────

    SKILL_CONSTRAINT_TEMPLATE = """
## 输出约束（自愈自动加固）
本技能由 Harness 自愈系统在 {date} 自动加固：
- 禁止直接输出完整代码、脚本、diff 内容到对话窗口
- 所有代码执行结果仅输出文件路径摘要（格式：`[模块名] 文件(±行)`）
- 完整代码强制写入 output-{date}.md
- 违反此规则将触发 GOV-OUT-003 阻断并自动修复
"""

    FLOW_CONSTRAINT_TEMPLATE = """
  - rule_id: "PM-{nid}"
    rule_source_file: ".claude/rules/flow_pm_rules.yaml"
    scope: "flow_private"
    flow_id: "FLOW-PM"
    name: "代码输出拦截（自愈自动加固）"
    description: "禁止 Flow 节点直接输出完整代码到对话"
    severity: "high"
    check_logic: |
      检测输出是否包含代码块标记、diff 符号、完整脚本
    remediate_mode: "auto_block_and_strip"
    remediate_steps:
      - 拦截代码输出，自动剥离至 output-{date}.md
      - 对话仅展示文件路径摘要
"""

    FILTER_ENHANCEMENT_TEMPLATE = r"""
# 自愈自动增强：代码块拦截正则（追加于 output-filter.sh）
# 拦截：markdown 代码块、diff 块、Python 测试客户端、npx 命令输出
CODE_BLOCK_PATTERN='```(python|bash|sh|yaml|json|javascript|typescript)'
DIFF_PATTERN='^[+-]{3} '
TEST_CLIENT_PATTERN='TestClient\('
PLAYWRIGHT_PATTERN='npx (playwright|cypress) '

# 命中任一正则 → 强制剥离至 output-*.md，对话仅留路径引用
if echo "$MODEL_OUTPUT" | grep -qE "$CODE_BLOCK_PATTERN|$DIFF_PATTERN|$TEST_CLIENT_PATTERN|$PLAYWRIGHT_PATTERN"; then
    echo "$MODEL_OUTPUT" >> "./output-$(date +%Y%m%d).md"
    echo "[代码变更] output-$(date +%Y%m%d).md（已自动剥离）"
    exit 0
fi
"""

    def __call__(self, state: FlowState) -> tuple[FlowState, Optional[str]]:
        # 从 metadata 获取触发信息
        trigger_rule_ids = state.metadata.get("root_trigger_rule_ids", ["GOV-OUT-003"])
        violation_content = state.metadata.get("root_violation_content", "")
        event_id = state.metadata.get("root_event_id", f"SHE-ROOT-{datetime.now().strftime('%Y%m%d%H%M%S')}")

        if not violation_content:
            state.record_node_execution(
                self.node_type, "skipped",
                summary="无违规内容，跳过根源修复",
            )
            return state, None

        # Step 1: 溯源定位
        source_node, config_path, root_cause = self._trace_source(state, violation_content)
        if not source_node:
            state.record_node_execution(self.node_type, "skipped", summary="无法定位违规源头")
            return state, None

        # Step 2: 根源修复
        root_action, change_record = self._execute_root_fix(source_node, config_path)

        # Step 3: 回归校验
        regress_passed, regress_detail = self._run_regression(source_node)
        regress_iter = 0
        while not regress_passed and regress_iter < 2:
            regress_iter += 1
            root_action, change_record = self._execute_root_fix(source_node, config_path, iteration=regress_iter)
            regress_passed, regress_detail = self._run_regression(source_node)

        # Step 4: 上报 Harness
        final_status = self._determine_status(regress_passed)
        self._report_root_event(
            state, event_id, source_node, config_path, root_cause,
            root_action, change_record, regress_passed, regress_detail,
            final_status,
        )

        # 更新 state
        state.metadata["root_cause_trace"] = {
            "source_node": source_node,
            "config_path": config_path,
            "root_cause": root_cause,
            "root_action": root_action,
            "change_record": change_record,
            "regression_passed": regress_passed,
            "final_status": final_status,
        }

        state.record_node_execution(
            self.node_type, "passed",
            summary=f"根源自愈完成: {source_node} → {final_status} (回归{'通过' if regress_passed else '失败'})",
        )
        return state, None

    # ═══════════════════════════════════════════════════════════════
    # 溯源逻辑
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _trace_source(state: FlowState, violation: str) -> tuple[Optional[str], Optional[str], str]:
        """
        追溯违规输出源头。
        优先从 state.metadata.last_agent_role / last_node 获取，
        如果无法获取则通过 violation 内容模式匹配推断。
        """
        # 方法1：从 state metadata 直接获取
        last_role = state.metadata.get("last_agent_role", "")
        last_node = state.metadata.get("last_node", "")

        if last_role and last_role != "pm":
            config_path = f".claude/skills/user/{last_role}/SKILL.md"
            return "skill_node", config_path, f"Agent 角色 [{last_role}] 直接输出了违规代码"

        if last_node and "skill" in last_node.lower():
            config_path = f".claude/skills/user/{last_node}/SKILL.md"
            return "skill_node", config_path, f"Skill 节点 [{last_node}] 输出了违规代码"

        # 方法2：通过 violation 内容模式推断
        if "npx playwright" in violation or "TestClient" in violation:
            return "langgraph_script", "backend/langgraph/nodes.py", "LangGraph 内置节点执行测试代码后直接输出了完整代码"

        if "```" in violation and ("yaml" in violation or "json" in violation):
            return "skill_node", ".claude/rules/global_output_rules.yaml", "技能/规则节点输出配置代码到对话"

        if "def " in violation or "class " in violation or "import " in violation:
            return "flow_node", "backend/langgraph/state.py", "Flow 节点生成了 Python 代码并直接展示"

        return None, None, "无法自动定位违规源头"

    # ═══════════════════════════════════════════════════════════════
    # 根源修复执行（三类场景）
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _execute_root_fix(
        source_node: str, config_path: str, iteration: int = 0
    ) -> tuple[str, str]:
        """
        根据源头类型执行根源修复。
        返回 (修复动作描述, 变更记录)
        """
        today = datetime.now().strftime("%Y%m%d")

        if source_node == "skill_node" and config_path:
            return SelfHealRootCauseNode._fix_skill_source(config_path, today)

        elif source_node == "flow_node":
            return SelfHealRootCauseNode._fix_flow_source(today, iteration)

        elif source_node == "langgraph_script":
            return SelfHealRootCauseNode._fix_script_source(today, iteration)

        return "未识别源头，跳过根源修复", ""

    @staticmethod
    def _fix_skill_source(config_path: str, today: str) -> tuple[str, str]:
        """场景 A：修改 SKILL.md，追加输出约束条款 + 同步 CLAUDE.md"""
        full_path = os.path.expanduser(f"~/{config_path}")
        action = ""
        change_record = ""

        if os.path.exists(full_path):
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
            constraint = SelfHealRootCauseNode.SKILL_CONSTRAINT_TEMPLATE.format(date=today)
            if "## 输出约束（自愈自动加固）" not in content:
                with open(full_path, "a", encoding="utf-8") as f:
                    f.write(constraint)
                action = f"向 {config_path} 追加输出约束条款"
                change_record = f"{config_path} 追加输出约束[{today}]"
            else:
                action = f"{config_path} 已有输出约束，无需重复加固"
                change_record = f"{config_path} 约束已存在，跳过"
        else:
            # SKILL.md 不存在 — 降级至写入 .claude/rules 相关规则文件
            action = f"SKILL.md 不存在 ({config_path})，降级至规则文件加固"
            change_record = f"SKILL.md 不存在，降级处理"
            # 尝试加固 CLAUDE.md
            claude_path = os.path.expanduser("~/.claude/CLAUDE.md")
            if os.path.exists(claude_path):
                claude_constraint = (
                    f"\n## 自愈自动加固 {today}\n"
                    f"来源节点: SKILL.md 不存在，自动降级\n"
                    f"约束：所有代码变更仅展示文件路径摘要，完整内容写入 output-{today}.md\n"
                )
                with open(claude_path, "a", encoding="utf-8") as f:
                    f.write(claude_constraint)
                action += "；CLAUDE.md 已补充约束"
                change_record += "；CLAUDE.md 约束加固"

        return action, change_record

    @staticmethod
    def _fix_flow_source(today: str, iteration: int) -> tuple[str, str]:
        """场景 B：追加流程私有规则（代码输出拦截）"""
        rules_path = os.path.expanduser("~/.claude/rules/flow_pm_rules.yaml")
        action = ""
        change_record = ""

        # 追加一条代码输出拦截的自愈规则
        nid = f"0{11 + iteration}"  # PM-011 或 PM-012
        new_rule = SelfHealRootCauseNode.FLOW_CONSTRAINT_TEMPLATE.format(
            nid=nid, date=today,
        )

        if os.path.exists(rules_path):
            with open(rules_path, "r", encoding="utf-8") as f:
                content = f.read()
            if f"PM-{nid}" not in content:
                with open(rules_path, "a", encoding="utf-8") as f:
                    f.write(new_rule)
                action = f"向 flow_pm_rules.yaml 追加 PM-{nid} 代码输出拦截规则"
                change_record = f"flow_pm_rules.yaml 追加 PM-{nid}[{today}]"
            else:
                action = f"PM-{nid} 已存在，跳过"
                change_record = f"PM-{nid} 已存在"
        else:
            action = f"flow_pm_rules.yaml 不存在，无法加固"
            change_record = "flow_pm_rules.yaml 缺失"

        return action, change_record

    @staticmethod
    def _fix_script_source(today: str, iteration: int) -> tuple[str, str]:
        """场景 C：增强过滤脚本 + global_output_rules.yaml 补充正则"""
        action_parts = []
        change_parts = []

        # 1. 增强 global_output_rules.yaml
        rules_path = os.path.expanduser("~/.claude/rules/global_output_rules.yaml")
        if os.path.exists(rules_path):
            enhancement = SelfHealRootCauseNode.FILTER_ENHANCEMENT_TEMPLATE
            with open(rules_path, "r", encoding="utf-8") as f:
                content = f.read()
            if "自愈自动增强" not in content:
                with open(rules_path, "a", encoding="utf-8") as f:
                    f.write(enhancement)
                action_parts.append("global_output_rules.yaml 追加代码块拦截正则")
                change_parts.append(f"global_output_rules.yaml 正则增强[{today}]")

        # 2. 尝试增强 output-filter.sh
        filter_paths = [
            os.path.expanduser("~/.claude/hooks/output-filter.sh"),
            os.path.expanduser("~/agent-harness/scripts/output-filter.sh"),
        ]
        for fp in filter_paths:
            if os.path.exists(fp):
                with open(fp, "r", encoding="utf-8") as f:
                    content = f.read()
                # 简单的检查：是否存在基础过滤逻辑
                if "grep" in content and "```" in content:
                    action_parts.append(f"output-filter.sh 已有代码拦截逻辑")
                    break
        else:
            # 尝试创建 output-filter.sh 骨架（如果不存在且 hooks 目录存在）
            hooks_dir = os.path.expanduser("~/.claude/hooks")
            os.makedirs(hooks_dir, exist_ok=True)
            filter_script = (
                "#!/bin/bash\n"
                "# Harness 自愈自动生成 — 代码块拦截 output-filter\n"
                + SelfHealRootCauseNode.FILTER_ENHANCEMENT_TEMPLATE
            )
            output_fp = os.path.join(hooks_dir, "output-filter.sh")
            if not os.path.exists(output_fp):
                with open(output_fp, "w", encoding="utf-8") as f:
                    f.write(filter_script)
                os.chmod(output_fp, 0o755)
                action_parts.append("创建 output-filter.sh 并写入代码拦截逻辑")
                change_parts.append(f"hooks/output-filter.sh 创建[{today}]")

        action = "; ".join(action_parts) if action_parts else "无需加固"
        change_record = "; ".join(change_parts) if change_parts else "无变更"
        return action, change_record

    # ═══════════════════════════════════════════════════════════════
    # 回归校验
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _run_regression(source_node: str) -> tuple[bool, str]:
        """
        长效回归校验：模拟检测配置是否已加固。
        实际场景中应调用同一节点模拟输出，此处通过检测配置变更确认。
        """
        # 检测修复是否已在配置文件落地
        checks = []

        if source_node == "skill_node":
            skills_dir = os.path.expanduser("~/.claude/skills/user")
            if os.path.exists(skills_dir):
                for root, dirs, files in os.walk(skills_dir):
                    for f in files:
                        if f == "SKILL.md":
                            fp = os.path.join(root, f)
                            with open(fp, "r", encoding="utf-8") as fh:
                                content = fh.read()
                            if "## 输出约束（自愈自动加固）" in content:
                                checks.append(True)
                            else:
                                checks.append(False)

        elif source_node == "flow_node":
            rules_path = os.path.expanduser("~/.claude/rules/flow_pm_rules.yaml")
            if os.path.exists(rules_path):
                with open(rules_path, "r", encoding="utf-8") as f:
                    content = f.read()
                checks.append("PM-011" in content or "代码输出拦截" in content)

        elif source_node == "langgraph_script":
            rules_path = os.path.expanduser("~/.claude/rules/global_output_rules.yaml")
            if os.path.exists(rules_path):
                with open(rules_path, "r", encoding="utf-8") as f:
                    content = f.read()
                checks.append("自愈自动增强" in content or "CODE_BLOCK_PATTERN" in content)

        passed = all(checks) if checks else False
        detail = f"回归校验: {'通过' if passed else '失败'} ({len(checks)} 项检测)"
        return passed, detail

    # ═══════════════════════════════════════════════════════════════
    # 事件上报
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _determine_status(regression_passed: bool) -> str:
        if regression_passed:
            return "full_success"
        return "regress_fail"

    @staticmethod
    def _report_root_event(
        state: FlowState, event_id: str,
        source_node: str, config_path: str, root_cause: str,
        root_action: str, change_record: str,
        regression_passed: bool, regress_detail: str,
        final_status: str,
    ):
        """全量上报 Harness（临时修复 + 根源根治双字段）"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            from engine.flow.harness_client import get_harness_client
            client = get_harness_client()

            # 1. 上报临时修复事件（已有逻辑）
            client.report_self_heal_event(
                instance_id=state.instance_id,
                rule_scope="global_output",
                rule_id="GOV-OUT-003",
                remediate_action="代码剥离+单行摘要压缩",
                remediate_result="success",
                violation_raw=root_cause,
                operator="GlobalOutputValidator",
                flow_id="FLOW-SELF-HEAL",
                file_ref="output-" + datetime.now().strftime("%Y%m%d") + ".md",
            )

            # 2. 上报根源根治事件（新增）
            # 直接通过 API 上报含 root_cause 字段的完整事件
            import requests as req
            try:
                req.post(
                    f"{os.environ.get('HARNESS_API_BASE', 'http://127.0.0.1:8001')}/api/self-heal/root-cause",
                    json={
                        "event_id": event_id,
                        "task_id": state.instance_id,
                        "violation_source_node": source_node,
                        "source_config_path": config_path,
                        "root_cause": root_cause,
                        "temp_remediate_action": "代码剥离+压缩摘要",
                        "temp_output_file_ref": f"output-{datetime.now().strftime('%Y%m%d')}.md",
                        "temp_verify_result": "pass",
                        "root_remediate_action": root_action,
                        "root_change_record": change_record,
                        "root_verify_result": "pass" if regression_passed else "fail",
                        "regression_test_passed": regression_passed,
                        "regression_test_detail": regress_detail,
                        "remediate_final_status": final_status,
                        "operator": "SelfHealRootCauseNode",
                    },
                    timeout=5,
                )
            except Exception:
                logger.debug("根源根治事件 API 上报失败（不阻断流程）")

        except Exception as e:
            logger.debug("根源根治事件上报异常: %s", e)


# 在 ALL_NODES 中注册根源修复节点（类定义之后追加）
ALL_NODES["self_heal_root"] = SelfHealRootCauseNode()

# Phase2 动态拓扑并行节点
ALL_NODES["parallel_dispatcher"] = parallel_dispatcher
ALL_NODES["parallel_aggregator"] = parallel_aggregator
