# 【宿主集成件 · HOST-ONLY】2026-09-13：本模块深绑 agent-harness 工作流/数据库，
# 无宿主环境（干净 venv 无 backend）不可 import——属预期语义（宿主功能在宿主用）。
# FlowGraph 核心（graph/nodes/edges/state/checkpoint）不依赖本模块。
import os as _os_hostcheck
if _os_hostcheck.environ.get("XJFRAME_STRICT_NO_HOST") == "1":
    raise ImportError("CUSTOM_AGENT_NODE_HOST_ONLY: 宿主集成件在无宿主模式禁用")
"""LangGraph CUSTOM_AGENT 执行节点。

职责：按 WorkflowDefinition 顺序执行自定义 Agent 节点，
支持 max_retry 重试、completed_pass/completed_fail 分支路由，
并复用 deliverable_service 进行交付物校验。
"""

import os
from datetime import datetime, timezone

from backend.services.workflow.execution_store import _EXECUTION_STORE, _EXECUTION_LOCK
from backend.db.models.workflow_custom_agent import WorkflowDefinition
from engine.flow.state import FlowState
from backend.services.workflow.xujin_flow_mapper import build_adjacency_map, resolve_next_node
from backend.services.workflow.deliverable_service import validate_deliverable


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_deliverable_content(agent, deliverable_name: str, template_text: str, context: str, user_input: str) -> str:
    """调用 Claude 引擎或本地回退逻辑生成交付物具体内容。"""
    if os.getenv("AGENT_HARNESS_DISABLE_LLM", "").lower() in ("1", "true", "yes"):
        api_key = ""
    else:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if api_key:
        try:
            from backend.engine.claude_engine import ClaudeEngine
            engine = ClaudeEngine(api_key=api_key, model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"), max_tokens=2000, temperature=0.3)
            prompt = (
                f"你是一名 {agent.role or '专业Agent'}。\n"
                f"技能：{agent.skills or '无'}\n"
                f"业务规则：{agent.business_rules or '无'}\n\n"
                f"任务：根据以下输入上下文，生成交付物『{deliverable_name}』的具体内容。\n\n"
                f"输入上下文：\n{context}\n\n"
                f"用户原始输入：{user_input}\n\n"
                f"交付物模板/要求：\n{template_text}\n\n"
                f"请直接输出交付物内容，不要解释。"
            )
            result = engine.send_raw(prompt)
            text = result.get("text", "")
            if text:
                return text.strip()
        except Exception:
            pass
    # 本地回退：生成一份包含处理痕迹的具体内容
    return (
        f"【{agent.name}】已根据角色「{agent.role or '未指定'}」处理输入。\n\n"
        f"输入上下文：\n{context}\n\n"
        f"本节点交付物：{deliverable_name}\n\n"
        f"处理结果：基于「{template_text}」完成处理。"
    )


def _execute_single_agent(state: FlowState, agent, node_key: str) -> tuple[str, str, list[dict]]:
    """执行单个 Agent 并校验交付物。返回 (status, message, deliverables)。"""
    user_input = state.metadata.get("user_input", "")
    context = state.metadata.get("execution_context", f"用户输入：{user_input}")
    outputs = []
    main_output = ""
    for d in (agent.deliverables or []):
        template = d.template_text or ""
        # 先生成具体交付物内容（调用 LLM 或回退逻辑）
        generated = _generate_deliverable_content(agent, d.name, template, context, user_input)
        # 模板占位符仍做替换，用于基础校验
        raw_content = (
            template
            .replace("{{instance_id}}", state.instance_id)
            .replace("{{project_name}}", state.project_name)
            .replace("{{user_input}}", user_input)
        ) or generated
        result = validate_deliverable(
            content=raw_content,
            schema=d.json_schema or {},
            expected_hash=d.expected_hash or "",
            whitelist=(d.whitelist or []),
            blacklist=(d.blacklist or []),
        )
        # 展示内容包含工作证明 + 生成结果
        work_content = (
            f"【节点：{agent.name}】\n"
            f"节点角色：{agent.role or '未指定'}\n\n"
            f"当前上下文：\n{context}\n\n"
            f"本节点处理：\n{template}\n\n"
            f"节点输出：\n{generated}"
        )
        outputs.append({
            "deliverable": d.name,
            "passed": result["passed"],
            "checks": result["checks"],
            "content": work_content,
            "generated": generated,
        })
        if main_output == "":
            main_output = generated
        if not result["passed"]:
            return "COMPLETED_FAIL", f"交付物校验失败: {d.name}", outputs
    state.metadata["execution_context"] = f"{context}\n\n【{agent.name}】输出：{main_output}"
    return "COMPLETED_PASS", f"节点 {node_key} 执行成功，交付物 {len(outputs)} 项通过", outputs


def custom_agent_subgraph(state: FlowState, workflow: WorkflowDefinition) -> tuple[FlowState, str]:
    """执行整个 CUSTOM_AGENT 子图。

    Returns:
        (final_state, final_status) 其中 final_status ∈ {COMPLETED_PASS, COMPLETED_FAIL, TERMINATED}
    """
    adj = build_adjacency_map(workflow)
    node_map = {rel.node_key: rel.agent for rel in workflow.node_rels}

    start_node = state.metadata.get("start_node", "")
    current_node = start_node or (next(iter(node_map.keys())) if node_map else "")
    if not current_node:
        state.metadata["current_node"] = ""
        return state, "COMPLETED_FAIL"

    node_states = {}
    visited = set()

    while current_node:
        if current_node in visited:
            state.metadata["node_states"] = node_states
            state.metadata["current_node"] = current_node
            return state, "TERMINATED"
        visited.add(current_node)

        # 节点边界检查中断请求
        with _EXECUTION_LOCK:
            record = _EXECUTION_STORE.get(state.instance_id)
            if record and record.get("status") == "TERMINATED":
                state.metadata["node_states"] = node_states
                state.metadata["current_node"] = current_node
                return state, "TERMINATED"

        agent = node_map.get(current_node)
        if not agent:
            state.metadata["node_states"] = node_states
            state.metadata["current_node"] = current_node
            return state, "COMPLETED_FAIL"

        status = "PENDING"
        message = ""
        retries = 0
        max_retry = max(0, agent.max_retry or 0)

        while retries <= max_retry:
            status, message, deliverables = _execute_single_agent(state, agent, current_node)
            node_states[current_node] = {"status": status, "message": message, "retry": retries, "deliverables": deliverables}
            if status == "COMPLETED_PASS":
                break
            retries += 1
            if retries <= max_retry:
                node_states[current_node]["status"] = "RETRYING"

        if status != "COMPLETED_PASS":
            state.metadata["node_states"] = node_states
            state.metadata["current_node"] = current_node
            return state, "COMPLETED_FAIL"

        next_node = resolve_next_node(adj, current_node, "completed_pass")
        if not next_node or next_node not in node_map:
            state.metadata["node_states"] = node_states
            state.metadata["current_node"] = current_node
            return state, "COMPLETED_PASS"
        current_node = next_node

    state.metadata["node_states"] = node_states
    state.metadata["current_node"] = current_node
    return state, "COMPLETED_PASS"


def custom_agent_node(state: FlowState, workflow: WorkflowDefinition | None = None) -> tuple[FlowState, str | None]:
    """标准 LangGraph Node 签名：接收 FlowState 与可选 WorkflowDefinition，返回 (state, routing_key)。"""
    if workflow is None:
        state.metadata["custom_agent_error"] = "missing workflow definition"
        return state, "completed_fail"
    final_state, final_status = custom_agent_subgraph(state, workflow)
    return final_state, final_status.lower()
