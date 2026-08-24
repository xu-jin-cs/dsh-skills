"""
ET 契约层 — 引擎入参/出参契约（引擎固有接口承诺，2026-08-16 按参考契约重构）。

契约来源：用户裁定参考《AgentEngine Payload 完整契约 Schema
（增量兼容原有链路｜JSON Schema Draft 2020-12）》，规则要点：
  1. 引擎内置入参契约 + 配套出参契约；ET / CustomET 只负责产出符合契约的载荷，
     不可修改引擎执行时序（artifact_validate → state_intercept → gate_guard
     → content_issue）；
  2. 所有扩展块全部可选，存量链路不传即可正常运行，向下兼容；
  3. 所有业务策略（ACL、跃迁规则、配额、失败策略）由 ET 组装进 payload，
     不属于引擎硬编码逻辑。

平台扩展键（参考未含、为覆盖旧引擎能力而追加，全部可选）：
  - artifact_validate        ：交付物校验块（旧引擎 validators 能力，参考无校验钩子）
  - gate_guard.route / route_whitelist ：路由白名单（用户最初门禁诉求）
  - gate_guard.rate_current           ：ET 上报的当前速率（无状态内核无法自计数）
  - resource_control.token_used / concurrent_current / cost_used ：ET 上报实测值
  - resource_control.model_allow_list / model ：模型版本约束
  - state_intercept.current_state     ：无状态内核的源状态显式传入
    （缺省回退读 artifact.state）

执行时序（引擎固定，ET 不可改）：
  resource_control 前置 → artifact_validate(扩展) → state_intercept
  → gate_guard → content_issue → delivery 装配
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import jsonschema


class ContractViolationError(ValueError):
    """入参 Payload 不符合契约时抛出。内核只认契约，不认 ET 实现。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("ET Payload 契约校验失败: " + "; ".join(errors))


class OutputContractError(RuntimeError):
    """内核出参不符合出参契约时抛出（属内核 bug，不应在正常执行中出现）。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("内核出参契约校验失败: " + "; ".join(errors))


# 拦截失败动作 → 出参 code 映射见 kernel
_ON_FAIL = {
    "enum": ["terminate", "rollback", "failed"],
    "description": "deprecated，内核不消费，统一用 failure_policy",
}

# ═══════════════════════════════════════════════════════════════
# 交付物校验条目（artifact_validate 扩展块专用）
# ═══════════════════════════════════════════════════════════════

_VALIDATE_CHECK = {
    "type": "object",
    "required": ["id", "type"],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "type": {
            "enum": [
                "required_fields",   # 文本/对象必须包含指定字段或关键词
                "file_exists",       # 文件必须存在且非空
                "file_min_size",     # 文件最小字节数
                "json_field",        # JSON 文件必须含指定字段
                "regex",             # 文本必须命中正则
                "min_ratio",         # 比率门禁（如覆盖率 checked/total >= min）
                # ── 通用扩展原语（2026-08-17 测试四门禁迁移专项 U6，零业务常量）──
                "items_regex",           # 数组逐项字段正则（pattern 由 payload 给）
                "items_unique",          # 数组逐项字段值去重
                "items_required_fields", # 数组逐项必填/非空（fields 支持项内点号路径）
                "items_enum",            # 数组逐项字段枚举白名单（field 支持 a[].b 通配）
                "dir_glob_count",        # 目录递归 glob 计数下限（目录不存在即失败）
                "dir_file_count_eq_json",# 目录文件数 == 同目录 JSON 数值字段对账
                "dir_file_hash_unique",  # 目录同后缀文件内容哈希去重（防复用）
                "fields_distinct",       # 两字段相异约束（ignore_empty 空值放行）
            ]
        },
        # required_fields
        "fields": {"type": "array", "items": {"type": "string"}},
        "text_source": {"type": "string"},       # artifact 内点号路径；缺省检查 artifact 键
        # file_exists / file_min_size / json_field / dir_*（目录对账族）
        "path": {"type": "string"},
        "min_size": {"type": "integer", "minimum": 1},
        # regex / items_regex
        "pattern": {"type": "string"},
        # min_ratio / dir_glob_count（min 计数下限）
        "numerator": {}, "denominator": {}, "min": {"type": "number"},
        # items_*（数组逐项校验族）
        "items_path": {"type": "string"},        # artifact 内点号路径，指向数组
        "field": {"type": "string"},             # 项内点号路径；items_enum 支持 a[].b 一层通配
        "values": {"type": "array", "items": {"type": "string"}},
        "nonempty": {"type": "boolean"},         # true 时要求值非空（falsy 即违例）
        # fields_distinct
        "field_a": {"type": "string"},
        "field_b": {"type": "string"},
        "ignore_empty": {"type": "boolean"},     # true 时任一为空即放行
        # dir_file_count_eq_json / dir_file_hash_unique
        "suffix": {"type": "string"},
        "json_file": {"type": "string"},
        "json_field": {"type": "string"},
        "algo": {"type": "string"},              # 哈希算法名（hashlib.new 可解析）
        # 通用
        "on_fail": _ON_FAIL,
        "message": {"type": "string"},
    },
    "additionalProperties": False,
}

# ═══════════════════════════════════════════════════════════════
# 入参契约 JSON Schema（ET 输出规范）
# ═══════════════════════════════════════════════════════════════

PAYLOAD_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "AgentEngine Input Payload",
    "description": "Agent接力交付物流转引擎入参契约，由ET生成，引擎消费",
    "type": "object",
    "required": ["artifact", "trace_id"],
    "properties": {
        "trace_id": {
            "type": "string",
            "minLength": 1,
            "description": "全局追踪ID，审计、日志、链路排查唯一标识",
        },
        "parent_trace_id": {
            "type": "string",
            "description": "上游父链路ID，构建完整谱系，可选",
        },
        "artifact": {
            "type": ["object", "string"],
            "description": "Agent原始交付物主体",
        },
        # ── 固定钩子 1：状态拦截 ──
        "state_intercept": {
            "type": "object",
            "description": "状态拦截&状态跃迁规则，不传则跳过本钩子",
            "properties": {
                "allow_transition": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "【弱模式，推荐 allowed_pairs】允许的源状态集合：仅校验 current "
                        "∈ 集合，不校验 (current, target) 跃迁对，存在 PENDING→CLOSED "
                        "类非法目标逃逸风险；仅在未提供 allowed_pairs 时生效"
                    ),
                },
                "allowed_pairs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["from", "to"],
                        "properties": {
                            "from": {"type": "string"},
                            "to": {"type": "string"},
                        },
                        "additionalProperties": False,
                    },
                    "description": (
                        "【推荐】合法跃迁对集合：提供时内核严格校验 "
                        "(current_state, target_state) ∈ 集合，不在则 block"
                    ),
                },
                "target_state": {
                    "type": "string",
                    "description": "校验通过后写入的目标任务状态",
                },
                "state_meta": {
                    "type": "object",
                    "description": "随状态变更附加的自定义元数据",
                },
                "current_state": {
                    "type": "string",
                    "description": "【平台扩展】源状态显式传入；缺省回退读 artifact.state",
                },
            },
            "additionalProperties": False,
        },
        # ── 固定钩子 2：门禁准入 ──
        "gate_guard": {
            "type": "object",
            "description": "门禁准入规则，不传则跳过本钩子",
            "properties": {
                "target_agent_id": {"type": "string"},
                "acl": {"type": "array", "items": {"type": "string"}},
                "rate_limit": {"type": "integer"},
                "rate_current": {
                    "type": "integer",
                    "description": "【平台扩展】ET 上报当前速率（仅作参考）：内核侧按 key 自维护 60s 滑窗权威计数，有效速率=max(上报,内核实测)，报低无法穿透",
                },
                "permission_scope": {"type": "string"},
                "route": {
                    "type": "string",
                    "description": "【平台扩展】本次请求路由，配合 route_whitelist",
                },
                "route_whitelist": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "【平台扩展】路由白名单",
                },
            },
            "additionalProperties": False,
        },
        # ── 固定钩子 3：内容签发 ──
        "content_issue": {
            "type": "object",
            "description": "交付物签发/防篡改配置，不传则跳过本钩子",
            "properties": {
                "sign": {"type": "boolean"},
                "sign_algo": {"enum": ["sha256", "hmac-sha256"], "default": "sha256"},
                "watermark": {"type": "boolean"},
                "attach_issue_meta": {"type": "object"},
                "secret": {
                    "type": "string",
                    "description": "【平台扩展】hmac-sha256 密钥；缺省用内核内置密钥",
                },
            },
            "additionalProperties": False,
        },
        # ── 平台扩展钩子：交付物校验（覆盖旧引擎 validators 能力） ──
        "artifact_validate": {
            "type": "object",
            "description": "【平台扩展】交付物校验规则，在 state_intercept 之前执行",
            "required": ["checks"],
            "properties": {
                "checks": {"type": "array", "items": _VALIDATE_CHECK, "minItems": 1},
            },
            "additionalProperties": False,
        },
        # ── 扩展块：资源 & 配额 ──
        "resource_control": {
            "type": "object",
            "description": "资源、Token、超时、优先级控制【扩展必选推荐】",
            "properties": {
                "token_limit": {"type": "integer"},
                "global_timeout_ms": {"type": "integer"},
                "hook_timeout_ms": {"type": "integer"},
                "priority": {"type": "string", "enum": ["low", "normal", "high"]},
                "max_concurrent": {"type": "integer"},
                "cost_budget": {"type": "number"},
                "token_used": {"type": "number", "description": "【平台扩展】ET 上报实测（仅作参考）：内核侧按身份单调高水位台账夹紧，有效用量=max(上报,内核台账)，报低/重置计数器无效"},
                "concurrent_current": {"type": "integer", "description": "【平台扩展】ET 上报实测（仅作参考）：内核侧自测在飞请求数，有效并发=max(上报,内核实测)"},
                "cost_used": {"type": "number", "description": "【平台扩展】ET 上报实测（仅作参考）：内核侧按身份单调高水位台账夹紧，有效用量=max(上报,内核台账)"},
                "model_allow_list": {
                    "type": "array", "items": {"type": "string"},
                    "description": "【平台扩展】模型版本约束",
                },
                "model": {"type": "string", "description": "【平台扩展】本次使用模型"},
            },
            "additionalProperties": False,
        },
        # ── 扩展块：失败策略 & 补偿分支 ──
        "failure_policy": {
            "type": "object",
            "description": "失败、重试、兜底分流策略【扩展必选推荐】",
            "properties": {
                "max_retry": {"type": "integer"},
                "retry_delay_ms": {"type": "integer"},
                "fallback_target": {"type": "string", "description": "校验失败兜底节点，如人工agent"},
                "compensation_action": {"type": "string", "enum": ["none", "revoke_issue", "rollback_state"]},
                "alert_on_block": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        # ── 扩展块：投递 ──
        "delivery": {
            "type": "object",
            "description": "下游投递模式、回执控制【扩展必选推荐】",
            "properties": {
                "mode": {"type": "string", "enum": ["single", "async", "broadcast"]},
                "next_handler": {"type": ["string", "array"]},
                "require_ack": {"type": "boolean", "description": "是否需要下游回执确认"},
                "output_transform": {
                    "type": "object",
                    "description": "轻量字段过滤/脱敏映射，禁止重型ETL逻辑",
                    "properties": {
                        "include_fields": {"type": "array", "items": {"type": "string"}},
                        "exclude_fields": {"type": "array", "items": {"type": "string"}},
                        "mask_fields": {"type": "array", "items": {"type": "string"}},
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
        # ── 任务域扩展：task_complete / task_cancel / task_archive ──
        "task": {
            "type": "object",
            "description": "任务生命周期动作：完成后状态流转、证据校验、审计、签名、桥接通知",
            "required": ["action", "task_id"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["complete", "cancel", "archive"],
                    "description": "complete=完成；cancel=取消；archive=注销归档",
                },
                "task_id": {"type": "string", "minLength": 1},
                "from_state": {"type": "string", "description": "期望源状态，可选；缺省由 StateStore 当前状态决定"},
                "to_state": {"type": "string", "description": "目标状态，可选；缺省按 action 映射：complete->completed / cancel->cancelled / archive->archived"},
                "evidence": {
                    "type": "object",
                    "description": "完成证据：由 artifact_validate 或外部证据校验消费",
                },
                "targets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "桥接目标，如 dsh / kimi / claude；缺省不通知前端",
                },
                "require_bridge_ack": {
                    "type": "boolean",
                    "default": False,
                    "description": "桥接是否需要前端回执；未实现回执时按成功处理",
                },
            },
            "additionalProperties": False,
        },
        # ── 扩展块：审计元数据 ──
        "audit_meta": {
            "type": "object",
            "description": "租户、身份、密级、留存策略【扩展必选推荐】",
            "properties": {
                "tenant_id": {"type": "string"},
                "principal": {"type": "string", "description": "操作主体"},
                "sensitivity_level": {"type": "string", "enum": ["public", "internal", "sensitive", "confidential"]},
                "audit_tags": {"type": "array", "items": {"type": "string"}},
                "retention_ttl_sec": {"type": "integer", "description": "审计快照保留时长"},
            },
            "additionalProperties": False,
        },
        # ── 进阶预留（接受并入约，内核暂不消费，L5 对外开放时启用） ──
        "traffic_exp": {
            "type": "object",
            "description": "灰度、A/B实验、流量染色【平台进阶，预留】",
            "properties": {
                "experiment_id": {"type": "string"},
                "sample_rate": {"type": "number", "minimum": 0, "maximum": 1},
                "traffic_tag": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "sandbox_policy": {
            "type": "object",
            "description": "沙箱、工具权限控制【高级安全场景，预留】",
            "properties": {
                "tool_allow_list": {"type": "array", "items": {"type": "string"}},
                "network_isolate": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        "debug": {
            "type": "boolean",
            "default": False,
            "description": "开启则出参附加本次规则快照，生产默认关闭",
        },
    },
    "additionalProperties": False,
}

_VALIDATOR = jsonschema.Draft202012Validator(PAYLOAD_SCHEMA)


def validate_payload(payload: Any) -> dict[str, Any]:
    """
    内核唯一前置动作：校验入参契约。
    通过则原样返回 payload；不通过抛 ContractViolationError（汇总全部违例）。
    """
    if not isinstance(payload, dict):
        raise ContractViolationError([f"payload 必须是 dict，实际: {type(payload).__name__}"])
    errors = sorted(_VALIDATOR.iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors:
        msgs = []
        for e in errors:
            path = ".".join(str(p) for p in e.absolute_path) or "<root>"
            msgs.append(f"{path}: {e.message}")
        raise ContractViolationError(msgs)
    return payload


# ═══════════════════════════════════════════════════════════════
# 出参契约 JSON Schema（引擎侧定义，gate 调度层消费）
# ═══════════════════════════════════════════════════════════════
#
# code 语义（引擎固定映射）：
#   success —— 全部已声明钩子通过，可投递
#   reject  —— artifact_validate 交付物校验未通过
#   block   —— state_intercept / gate_guard / resource_control 拦截
#   timeout —— hook_timeout_ms / global_timeout_ms 超时
#   error   —— 内核或 content_issue 执行异常
#
# 除 code/trace_id 外各键恒在（null 表示对应钩子未声明或未执行）。

_GATE_RESULT_OUT = {
    "type": ["object", "null"],
    "required": ["pass", "reason"],
    "properties": {
        "pass": {"type": "boolean"},
        "reason": {"type": "string"},
    },
}

_FAILURE_INFO_OUT = {
    "type": ["object", "null"],
    "required": ["error_msg"],
    "properties": {
        "error_msg": {"type": "string"},
        "fallback_target": {"type": ["string", "null"]},
        "max_retry": {"type": "integer"},
        "retry_delay_ms": {"type": "integer"},
        "compensation_action": {"enum": ["none", "revoke_issue", "rollback_state"]},
        "alert": {"type": "boolean"},
    },
}

_DELIVERY_OUT = {
    "type": ["object", "null"],
    "required": ["next_handler", "require_ack"],
    "properties": {
        "next_handler": {"type": ["string", "array", "null"]},
        "require_ack": {"type": "boolean"},
        "mode": {"enum": ["single", "async", "broadcast"]},
        "payload": {},   # 转换后的投递载荷；非 success 时为 null
    },
}

_RESOURCE_OUT = {
    "type": ["object", "null"],
    "required": ["pass", "violations"],
    "properties": {
        "pass": {"type": "boolean"},
        "violations": {"type": "array", "items": {"type": "string"}},
        "priority": {"enum": ["low", "normal", "high"]},
    },
}

_VALIDATE_RESULT_OUT = {
    "type": ["object", "null"],
    "required": ["pass", "results", "failures"],
    "properties": {
        "pass": {"type": "boolean"},
        "results": {"type": "array"},
        "failures": {"type": "array"},
    },
}

OUTPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "AgentEngine Output Contract",
    "description": "引擎固定出参契约，gate调度层消费",
    "type": "object",
    "required": ["code", "trace_id"],
    "properties": {
        "code": {"type": "string", "enum": ["success", "block", "reject", "timeout", "error"]},
        "trace_id": {"type": "string"},
        "parent_trace_id": {"type": ["string", "null"]},
        "new_task_state": {"type": ["string", "null"]},
        "signed_artifact": {"type": ["object", "string", "null"]},
        "gate_result": _GATE_RESULT_OUT,
        "validate_result": _VALIDATE_RESULT_OUT,
        "resource": _RESOURCE_OUT,
        "issue_meta": {
            "type": ["object", "null"],
            "description": "签发哈希、时间等凭证",
        },
        "delivery": _DELIVERY_OUT,
        "failure_info": _FAILURE_INFO_OUT,
        "audit_meta": {"type": ["object", "null"], "description": "入参审计元数据透传"},
        "task_result": {
            "type": ["object", "null"],
            "description": "task 生命周期动作结果（task_complete/task_cancel/task_archive）",
        },
        "_debug": {
            "type": "object",
            "description": "仅debug=true时返回：本次执行使用的规则快照、各钩子明细",
        },
    },
    "additionalProperties": False,
}

_OUTPUT_VALIDATOR = jsonschema.Draft202012Validator(OUTPUT_SCHEMA)


def validate_output(output: Any) -> dict[str, Any]:
    """内核返回前自验出参契约。不符合说明内核实现有 bug，抛 OutputContractError。"""
    errors = sorted(_OUTPUT_VALIDATOR.iter_errors(output), key=lambda e: list(e.absolute_path))
    if errors:
        msgs = []
        for e in errors:
            path = ".".join(str(p) for p in e.absolute_path) or "<root>"
            msgs.append(f"{path}: {e.message}")
        raise OutputContractError(msgs)
    return output


# ═══════════════════════════════════════════════════════════════
# ET 契约实现基类 — 外部可整体重写替换
# ═══════════════════════════════════════════════════════════════

class ETContract(ABC):
    """
    ET（载荷生成器）契约基类。

    外部系统只需实现 build_payload()，输出符合 PAYLOAD_SCHEMA 的 dict，
    即可交付引擎内核执行；内核不依赖任何具体 ET 实现，也不可被 ET
    修改执行时序。

    便捷调用：``et_instance(artifact, **kw)`` 等价于
    ``kernel.et(self.build_payload(...))``。
    """

    @abstractmethod
    def build_payload(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """生成标准 Payload。子类唯一必须实现的方法。"""
        raise NotImplementedError

    def __call__(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """生成 Payload 并直接交付内核执行，返回标准出参。"""
        from .kernel import et  # 延迟导入，避免环

        return et(self.build_payload(*args, **kwargs))
