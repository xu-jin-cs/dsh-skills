"""
LangGraph ↔ agent-harness 数据桥接层。

设计（来自全局融合方案 §7）：
  单一权威数据源：运行过程中唯一可信数据为 LangGraph State，
  Harness 仅做镜像备份。所有持久化通过 callback 机制异步上报。

数据流转链路：
  Node 执行 → FlowGraph.step()
    ├─ 1. 执行 Node（纯 State 操作，无 DB 依赖）
    ├─ 2. 保存本地 Checkpoint（第一优先级）
    ├─ 3. 触发回调 → HarnessClient HTTP 上报（第二优先级）
    └─ 4. Edge 条件路由 → 下一节点

本模块职责：
  1. state_to_json / json_to_state — State ↔ JSON（用于 checkpoint 序列化）
  2. assign_thread_id — 线程 ID 生成
  3. build_initial_state — 从 Harness DB 重建初始 State（阶段 3+ 启用）
  4. 向后兼容的 load_state_from_db / save_state_to_db — 保留签名但不推荐使用
"""

import json
import os
import uuid
from datetime import datetime
from typing import Optional

from engine.flow.state import (
    FlowState, FlowStatus, BugLevel, NodeType,
    BugRecord, DeliverableRecord, ViolationRecord, FilePathRef,
)
from engine.flow.file_utils import ensure_evidence_dirs


def state_to_json(state: FlowState) -> str:
    """FlowState → JSON 字符串（用于 checkpoint 序列化 / 批量导入）"""
    return state.model_dump_json(indent=2)


def json_to_state(json_str: str) -> FlowState:
    """JSON 字符串 → FlowState（用于 checkpoint 恢复 / Harness 导入）"""
    return FlowState.model_validate_json(json_str)


def assign_thread_id(project_name: str = "default") -> str:
    """
    生成全局唯一 thread_id。
    格式：lg_{project_short}_{uuid8}
    等价于 Harness instance_id。
    """
    short = project_name.lower().replace(" ", "_")[:12]
    suffix = uuid.uuid4().hex[:8]
    return f"lg_{short}_{suffix}"


def build_initial_state(
    instance_id: str,
    project_name: str,
    project_description: str = "",
    config_version: str = "1.0.0",
    prompt_template_id: str = "pm/v1",
    evidence_root: Optional[str] = None,
) -> FlowState:
    """
    构建初始 FlowState（新任务起点）。

    自动创建证据目录子结构。
    Args:
        config_version: skill+流程门禁+校验规则统一版本
        prompt_template_id: 主角色Prompt模板ID
        evidence_root: 证据根目录，默认 ./workspace/evidence/{instance_id}
    """
    now = datetime.utcnow().isoformat()
    evidence_root_dir = evidence_root or os.path.join(
        os.getcwd(), "workspace", "evidence", instance_id
    )
    ensure_evidence_dirs(evidence_root_dir)

    return FlowState(
        instance_id=instance_id,
        project_name=project_name,
        project_description=project_description,
        current_status=FlowStatus.PENDING,
        config_version=config_version,
        prompt_template_id=prompt_template_id,
        evidence_root_dir=evidence_root_dir,
        started_at=now,
        updated_at=now,
    )


# ═══════════════════════════════════════════════════════════════
# 向后兼容函数（保留签名，内容简化）
# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════
# 治理 JSON ↔ FlowState 双向转换
# ═══════════════════════════════════════════════════════════════

def json_to_state(governance_json: dict, state: FlowState) -> FlowState:
    """
    将 DeepSeek 输出的治理 JSON 块解析并填充到 FlowState 对应字段。

    仅填充轻量元数据，大文本由调用方通过 file_utils 写入后赋值 FilePathRef。
    """
    # 轻量元数据直接填充
    state.clean_input = governance_json.get("clean_input")
    state.char_count = governance_json.get("char_count", 0)
    state.is_long_text = governance_json.get("is_long_text", False)
    state.temp_path = governance_json.get("temp_path")
    state.need_deepseek_forward = governance_json.get("need_deepseek_forward", False)
    state.show_summary = governance_json.get("show_summary")
    state.task_meta = governance_json.get("task_meta", {})
    state.full_content_embedded = governance_json.get("full_content_embedded", False)
    return state


def state_to_file_cache(state: FlowState) -> dict:
    """
    将 FlowState 治理字段同步写入 temp_input_cache 临时文件，
    供 output-filter.sh 等原有文件 IO 逻辑读取。

    写入文件：
      _last_governance.json  — 完整治理 JSON（供外部进程消费）
      _last_state_meta.json  — State 轻量元数据快照

    Returns:
        {"governance_path": str, "meta_path": str} 或 {"error": str}
    """
    import hashlib

    cache_dir = state.temp_cache_dir or "./temp_input_cache"
    os.makedirs(cache_dir, exist_ok=True)

    # 构建治理 JSON
    gov_payload = {
        "clean_input": state.clean_input,
        "char_count": state.char_count,
        "is_long_text": state.is_long_text,
        "temp_path": state.temp_path,
        "need_deepseek_forward": state.need_deepseek_forward,
        "show_summary": state.show_summary,
        "task_meta": state.task_meta,
        "full_content_embedded": state.full_content_embedded,
    }

    gov_path = os.path.join(cache_dir, "_last_governance.json")
    with open(gov_path, "w", encoding="utf-8") as f:
        json.dump(gov_payload, f, ensure_ascii=False, indent=2)

    meta_path = os.path.join(cache_dir, "_last_state_meta.json")
    meta = {
        "instance_id": state.instance_id,
        "project_name": state.project_name,
        "current_status": state.current_status.value if hasattr(state.current_status, "value") else str(state.current_status),
        "clean_input": state.clean_input,
        "is_long_text": state.is_long_text,
        "char_count": state.char_count,
        "need_rollback": state.need_rollback,
        "snapshot_id": state.task_meta.get("snapshot_id"),
    }
    # ENG-046（2026-08-20 审计）：_last_state_meta.json 自诞生无消费者，删写点；
    # meta_path 仍随返回值透出（路径字符串），不再落盘。
    return {"governance_path": gov_path, "meta_path": meta_path}


def save_state_to_db(state: FlowState, db=None) -> None:
    """
    （已弃用）直接 SQLAlchemy 写入方式已由 callback → HTTP 替代。
    保留签名避免导入报错，内部仅做日志占位。
    新代码请使用 callback.harness_sync_callback() 或 harness_client.py。
    """
    import logging
    logger = logging.getLogger("langgraph.integration")
    logger.debug(
        "save_state_to_db 已弃用（instance=%s status=%s），"
        "持久化请使用 callback 机制",
        state.instance_id, state.current_status.value,
    )


def load_state_from_db(instance_id: str, db=None) -> Optional[FlowState]:
    """
    （已弃用）直接 SQLAlchemy 读取方式已由 checkpoint → Harness API 替代。
    保留签名避免导入报错。
    """
    import logging
    logger = logging.getLogger("langgraph.integration")
    logger.debug(
        "load_state_from_db 已弃用（instance=%s），"
        "断点恢复请使用 checkpoint.get_checkpointer().load()",
        instance_id,
    )
    return None


def check_harness_guards(state, target_status, operator="system", db=None):
    """
    （已弃用）Guards 校验已迁移至 FlowGraph 内联逻辑。
    保留签名。
    """
    return True, "Guards 校验已迁移至内联逻辑"


def execute_harness_transition(state, from_status, to_status, operator="system", db=None, comment=""):
    """
    （已弃用）状态流转已由 callback → HarnessClient.transition() 替代。
    保留签名。
    """
    state.current_status = to_status
    return state


# ═══════════════════════════════════════════════════════════════
# 增量优化202607：状态对比工具函数
# ═══════════════════════════════════════════════════════════════

def compare_state_fields(local: dict, online: dict, compare_fields: list[str] = None) -> dict:
    """
    对比本地缓存与在线 State 的字段差异。

    Args:
        local: 本地缓存的治理字典（如 _last_governance.json 内容）
        online: LangGraph API 返回的 State dict
        compare_fields: 需要对比的字段列表，默认基础治理字段

    Returns:
        {"diffs": {field: (local_val, online_val)}, "in_sync": bool}
    """
    if compare_fields is None:
        compare_fields = ["clean_input", "char_count", "is_long_text", "show_summary"]

    diffs = {}
    for field in compare_fields:
        lv = local.get(field)
        ov = online.get(field)
        if lv is not None and lv != ov:
            diffs[field] = (lv, ov)

    return {"diffs": diffs, "in_sync": len(diffs) == 0}


def build_sync_repair_updates(local_gov: dict, target: dict) -> dict:
    """
    构建需要推送到在线的增量更新字典。
    只推送有变化的字段，不推送完整 State。
    """
    updates = {}
    scalar_fields = ["clean_input", "char_count", "is_long_text", "show_summary"]
    for field in scalar_fields:
        lv = local_gov.get(field)
        tv = target.get(field)
        if lv is not None and lv != tv:
            updates[field] = lv


# ═══════════════════════════════════════════════════════════════
# 增量优化202607：通用治理解析器（模型无关）
# ═══════════════════════════════════════════════════════════════

class GovernanceParser:
    """
    通用 LLM 输出治理解析器 — 隔离模型差异。

    支持多种 LLM 输出格式，统一返回标准治理字典。
    新增模型支持时只需扩展 _extract_* 方法，不修改调用方。
    """

    # 标准治理字段名映射（用于非标准输出格式的字段提取）
    FIELD_ALIASES = {
        "clean_input": ["clean_input", "clean_input_text", "filtered_input", "cleaned_request"],
        "char_count": ["char_count", "char_count_total", "character_count", "chinese_char_count"],
        "is_long_text": ["is_long_text", "long_text", "is_long", "is_long_text_flag"],
        "temp_path": ["temp_path", "temp_file_path", "temp_file", "temporary_path"],
        "need_deepseek_forward": ["need_deepseek_forward", "need_deepseek", "forward_to_deepseek", "is_code_task"],
        "show_summary": ["show_summary", "summary", "display_summary", "summary_text"],
        "task_meta": ["task_meta", "task_metadata", "meta", "task_info"],
    }

    @staticmethod
    def parse_llm_output(raw_output: str) -> dict:
        """
        解析任意 LLM 完整输出文本，返回标准治理字典。

        支持格式：
          1. ```json ... ``` 代码块格式（DeepSeek 原生）
          2. 裸 JSON 对象 { ... }
          3. 非标准字段映射（通过 FIELD_ALIASES 适配）

        Returns:
            标准治理字典，缺失字段使用默认值。
        """
        import json
        import re

        gov = {}

        # 尝试格式1：```json ... ``` 代码块
        json_block = re.search(r'```json\s*\n?(.*?)\n?```', raw_output, re.DOTALL)
        if json_block:
            try:
                gov = json.loads(json_block.group(1).strip())
                return gov
            except json.JSONDecodeError:
                pass

        # 尝试格式2：裸 JSON 对象
        brace_match = re.search(r'\{[\s\S]*\}', raw_output)
        if brace_match:
            try:
                gov = json.loads(brace_match.group(0))
                return gov
            except json.JSONDecodeError:
                pass

        # 尝试格式3：非标准字段 → 别名映射
        if not gov:
            gov = GovernanceParser._extract_by_alias(raw_output)

        return gov

    @staticmethod
    def _extract_by_alias(raw_output: str) -> dict:
        """
        通过字段别名从任意文本中提取治理字段。
        用于非标准输出格式的兜底提取。
        """
        import re
        result = {}

        for std_field, aliases in GovernanceParser.FIELD_ALIASES.items():
            for alias in aliases:
                patterns = [
                    rf'"{alias}"\s*:\s*"(.+?)"',
                    rf'"{alias}"\s*:\s*(\d+)',
                    rf'"{alias}"\s*:\s*(true|false)',
                    rf'{alias}\s*[:=]\s*"(.+?)"',
                    rf'{alias}\s*[:=]\s*(\d+)',
                    rf'{alias}\s*[:=]\s*(true|false)',
                ]
                for pat in patterns:
                    m = re.search(pat, raw_output, re.IGNORECASE)
                    if m:
                        val = m.group(1)
                        # 类型推断
                        if val.lower() in ("true", "false"):
                            result[std_field] = val.lower() == "true"
                        elif val.isdigit():
                            result[std_field] = int(val)
                        else:
                            result[std_field] = val
                        break
                if std_field in result:
                    break

        # 填充默认值
        result.setdefault("clean_input", "")
        result.setdefault("char_count", 0)
        result.setdefault("is_long_text", False)
        result.setdefault("temp_path", None)
        result.setdefault("need_deepseek_forward", True)
        result.setdefault("show_summary", "")
        result.setdefault("task_meta", {})

        return result

    @staticmethod
    def to_governance_json(parsed: dict) -> str:
        """将解析后的治理字典格式化为标准 JSON 字符串"""
        return json.dumps(parsed, ensure_ascii=False, indent=2)

    @staticmethod
    def parse_and_validate(raw_output: str) -> tuple[dict, list[str]]:
        """
        解析并校验 — 一站式方法。
        Returns:
            (parsed_dict, validation_errors)
        """
        parsed = GovernanceParser.parse_llm_output(raw_output)

        from engine.flow.prompt_manager import validate_governance_json
        errors = validate_governance_json(parsed)

        return parsed, errors
