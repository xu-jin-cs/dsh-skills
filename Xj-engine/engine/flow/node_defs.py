"""
LangGraph 节点元数据定义（Phase2 动态拓扑并行）。

原则：
  1. 只声明依赖，不改动节点执行源码。
  2. 新增 Agent 只需补充 FlowNodeMeta，调度逻辑无需修改。
"""

from pydantic import BaseModel
from typing import List


class FlowNodeMeta(BaseModel):
    node_key: str
    display_name: str
    # 强依赖：必须全部完成，当前节点才能启动
    depends_on: List[str]
    # 产出交付物标识（用于未来扩展依赖推导，本期配套预留）
    produces: List[str] = []


# ========= 开发流程节点元数据定义 =========
NODE_META_MAP: dict[str, FlowNodeMeta] = {
    "pending": FlowNodeMeta(
        node_key="pending",
        display_name="待启动",
        depends_on=[],
        produces=["instance_init"],
    ),
    "pm": FlowNodeMeta(
        node_key="pm",
        display_name="项目经理",
        depends_on=["pending"],
        produces=["project_plan"],
    ),
    "spm": FlowNodeMeta(
        node_key="spm",
        display_name="大产品经理",
        depends_on=["pm"],
        produces=["prd_doc"],
    ),
    "dpm": FlowNodeMeta(
        node_key="dpm",
        display_name="细节产品经理",
        depends_on=["spm"],
        produces=["interaction_doc"],
    ),
    # 并行区间节点：DPM 完成后可同时启动
    "ui_designer": FlowNodeMeta(
        node_key="ui_designer",
        display_name="界面设计Agent",
        depends_on=["dpm"],
        produces=["ui_spec", "layout_artifact"],
    ),
    "tcd": FlowNodeMeta(
        node_key="tcd",
        display_name="测试用例设计Agent",
        depends_on=["dpm"],
        produces=["test_case"],
    ),
    "be": FlowNodeMeta(
        node_key="be",
        display_name="后端开发Agent",
        depends_on=["dpm"],
        produces=["api_schema", "db_ddl", "backend_source"],
    ),
    "fe": FlowNodeMeta(
        node_key="fe",
        display_name="前端开发Agent",
        depends_on=["dpm", "ui_designer"],
        produces=["frontend_source"],
    ),
    "material_gen": FlowNodeMeta(
        node_key="material_gen",
        display_name="ComfyUI素材生成Agent",
        depends_on=["dpm"],
        produces=["ui_material"],
    ),
    "pm_confirm": FlowNodeMeta(
        node_key="pm_confirm",
        display_name="PM确认",
        depends_on=["ui_designer", "be", "fe", "material_gen"],
        produces=["pm_accept_signature"],
    ),
    # 后续串行节点（保留完整元数据）
    "executor_smoke": FlowNodeMeta(
        node_key="executor_smoke",
        display_name="冒烟测试",
        depends_on=["pm_confirm"],
        produces=["smoke_test_report"],
    ),
    "supervisor_pre": FlowNodeMeta(
        node_key="supervisor_pre",
        display_name="测试用例审核",
        depends_on=["executor_smoke"],
        produces=["test_audit_pre"],
    ),
    "executor_full": FlowNodeMeta(
        node_key="executor_full",
        display_name="全量测试",
        depends_on=["supervisor_pre"],
        produces=["full_test_report"],
    ),
    "supervisor_post": FlowNodeMeta(
        node_key="supervisor_post",
        display_name="执行审计",
        depends_on=["executor_full"],
        produces=["test_audit_post"],
    ),
    "code_review": FlowNodeMeta(
        node_key="code_review",
        display_name="代码审查",
        depends_on=["supervisor_post"],
        produces=["code_review_report"],
    ),
    "ops": FlowNodeMeta(
        node_key="ops",
        display_name="运维部署",
        depends_on=["code_review"],
        produces=["deploy_report"],
    ),
    "qa": FlowNodeMeta(
        node_key="qa",
        display_name="验收经理",
        depends_on=["ops"],
        produces=["acceptance_report"],
    ),
    "retro": FlowNodeMeta(
        node_key="retro",
        display_name="复盘",
        depends_on=["qa"],
        produces=["retro_report"],
    ),
}

# 并行区间边界
PARALLEL_START_NODE = "dpm"
PARALLEL_END_NODE = "pm_confirm"

# 本期实际接入并行调度的节点（material_gen 预留，暂不接入现有 14 步图）
_PARALLEL_ZONE_KEYS = ["ui_designer", "tcd", "be", "fe"]


def get_all_parallel_zone_nodes() -> List[FlowNodeMeta]:
    """获取并行区间内所有参与动态调度的节点。"""
    return [NODE_META_MAP[k] for k in _PARALLEL_ZONE_KEYS if k in NODE_META_MAP]


def get_node_meta(node_key: str) -> FlowNodeMeta | None:
    return NODE_META_MAP.get(node_key)
