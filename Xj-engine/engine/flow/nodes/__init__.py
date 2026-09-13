"""LangGraph 节点包：复用原 backend.langgraph.nodes 模块并新增 CUSTOM_AGENT 节点。"""

from engine.flow.nodes.nodes import (  # noqa
    PMNode, SPMNode, DPMNode, UIDesignerNode,
    TestCaseDesignerNode, FrontendDevNode, BackendDevNode,
    TestExecutorNode, TestSupervisorNode, CodeReviewNode,
    OpsDeployNode, AcceptanceNode, RetrospectiveNode,
    SVSupervisorNode,
    InputHookNode, DeepSeekInferNode, OutputHookNode,
    SnapshotBackupNode, SnapshotRestoreNode, ContextCompressNode,
    PauseNode, ResumeNode,
    SkillGateCheckNode, FlowRuleValidatorNode, GlobalOutputValidatorNode,
    SelfHealRootCauseNode,
    ALL_NODES,
    NodeFn,
)

try:  # 宿主集成件（HOST-ONLY）：无宿主环境降级为 None（2026-09-13 钩子化）
    from engine.flow.nodes.custom_agent_node import (  # noqa
        custom_agent_node,
        custom_agent_subgraph,
    )
except Exception:  # noqa: BLE001
    custom_agent_node = None
    custom_agent_subgraph = None

__all__ = [
    "PMNode", "SPMNode", "DPMNode", "UIDesignerNode",
    "TestCaseDesignerNode", "FrontendDevNode", "BackendDevNode",
    "TestExecutorNode", "TestSupervisorNode", "CodeReviewNode",
    "OpsDeployNode", "AcceptanceNode", "RetrospectiveNode",
    "SVSupervisorNode",
    "InputHookNode", "DeepSeekInferNode", "OutputHookNode",
    "SnapshotBackupNode", "SnapshotRestoreNode", "ContextCompressNode",
    "PauseNode", "ResumeNode",
    "SkillGateCheckNode", "FlowRuleValidatorNode", "GlobalOutputValidatorNode",
    "SelfHealRootCauseNode",
    "ALL_NODES", "NodeFn",
    "custom_agent_node", "custom_agent_subgraph",
]
