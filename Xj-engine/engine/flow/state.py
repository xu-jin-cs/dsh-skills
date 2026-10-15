"""
LangGraph 统一全局状态容器（Pydantic）。

设计原则：
  1. 唯一数据源 — 所有 Node 只读写本 State，杜绝各自缓存、幻读
  2. 枚举约束 — 用 Enum 约束所有状态值，禁止随便写字符串
  3. 门禁控制布尔 — Edge 读取的门禁标记集中管理
  4. 可序列化 — 全部字段支持 model_dump_json()，用于 DB checkpoint
  5. 大文本不入 State — 文档/日志写入磁盘，State 只存 FilePathRef(path+md5)
  6. 版本可追溯 — config_version 统一管控全底层配置
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Set, Any
from enum import Enum
from datetime import datetime


# ═══════════════════════════════════════════════════════════════
# 文件引用标准结构体（替代所有大文本内联字段）
# ═══════════════════════════════════════════════════════════════

class FilePathRef(BaseModel):
    """文件引用 — 存路径+md5，不存原始大文本"""
    file_path: str                          # 文件本地绝对路径
    file_md5: str                           # 文件MD5哈希，用于校验篡改
    brief_summary: Optional[str] = None     # 百字内摘要（仅用于流程判断，不存全文）


# ═══════════════════════════════════════════════════════════════
# 枚举（统一约束状态值，禁止随便写字符串）
# ═══════════════════════════════════════════════════════════════

class FlowStatus(str, Enum):
    """流程生命周期状态——与 CLAUDE.md 流程 A 对齐"""
    PENDING = "PENDING"
    PRD_REVIEW = "PRD_REVIEW"
    DESIGN = "DESIGN"
    DEV_FRONTEND = "DEV_FRONTEND"
    DEV_BACKEND = "DEV_BACKEND"
    PM_CONFIRM = "PM_CONFIRM"
    SMOKE_TEST = "SMOKE_TEST"
    FULL_TEST = "FULL_TEST"
    CODE_REVIEW = "CODE_REVIEW"
    DEPLOY = "DEPLOY"
    ACCEPTANCE = "ACCEPTANCE"
    CLOSED = "CLOSED"
    # 异常状态
    FROZEN = "FROZEN"
    ROLLBACK = "ROLLBACK"
    # Phase2 并行区间内部路由状态
    WAIT_BRANCH_AGGREGATE = "WAIT_BRANCH_AGGREGATE"
    SCAN_NEXT_BATCH = "SCAN_NEXT_BATCH"
    EXIT_PARALLEL_ZONE = "EXIT_PARALLEL_ZONE"


class BugLevel(str, Enum):
    """缺陷等级——来自 CLAUDE.md 质量基线"""
    P0 = "P0"  # 核心业务流程崩溃、核心数据计算错误
    P1 = "P1"  # 接口逻辑不符、代码分支缺失、核心表单校验失效
    P2 = "P2"  # 次要交互 bug、非核心代码分支冗余
    P3 = "P3"  # 视觉样式细微偏差、不影响使用的提示文字问题


class NodeType(str, Enum):
    """LangGraph Node 类型——对应 CLAUDE.md 全部角色"""
    PM = "pm"                      # 项目经理
    SPM = "spm"                    # 大产品经理
    DPM = "dpm"                    # 细节产品经理
    UI_DESIGNER = "uid"            # 界面设计师
    TEST_CASE_DESIGNER = "tcd"     # 测试用例设计 Agent
    FRONTEND = "fe"                # 前端工程师
    BACKEND = "be"                 # 后端工程师
    TEST_EXECUTOR = "exec"         # 测试执行 Agent
    TEST_SUPERVISOR = "ts"         # 测试监督 Agent
    CODE_REVIEWER = "cr"           # 代码审查
    OPS = "ops"                    # 运维部署
    QA = "qa"                      # 验收经理
    RETROSPECTIVE = "retro"        # 复盘
    SV_SUPERVISOR = "sv"           # 独立监督者

    # 治理流程节点类型
    GOV_INPUT = "governance_input"      # 治理输入节点
    GOV_INFER = "governance_infer"      # 治理推理节点
    GOV_OUTPUT = "governance_output"    # 治理输出节点
    GOV_SNAPSHOT = "governance_snapshot"  # 治理快照节点
    GOV_RESTORE = "governance_restore"  # 治理回滚节点
    GOV_COMPRESS = "governance_compress"  # 治理压缩节点

    # 自愈模式节点类型
    SELF_HEAL_GATE = "self_heal_gate"          # SV门禁校验
    SELF_HEAL_FLOW = "self_heal_flow"          # 流程规则自愈
    SELF_HEAL_OUTPUT = "self_heal_output"      # 全局输出自愈
    SELF_HEAL_ROOT = "self_heal_root"          # 根源根治自愈


class DeliverableType(str, Enum):
    """交付物类型——与 validators.py VALIDATORS 对齐"""
    PRD_DOC = "prd_doc"
    INTERACTION_DOC = "interaction_doc"
    SELF_TEST_REPORT = "self_test_report"
    TEST_REPORT = "test_report"
    CODE_REVIEW_REPORT = "code_review_report"
    DEPLOY_REPORT = "deploy_report"
    ACCEPTANCE_REPORT = "acceptance_report"


class ViolationType(str, Enum):
    """违规类型"""
    SKIP_ATTEMPT = "SKIP_ATTEMPT"
    P0_BLOCKER = "P0_BLOCKER"
    INTERFACE_MISMATCH = "INTERFACE_MISMATCH"
    LOGIC_BLOCKER = "LOGIC_BLOCKER"
    EVIDENCE_CHEAT = "EVIDENCE_CHEAT"
    MANUAL_FREEZE = "MANUAL_FREEZE"
    COMPLIANCE_FAILURE = "COMPLIANCE_FAILURE"


# ═══════════════════════════════════════════════════════════════
# 子结构（仅由对应 Node/Integration 写入）
# ═══════════════════════════════════════════════════════════════

class DeliverableRecord(BaseModel):
    """交付物记录——与 models.Deliverable 对齐"""
    content_type: str
    summary: str
    agent_role: NodeType
    file_path: str = ""
    validated: bool = False
    validation_result: str = ""
    created_at: Optional[str] = None


class BugRecord(BaseModel):
    """缺陷记录——与 models.LogicVulnerability 对齐"""
    agent_role: str
    vulnerability_type: str  # business / code / interface / ui
    severity: BugLevel
    title: str
    description: str
    location: str = ""
    suggestion: str = ""
    resolved: bool = False
    created_at: Optional[str] = None


class ViolationRecord(BaseModel):
    """违规记录——与 models.Violation 对齐"""
    violation_type: ViolationType
    description: str
    resolved: bool = False
    created_at: Optional[str] = None


class TestResult(BaseModel):
    """测试结果——冒烟/全量测试共用"""
    batch_id: str = ""
    pass_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    total_steps: int = 0
    bug_list: List[BugRecord] = []
    has_p0: bool = False
    has_p1: bool = False
    evidence_checksum: str = ""
    summary: str = ""


class NodeExecution(BaseModel):
    """单次 Node 执行记录——用于审计追踪"""
    node_type: NodeType
    status: str = "pending"  # pending / running / passed / failed
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output_summary: str = ""
    duration_seconds: float = 0.0
    error: str = ""


# ═══════════════════════════════════════════════════════════════
# 全局统一 State
# ═══════════════════════════════════════════════════════════════

class FlowState(BaseModel):
    """
    全局统一 State——整个 LangGraph 流程的唯一数据源。

    所有 Node 只读写这个 State。Edge 只读 State 里的门禁标记做条件路由。
    大文本不入 State，全部存入磁盘文件，State 只存 FilePathRef(path+md5)。
    """

    # ─── 流程基础标识（创建时固定，不做修改） ──────────────────────
    instance_id: str = Field(description="harness 流程实例 ID，唯一断点标识")
    project_name: str = Field(description="项目名称")
    project_description: str = ""
    current_status: FlowStatus = Field(default=FlowStatus.PENDING)
    schema_version: int = Field(default=1, description="State schema 版本号，用于向前兼容加载旧版快照")

    # ─── 版本/配置引用（统一管控全底层约束） ─────────────────────
    config_version: str = Field(default="1.0.0", description="全局skill+流程门禁+校验规则统一版本")
    prompt_template_id: str = Field(default="pm/v1", description="当前任务主角色模板ID")
    prompt_config_version: str = Field(default="1.0.0", description="配套Prompt全局配置版本")

    # ─── 证据/日志文件引用 ─────────────────────────────────────────
    evidence_root_dir: str = Field(default="", description="当前任务证据根目录（instance_id专属文件夹）")
    audit_log_ref: Optional[FilePathRef] = Field(default=None, description="全链路审计总日志文件引用")

    # ─── 文档类：统一 FilePathRef，不存完整文本 ──────────────────
    prd_doc: Optional[FilePathRef] = None
    interaction_doc: Optional[FilePathRef] = None
    ui_spec: Optional[FilePathRef] = None
    code_output: Optional[FilePathRef] = None
    deploy_report: Optional[FilePathRef] = None
    acceptance_report: Optional[FilePathRef] = None

    # ─── 日志：分段文件，不存内联文本 ────────────────────────────
    error_log: List[str] = []

    # ─── 交付物记录列表（持久化用） ────────────────────────────────
    deliverables: List[DeliverableRecord] = []

    # ─── 测试结果（仅对应 Node 可写入） ──────────────────────────
    smoke_test: Optional[TestResult] = None
    full_test: Optional[TestResult] = None
    smoke_test_gate_passed: bool = False

    # ─── 缺陷列表（所有测试发现的缺陷汇总） ────────────────────────
    bugs: List[BugRecord] = []
    unresolved_bug_count: int = 0
    bug_fix_rounds: int = Field(default=0, description="Bug 修复轮次计数")

    # ─── 门禁控制布尔（Edge 条件路由核心依据） ─────────────────────
    allow_deploy: bool = Field(default=False, description="是否允许部署")
    skip_test_allowed: bool = Field(default=False, description="是否允许跳过全量测试")
    code_review_passed: bool = Field(default=False, description="代码审查是否通过")
    acceptance_passed: bool = Field(default=False, description="验收是否通过")

    # ─── 违规记录 ──────────────────────────────────────────────────
    violations: List[ViolationRecord] = []
    total_points: int = Field(default=0, description="累计违规积分")
    is_frozen: bool = Field(default=False, description="是否已冻结")
    freeze_reason: str = ""

    # ─── Node 执行追踪 ─────────────────────────────────────────────
    execution_trace: List[NodeExecution] = []

    # ─── Phase2 动态拓扑并行追踪 ───────────────────────────────────
    finished_nodes: Set[str] = Field(default_factory=set, description="并行区间内已完成节点key集合")
    active_branch_keys: Set[str] = Field(default_factory=set, description="当前正在运行的并行分支节点key集合")

    # ─── 时间元数据 ──────────────────────────────────────────────
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None

    # ─── 扩展字段（技能自定义数据） ────────────────────────────────
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # ─── 治理上下文字段（对接 input-filter.sh + DeepSeek 治理 JSON）─
    clean_input: Optional[str] = Field(default=None, description="过滤礼貌词后的精简需求")
    char_count: int = Field(default=0, description="原始中文字符总数")
    is_long_text: bool = Field(default=False, description="是否超长文本（>50中文）")
    temp_path: Optional[str] = Field(default=None, description="超长文本临时文件路径")
    need_deepseek_forward: bool = Field(default=False, description="是否需要DeepSeek推理：True=代码任务/False=纯咨询")
    show_summary: Optional[str] = Field(default=None, description="对话展示摘要")
    task_meta: Dict[str, Any] = Field(default_factory=dict, description="任务元数据(task_id/snapshot_id/change_file_count/total_line_change/file_detail)")
    full_content_embedded: bool = Field(default=False, description="是否违反输出隔离铁律：完整内容/代码已嵌入对话")

    # ─── 文件引用（大文本不入 State，存 FilePathRef path+md5） ──
    user_input_ref: Optional[FilePathRef] = Field(default=None, description="用户原始输入文件引用")
    model_output_ref: Optional[FilePathRef] = Field(default=None, description="模型完整输出文件引用")

    # ─── 缓存/日志路径绑定 ──────────────────────────────────────────
    temp_cache_dir: str = Field(default="./temp_input_cache", description="临时缓存目录路径")
    log_date_suffix: Optional[str] = Field(default=None, description="日志日期后缀(YYYYMMDD)")
    snapshot_root: str = Field(default="./.agent_backup", description="项目文件快照根目录")

    # ─── 治理流程标记 ────────────────────────────────────────────────
    need_rollback: bool = Field(default=False, description="回滚任务标记：input-filter检测到回滚指令时置为True")

    # ═══════════════════════════════════════════════════════════════
    # 便捷方法
    # ═══════════════════════════════════════════════════════════════

    def has_blocker_bugs(self) -> bool:
        """是否有阻断性缺陷（P0 或 P1 未解决）"""
        return any(b.severity in (BugLevel.P0, BugLevel.P1) and not b.resolved for b in self.bugs)

    def add_bug(self, bug: BugRecord) -> None:
        """添加缺陷记录并更新统计"""
        self.bugs.append(bug)
        if not bug.resolved:
            self.unresolved_bug_count += 1

    def resolve_bug(self, index: int) -> None:
        """按索引解决缺陷"""
        if 0 <= index < len(self.bugs) and not self.bugs[index].resolved:
            self.bugs[index].resolved = True
            self.unresolved_bug_count = max(0, self.unresolved_bug_count - 1)

    def record_node_execution(
        self, node_type: NodeType, status: str = "passed",
        summary: str = "", error: str = "",
    ) -> None:
        """记录 Node 执行状态"""
        now = datetime.utcnow().isoformat()
        exec_entry = NodeExecution(
            node_type=node_type,
            status=status,
            started_at=now,
            completed_at=now,
            output_summary=summary[:200],
            error=error,
        )
        self.execution_trace.append(exec_entry)
        self.updated_at = now

    def add_violation(
        self, vtype: ViolationType, description: str,
        points: int = 1,
    ) -> None:
        """添加违规记录"""
        self.violations.append(ViolationRecord(
            violation_type=vtype,
            description=description,
            created_at=datetime.utcnow().isoformat(),
        ))
        self.total_points += points

    def add_deliverable(
        self, content_type: str, summary: str,
        agent_role: NodeType, file_path: str = "",
        validated: bool = True,
    ) -> None:
        """记录交付物"""
        self.deliverables.append(DeliverableRecord(
            content_type=content_type,
            summary=summary,
            agent_role=agent_role,
            file_path=file_path,
            validated=validated,
            validation_result="通过" if validated else "待校验",
            created_at=datetime.utcnow().isoformat(),
        ))

    def model_dump_db_safe(self) -> dict:
        """导出可安全序列化到 DB 的字典（排除非必须字段）"""
        return self.model_dump(mode="json")

    @classmethod
    def from_db_restore(cls, data: dict) -> "FlowState":
        """从 DB checkpoint 恢复 State"""
        return cls.model_validate(data)
