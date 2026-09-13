"""
LangGraph Prompt Manager — 桥接 Prompt Store 与 FlowState。

职责：
  1. 根据 FlowState + 角色名渲染完整 System Prompt
  2. 校验 LLM 输出是否符合 Schema
  3. 校验失败时自动触发违规记录写入 FlowState
  4. 记录本次使用的 prompt_version，存入 FlowState.prompt_template_id

用法（在 Node 中调用）：
  from engine.flow.prompt_manager import render_and_validate

  prompt = render_and_validate(
      role="test_executor",
      state=current_state,
      version="v1",
      llm_output=llm_raw_output,  # 可选：直接校验
  )
"""

import logging
from typing import Callable, Optional

from engine.flow.state import FlowState, ViolationType

logger = logging.getLogger("langgraph.prompt_manager")


# 增量优化202607：治理 JSON 标准 Schema 定义
GOVERNANCE_JSON_SCHEMA = {
    "required_fields": {
        "clean_input": str,
        "char_count": (int, float),
        "is_long_text": bool,
        "show_summary": str,
        "task_meta": dict,
    },
    "field_constraints": {
        "char_count": {"min": 0},
        "need_deepseek_forward": {"type": bool, "optional": True},
    },
}


# 增量优化202607：业务联动校验规则数组
# 每条规则 = condition(触发条件) + require(断言条件) + error_msg(错误信息)
# 统一在此追加新规则，不分散到校验函数内
# 规则 0 为最高优先级：检测输出是否包含完整标准治理 JSON（8 个必填字段全部校验，缺一不可）
BUSINESS_RULES: list[dict] = [
    {
        "desc": "输出首块无完整标准治理 JSON —— 8 字段完整性校验（最高优先级规则 0，优先于所有其他规则）",
        "condition": lambda d: True,
        "require": lambda d: all([
            isinstance(d.get("clean_input"), str),
            isinstance(d.get("char_count"), (int, float)),
            isinstance(d.get("is_long_text"), bool),
            d.get("need_deepseek_forward") is not None,
            isinstance(d.get("show_summary"), str),
            isinstance(d.get("full_content_embedded"), bool),
            isinstance(d.get("task_meta"), dict),
            d.get("task_meta", {}).get("change_file_count") is not None,
        ]),
        "error_msg": "治理 JSON 8 字段完整性校验失败：必须包含 clean_input、char_count、is_long_text、temp_path、need_deepseek_forward、show_summary、full_content_embedded、task_meta 全套结构且类型正确。违反全局最高优先级核心强制约束",
    },
    {
        "desc": "中文超50字符必须标记长文本",
        "condition": lambda d: isinstance(d.get("char_count"), (int, float)) and d["char_count"] > 50,
        "require": lambda d: d.get("is_long_text") is True,
        "error_msg": "char_count大于50时is_long_text必须为true，模型输出违反长文本分流规则",
    },
    {
        "desc": "长文本必须提供临时文件路径",
        "condition": lambda d: d.get("is_long_text") is True,
        "require": lambda d: bool(d.get("temp_path")),
        "error_msg": "is_long_text=true时temp_path不能为空，缺少长文本缓存路径",
    },
    {
        "desc": "对话禁止包含完整代码和长篇细则",
        "condition": lambda d: d.get("full_content_embedded", False) is True,
        "require": lambda d: False,  # 永远失败：一旦标记就拒绝
        "error_msg": "full_content_embedded=true，对话包含完整代码/细则，违反输出隔离铁律",
    },
    {
        "desc": "有文件变更时必须提供摘要",
        "condition": lambda d: (
            isinstance(d.get("task_meta"), dict)
            and d["task_meta"].get("change_file_count", 0) > 0
        ),
        "require": lambda d: bool(d.get("show_summary")),
        "error_msg": "change_file_count>0但show_summary为空，有文件变更却未提供摘要，违反输出分流规则",
    },
    {
        "desc": "有文件变更时必须提供变更文件列表",
        "condition": lambda d: (
            isinstance(d.get("task_meta"), dict)
            and d["task_meta"].get("change_file_count", 0) > 0
        ),
        "require": lambda d: bool(d["task_meta"].get("file_detail")),
        "error_msg": "change_file_count>0但file_detail为空，缺少变更文件明细",
    },
]


def validate_governance_dict(govern_data: dict) -> tuple[bool, list[str]]:
    """
    完整校验治理 JSON：基础字段存在性 + 数据类型 + 业务联动规则。

    Args:
        govern_data: 待校验的治理字典（从 JSON 解析而来）

    Returns:
        (is_valid, error_messages)
    """
    errors: list[str] = []

    # 1. 字段存在性 + 类型校验（原 validate_governance_json 逻辑）
    for field, expected_type in GOVERNANCE_JSON_SCHEMA["required_fields"].items():
        if field not in govern_data:
            errors.append(f"缺失必需字段: {field}")
        elif not isinstance(govern_data[field], expected_type):
            errors.append(
                f"字段类型错误: {field} 期望 {expected_type.__name__ if hasattr(expected_type, '__name__') else expected_type}, "
                f"实际 {type(govern_data[field]).__name__}"
            )

    # 2. 业务联动校验（遍历 BUSINESS_RULES）
    for rule in BUSINESS_RULES:
        try:
            cond_match = rule["condition"](govern_data)
            if cond_match and not rule["require"](govern_data):
                errors.append(rule["error_msg"])
        except (KeyError, TypeError, AttributeError) as e:
            errors.append(f"业务规则 [{rule['desc']}] 校验异常: {e}")

    return len(errors) == 0, errors


# 向后兼容：旧 validate_governance_json 调用重定向
def validate_governance_json(gov: dict) -> tuple[bool, list[str]]:
    """
    向后兼容封装，返回 (is_valid, errors) 元组。
    """
    return validate_governance_dict(gov)


def render_prompt(
    role: str,
    state: FlowState,
    version: str = "v1",
    extra_vars: Optional[dict] = None,
) -> str:
    """
    渲染完整 System Prompt。

    自动从 FlowState 提取变量字段。
    返回渲染后的 Prompt 字符串，可直接传递给 LLM。
    """
    from prompt_store.core_loader import render_prompt as _render

    state_dict = state.model_dump(mode="json")
    return _render(role, state_dict, version, extra_vars)


def validate_llm_output(
    role: str,
    state: FlowState,
    output: str,
    auto_violation: bool = True,
) -> tuple[bool, list[str]]:
    """
    校验 LLM 输出是否符合对应 JSON Schema。

    Args:
        role: 角色名
        state: 当前 FlowState（校验失败时写入违规）
        output: LLM 原始输出
        auto_violation: 校验失败是否自动写入违规记录

    Returns:
        (is_valid, error_messages)
    """
    from prompt_store.core_loader import validate_output as _validate

    is_valid, errors = _validate(role, output)
    if not is_valid and auto_violation:
        for err in errors[:3]:
            state.add_violation(
                ViolationType.COMPLIANCE_FAILURE,
                f"Prompt 输出 Schema 校验失败 [{role}]: {err}",
            )
        logger.warning("LLM 输出校验失败 [%s]: %s", role, errors)

    return is_valid, errors


def get_role_params(role: str) -> dict:
    """获取角色 LLM 调用参数（temperature, max_tokens 等）"""
    from prompt_store.core_loader import get_role_params as _get_params
    return _get_params(role)


def get_available_vars(role: str) -> list[str]:
    """获取角色模板可用的全部变量列表"""
    from prompt_store.core_loader import get_loader
    meta = get_loader().load_role_meta(role)
    return meta.get("available_vars", [])
