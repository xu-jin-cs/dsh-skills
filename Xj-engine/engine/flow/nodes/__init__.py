"""流程节点包：2026-09-13 自原平台节点模块迁入 Xj-engine，并新增 CUSTOM_AGENT 节点。

【冻结注记 · 2026-11-04】本包随 nodes.py 冻结（FROZEN-2026-11-04，声明见
nodes.py 头部）：headless 备用通道资产，停止新特性，仅缺陷修复单向自宿主回填；
ALL_NODES 注册表完整性由 tests/test_nodes_registry.py 金样本守护。
"""

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
