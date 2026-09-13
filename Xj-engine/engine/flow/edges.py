"""
LangGraph Edges — 条件流转分支（流程控制器）。

设计原则：
  1. Edge 读取 State 里的门禁标记、测试结果、缺陷等级，自动决定下一步
  2. 非法跳转阻断 — 未完成测试不许部署、P0 缺陷直接回流修复
  3. 普通线性边 — 按序流转；条件判断边 — 读取 State 做分支
  4. 每种 Edge 是纯函数：输入 State → 输出 (from_node, to_node, reason)
"""

from typing import Optional
from engine.flow.state import FlowState, FlowStatus, BugLevel

# 路由结果
EdgeResult = tuple[str, Optional[str], str]
# (from_node_key, to_node_key, reason)


# ═══════════════════════════════════════════════════════════════
# GATE_BRIDGE_CHECKLIST 模板
# ═══════════════════════════════════════════════════════════════

CHECKLIST_TEMPLATE = {
    "1️⃣ PRD验收标准覆盖率": {
        "覆盖率": "0%（阈值：≥95%）",
        "用例ID映射表": "待补充",
        "未覆盖条款": "待分析",
    },
    "2️⃣ 自测报告真实性": {
        "自测通过率": "待检查",
    },
    "3️⃣ 代码审查质量": {
        "阻塞级Bug数": "0（阈值：0）",
    },
    "4️⃣ Bug根因分析质量（如适用）": {
        "使用5-Whys模板": "待确认",
        "根因归因": "禁止出现模糊归因",
    },
    "5️⃣ 交叉执行合规": {
        "designer ≠ executor": "待验证",
        "executor ≠ supervisor": "待验证",
        "时间间隔 > 30分钟": "待检查",
    },
}


# ═══════════════════════════════════════════════════════════════
# Phase2 并行区间条件边
# ═══════════════════════════════════════════════════════════════

def edge_parallel_dispatcher_route(state: FlowState) -> EdgeResult:
    """parallel_dispatcher 后条件路由。"""
    status = state.current_status
    if status == FlowStatus.EXIT_PARALLEL_ZONE:
        return ("parallel_dispatcher", "pm_confirm", "并行区间无就绪节点，进入 PM 确认")
    if status == FlowStatus.FROZEN:
        return ("parallel_dispatcher", "frozen", f"并行分支失败，流程冻结: {state.freeze_reason}")
    return ("parallel_dispatcher", "parallel_aggregator", "分支已分发，等待聚合")


def edge_parallel_aggregator_route(state: FlowState) -> EdgeResult:
    """parallel_aggregator 后条件路由。"""
    status = state.current_status
    if status == FlowStatus.EXIT_PARALLEL_ZONE:
        return ("parallel_aggregator", "pm_confirm", "全部分支完成，进入 PM 确认")
    if status == FlowStatus.SCAN_NEXT_BATCH:
        return ("parallel_aggregator", "parallel_dispatcher", "发现下一批可并行节点，继续扫描")
    if status == FlowStatus.FROZEN:
        return ("parallel_aggregator", "frozen", f"并行分支失败，流程冻结: {state.freeze_reason}")
    return ("parallel_aggregator", "parallel_aggregator", "仍有分支未完成，继续聚合")


# ═══════════════════════════════════════════════════════════════
# 条件判断边
# ═══════════════════════════════════════════════════════════════

def edge_after_smoke_test(state: FlowState) -> EdgeResult:
    """
    冒烟测试完后条件路由：
    - 存在 P0 缺陷 → BUG_FIX（流程B）
    - 全部通过 → FULL_TEST（流程A继续）
    """
    if state.smoke_test is None:
        return ("executor", "supervisor_pre", "冒烟测试数据为空，跳过 P0 判定，进入全量测试准备")

    if state.smoke_test.has_p0:
        return ("executor", "bug_fix",
                f"冒烟测试发现 P0 缺陷（{state.smoke_test.fail_count} 个失败），触发流程B Bug修复")

    return ("executor", "supervisor_pre",
            f"冒烟测试全部通过（{state.smoke_test.pass_count}/{state.smoke_test.total_steps}），进入全量测试准备")


def edge_after_supervisor_pre_full(state: FlowState) -> EdgeResult:
    """全量测试前 supervisor 审核门禁"""
    if state.violations and state.total_points >= 3:
        return ("supervisor", "frozen",
                f"违规积分 {state.total_points} ≥ 3，流程冻结，需 sv-supervisor 解除")
    return ("supervisor", "executor_full", "审核通过，进入全量测试")


def edge_after_full_test(state: FlowState) -> EdgeResult:
    """
    全量测试完后条件路由：
    - 存在 P0/P1 缺陷 → BUG_FIX
    - 全部通过 → CODE_REVIEW
    """
    if state.full_test is None:
        return ("executor", "supervisor_post", "全量测试数据为空，跳过缺陷判定，进入执行审计")

    if state.full_test.has_p0:
        return ("executor", "bug_fix",
                f"全量测试发现 P0 缺陷（{state.full_test.fail_count} 个失败），回流修复")
    if state.full_test.has_p1:
        return ("executor", "bug_fix",
                f"全量测试发现 P1 缺陷，回流修复")

    return ("executor", "supervisor_post",
            f"全量测试通过（{state.full_test.pass_count}/{state.full_test.total_steps}），进入执行审计")


def edge_after_supervisor_post_full(state: FlowState) -> EdgeResult:
    """全量测试后 supervisor 执行审计门禁"""
    # 检查是否存在证据链问题
    evidence_issues = [
        v for v in state.violations
        if v.violation_type.value in ("EVIDENCE_CHEAT",)
    ]
    if evidence_issues:
        return ("supervisor", "frozen", f"证据链异常：{evidence_issues[0].description}")

    return ("supervisor", "code_review", "执行审计通过，进入代码审查")


def edge_after_code_review(state: FlowState) -> EdgeResult:
    """
    代码审查后条件路由：
    - 审查未通过 → 回流修复
    - 通过 → 检查 allow_deploy → DEPLOY
    """
    if not state.code_review_passed:
        return ("code_review", "bug_fix", "代码审查未通过，回流修复")

    if not state.allow_deploy:
        return ("code_review", "frozen",
                "代码审查通过但 allow_deploy=False，检查测试报告完整性")

    return ("code_review", "ops", "代码审查通过，进入部署")


def edge_after_deploy(state: FlowState) -> EdgeResult:
    """部署后验收路由"""
    return ("ops", "qa", "部署完成，进入验收")


def edge_after_acceptance(state: FlowState) -> EdgeResult:
    """
    验收后条件路由：
    - 不通过 → 回流修复
    - 通过 → 复盘结项
    """
    if not state.acceptance_passed:
        return ("qa", "bug_fix", "验收不通过，回流修复")

    return ("qa", "retro", "验收通过，进入复盘结项")


def edge_after_retro(state: FlowState) -> EdgeResult:
    """复盘后结项"""
    return ("retro", "__end__", "复盘完成，项目结项")


# ═══════════════════════════════════════════════════════════════
# Bug 修复循环边
# ═══════════════════════════════════════════════════════════════

def edge_bug_fix_loop(state: FlowState) -> EdgeResult:
    """
    Bug 修复循环控制：
    - 0 轮 → 首次修复后回归
    - 1 轮 → 二次修复后回归
    - ≥2 轮 → 触发根因分析，冻结流程
    """
    state.bug_fix_rounds += 1

    if state.bug_fix_rounds >= 3:
        return ("bug_fix", "frozen",
                f"Bug 修复已进行 {state.bug_fix_rounds} 轮仍未关闭，触发根因分析，流程冻结等待 sv-supervisor 裁决")

    target_status = None
    if state.current_status in (FlowStatus.SMOKE_TEST,):
        target_status = "smoke_test"
    elif state.current_status in (FlowStatus.FULL_TEST, FlowStatus.CODE_REVIEW):
        target_status = "full_test"
    elif state.current_status in (FlowStatus.ACCEPTANCE, FlowStatus.DEPLOY):
        target_status = "deploy"
    else:
        target_status = "pm"

    return ("bug_fix", target_status,
            f"Bug 修复第 {state.bug_fix_rounds} 轮完成后回归")


# ═══════════════════════════════════════════════════════════════
# SV-Supervisor 后置审计边
# ═══════════════════════════════════════════════════════════════

def edge_sv_audit(state: FlowState) -> EdgeResult:
    """
    sv-supervisor 后置审计路由：
    - 审计通过 → 继续下一节点
    - 审计不通过 → 冻结
    """
    sv_verdict = state.metadata.get("sv_verdict", "APPROVED")
    if sv_verdict != "APPROVED":
        return ("sv", "frozen", f"sv-supervisor 审计未通过：{sv_verdict}")

    return ("sv", None, "sv-supervisor 审计通过，继续流转")


# ═══════════════════════════════════════════════════════════════
# 线性流转边（无分支，按序前进）
# ═══════════════════════════════════════════════════════════════

# 标准流程线性边（来自 state_machine.py ORDERED_SEQUENCE）
# 增量优化202607：各业务节点前插入 SV 前置审计通道
# Phase2 改造：DPM 完成后进入 parallel_dispatcher；parallel_aggregator 完成后进入 pm_confirm
LINEAR_EDGES = [
    # PM → SPM 经过 SV 审计
    ("pm", "sv_pre_spm", "项目初始化完成 → SV 前置审计 SPM"),
    ("sv_pre_spm", "spm", "SV 前置审计通过，进入需求分析"),
    # SPM → DPM 经过 SV 审计
    ("spm", "sv_pre_dpm", "PRD 确认完成 → SV 前置审计 DPM"),
    ("sv_pre_dpm", "dpm", "SV 前置审计通过，进入交互设计"),
    # DPM → 并行 Dispatcher
    ("dpm", "parallel_dispatcher", "交互文档完成，进入并行调度"),
    # 并行 Aggregator → PM 确认
    ("parallel_aggregator", "pm_confirm", "并行分支全部完成，进入 PM 确认"),
    # PM 确认 → 测试（经过 SV 审计）
    ("pm_confirm", "executor_smoke", "PM 确认通过，进入冒烟测试"),
    # 以下节点通过条件边处理
    # executor_smoke → 条件边 edge_after_smoke_test
    # supervisor_pre_full → 条件边 edge_after_supervisor_pre_full
    # executor_full → 条件边 edge_after_full_test
    # supervisor_post_full → 条件边 edge_after_supervisor_post_full
    # code_review → 条件边 edge_after_code_review
    # deploy → 条件边 edge_after_deploy
    # qa → 条件边 edge_after_acceptance
    # retro → __end__
]


# ═══════════════════════════════════════════════════════════════
# 治理流程条件边
# ═══════════════════════════════════════════════════════════════

def edge_gov_compress_route(state: FlowState) -> EdgeResult:
    """
    治理压缩后条件路由：
    need_deepseek_forward=True（代码任务） → 转入 pm 业务流程节点
    need_deepseek_forward=False（纯咨询） → 流程结束
    """
    if state.need_deepseek_forward:
        return ("gov_compress", "pm",
                "治理子图完成 → need_deepseek_forward=True，转入业务流程")

    return ("gov_compress", "__end__",
            "治理子图完成 → need_deepseek_forward=False，流程结束（纯咨询）")


def edge_rollback_route(state: FlowState) -> EdgeResult:
    """
    回滚分流边：need_rollback=True → 跳转 SnapshotRestoreNode → END
    need_rollback=False → 正常流转至 DeepSeekInferNode
    """
    if state.need_rollback:
        return ("gov_input", "gov_restore",
                "回滚指令检测 → 跳转快照回滚节点，跳过 DeepSeek 推理")

    return ("gov_input", "gov_infer",
            "正常输入 → 进入 DeepSeek 治理推理节点")


# ═══════════════════════════════════════════════════════════════
# 治理流程线性边（子图 GovernanceSubGraph 内部流转）
# ═══════════════════════════════════════════════════════════════

GOVERNANCE_EDGES = [
    ("gov_input", "gov_infer", "原始输入就绪 → 进入 DeepSeek 推理"),
    ("gov_infer", "gov_output", "治理 JSON 解析完成 → 输出落地"),
    ("gov_output", "gov_snapshot", "文件缓存同步完成 → 快照备份"),
    ("gov_snapshot", "gov_compress", "快照完成 → 压缩"),
]

# 增量优化202607：治理到业务的线性边 — 经过 SV 前置审计
GOVERNANCE_TO_BUSINESS_EDGES = [
    ("gov_compress", "sv_pre_pm", "治理压缩完成 → SV 前置审计 PM"),
    ("sv_pre_pm", "pm", "SV 前置审计通过，进入 PM 节点"),
]


# ═══════════════════════════════════════════════════════════════
# 增量优化202607：SV 前置审计条件边（需求/开发阶段实时阻断）
# ═══════════════════════════════════════════════════════════════

def edge_sv_pre_audit_pm(state: FlowState) -> EdgeResult:
    """PM 节点前置 SV 审计"""
    sv_verdict = state.metadata.get("sv_pre_audit", {}).get("pm", {}).get("verdict", "APPROVED")
    if sv_verdict != "APPROVED":
        reason = state.metadata.get("sv_pre_audit", {}).get("pm", {}).get("reason", "SV 前置审计未通过")
        return ("sv", "frozen", f"SV PM 前置审计: {reason}")
    return ("sv", "pm", "SV 前置审计通过，进入 PM 节点")


def edge_sv_pre_audit_spm(state: FlowState) -> EdgeResult:
    """SPM 节点前置 SV 审计"""
    sv_verdict = state.metadata.get("sv_pre_audit", {}).get("spm", {}).get("verdict", "APPROVED")
    if sv_verdict != "APPROVED":
        reason = state.metadata.get("sv_pre_audit", {}).get("spm", {}).get("reason", "SV 前置审计未通过")
        return ("sv", "frozen", f"SV SPM 前置审计: {reason}")
    return ("sv", "spm", "SV 前置审计通过，进入 SPM 节点")


def edge_sv_pre_audit_dpm(state: FlowState) -> EdgeResult:
    """DPM 节点前置 SV 审计"""
    sv_verdict = state.metadata.get("sv_pre_audit", {}).get("dpm", {}).get("verdict", "APPROVED")
    if sv_verdict != "APPROVED":
        reason = state.metadata.get("sv_pre_audit", {}).get("dpm", {}).get("reason", "SV 前置审计未通过")
        return ("sv", "frozen", f"SV DPM 前置审计: {reason}")
    return ("sv", "dpm", "SV 前置审计通过，进入 DPM 节点")


def edge_sv_pre_audit_fe(state: FlowState) -> EdgeResult:
    """FE 节点前置 SV 审计"""
    sv_verdict = state.metadata.get("sv_pre_audit", {}).get("fe", {}).get("verdict", "APPROVED")
    if sv_verdict != "APPROVED":
        reason = state.metadata.get("sv_pre_audit", {}).get("fe", {}).get("reason", "SV 前置审计未通过")
        return ("sv", "frozen", f"SV FE 前置审计: {reason}")
    return ("sv", "fe", "SV 前置审计通过，进入 FE 节点")


def edge_sv_pre_audit_be(state: FlowState) -> EdgeResult:
    """BE 节点前置 SV 审计"""
    sv_verdict = state.metadata.get("sv_pre_audit", {}).get("be", {}).get("verdict", "APPROVED")
    if sv_verdict != "APPROVED":
        reason = state.metadata.get("sv_pre_audit", {}).get("be", {}).get("reason", "SV 前置审计未通过")
        return ("sv", "frozen", f"SV BE 前置审计: {reason}")
    return ("sv", "be", "SV 前置审计通过，进入 BE 节点")


# Edge 注册表增量 — SV 前置审计边名称列表
SV_PRE_AUDIT_EDGES: dict[str, str] = {
    "sv_pre_pm": "pm",
    "sv_pre_spm": "spm",
    "sv_pre_dpm": "dpm",
    "sv_pre_fe": "fe",
    "sv_pre_be": "be",
}


# ═══════════════════════════════════════════════════════════════
# Edge 注册表
# ═══════════════════════════════════════════════════════════════

CONDITIONAL_EDGES: dict[str, callable] = {
    "smoke_after": edge_after_smoke_test,
    "supervisor_pre": edge_after_supervisor_pre_full,
    "full_after": edge_after_full_test,
    "supervisor_post": edge_after_supervisor_post_full,
    "code_review_after": edge_after_code_review,
    "deploy_after": edge_after_deploy,
    "acceptance_after": edge_after_acceptance,
    "retro_after": edge_after_retro,
    "bug_fix_loop": edge_bug_fix_loop,
    "sv_audit": edge_sv_audit,
    # 治理流程条件边
    "rollback_route": edge_rollback_route,
    "gov_compress_route": edge_gov_compress_route,
    # 增量优化202607：SV 前置审计边
    "sv_pre_pm": edge_sv_pre_audit_pm,
    "sv_pre_spm": edge_sv_pre_audit_spm,
    "sv_pre_dpm": edge_sv_pre_audit_dpm,
    "sv_pre_fe": edge_sv_pre_audit_fe,
    "sv_pre_be": edge_sv_pre_audit_be,
    # Phase2 并行区间路由边
    "parallel_dispatcher_route": edge_parallel_dispatcher_route,
    "parallel_aggregator_route": edge_parallel_aggregator_route,
}


def get_linear_next(from_node: str) -> Optional[str]:
    """获取线性流转的下一节点（合并业务边 + 治理边 + SV审计边）"""
    # 先查业务线性边
    for src, dst, _ in LINEAR_EDGES:
        if src == from_node:
            return dst
    # 再查治理线性边
    for src, dst, _ in GOVERNANCE_EDGES:
        if src == from_node:
            return dst
    # 再查治理到业务的SV审计边
    for src, dst, _ in GOVERNANCE_TO_BUSINESS_EDGES:
        if src == from_node:
            return dst
    return None
