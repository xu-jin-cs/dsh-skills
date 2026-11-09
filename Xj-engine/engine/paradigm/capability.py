"""能力建模：范式 × 任务角色的四能力矩阵 + 角色升降级 + 冲突裁决（唯一实现）。

输入 = capabilityProfile(paradigm) ⊕ taskRole（不允许第三个输入源）
优先级：taskRole 修正 > paradigm 默认 > 全局缺省
输出字段均带 source（paradigm | role_override），无出处 = 第⑥步一致性门 FAIL。
"""
from __future__ import annotations

import copy

from . import spec

TIERS_OF = {
    "none": [],
    "working_only": ["working"],
    "working_episodic": ["working", "episodic"],
    "tiered_shared": ["working", "episodic", "semantic"],
}
REFLECT_LOOP = {"forbidden": 0, "lite": 1, "once": 1, "required_capped": 5, "arbitrate_once": 1}
# 需要外部数据的范式：工具能力不得为 none
NEEDS_TOOL = {"react", "plan_execute", "reflexion", "multi_agent"}


def _matrix() -> dict:
    return spec.load().get("capabilityMatrix") or {}


def _corrections() -> dict:
    return spec.load().get("roleCorrections") or {}


def normalize_role(role: str) -> str:
    """batch_job 为规范名；background_batch 为兼容别名。"""
    return "batch_job" if role == "background_batch" else role


def derive(paradigm: str, task_role: str) -> dict:
    """返回 capabilityProfile（含 source 与 overrides）；非法范式/角色直接抛错。"""
    if not spec.by_id(paradigm):
        raise ValueError(f"未知范式 {paradigm!r}")
    role = normalize_role(task_role)
    if role not in (spec.load().get("taskRoles") or {}):
        raise ValueError(f"未知任务角色 {task_role!r}")

    base = copy.deepcopy((_matrix().get(paradigm) or {}).get(role.split("_")[0]) or {})
    if not base:  # 矩阵按范式存默认值
        base = copy.deepcopy(_matrix().get(paradigm) or {})
    profile = {
        "plan": {"mode": base.get("plan", "lite"), "source": "paradigm"},
        "tool": {"mode": base.get("tool", "none"), "maxTools": base.get("maxTools", 0),
                 "source": "paradigm"},
        "memory": {"enabledTiers": TIERS_OF.get(base.get("memory", "none"), []),
                   "persist": base.get("memory") in ("working_episodic", "tiered_shared"),
                   "recall": base.get("recall", "on_demand"),
                   "sharedBlackboard": base.get("memory") == "tiered_shared",
                   "source": "paradigm"},
        "reflect": {"mode": base.get("reflect", "forbidden"),
                    "loop": {"maxIterations": REFLECT_LOOP.get(base.get("reflect", "forbidden"), 0)},
                    "verify": {"maxReflow": 5},
                    "source": "paradigm"},
    }
    if profile["tool"]["mode"] == "required_isolated":
        profile["tool"]["mode"] = "required"
        profile["tool"]["isolated"] = True

    overrides: list[dict] = []
    rule = (_corrections().get(role) or {})
    # 记忆
    mem_rule = rule.get("memory") or {}
    if mem_rule.get("maxTier") == "working":
        keep = [t for t in profile["memory"]["enabledTiers"] if t == "working"]
        changed = keep != profile["memory"]["enabledTiers"] or profile["memory"]["persist"] is True
        profile["memory"]["enabledTiers"] = keep
        profile["memory"]["persist"] = False
        if changed:
            profile["memory"]["source"] = "role_override"
            overrides.append({"field": "memory.enabledTiers", "reason": f"taskRole={role}"})
    if mem_rule.get("requireEpisodic"):
        tiers = profile["memory"]["enabledTiers"]
        for t in ("working", "episodic"):
            if t not in tiers:
                tiers.append(t)
        profile["memory"]["persist"] = True
        profile["memory"]["source"] = "role_override"
        overrides.append({"field": "memory.enabledTiers", "reason": f"taskRole={role}"})
    if mem_rule.get("requireRecall"):
        profile["memory"]["recall"] = "on_demand"
        profile["memory"]["source"] = "role_override"
        overrides.append({"field": "memory.recall", "reason": f"taskRole={role}"})
    # 反思
    ref_rule = rule.get("reflect") or {}
    cap = ref_rule.get("maxIterations")
    if isinstance(cap, int):
        cur = profile["reflect"]["loop"]["maxIterations"] or 1
        if cap < cur:
            profile["reflect"]["loop"]["maxIterations"] = cap
            profile["reflect"]["source"] = "role_override"
            overrides.append({"field": "reflect.loop.maxIterations", "reason": f"taskRole={role}"})
    # 规划
    plan_rule = rule.get("plan") or {}
    if plan_rule.get("maxMode") == "lite" and profile["plan"]["mode"] == "full":
        profile["plan"]["mode"] = "lite"
        profile["plan"]["source"] = "role_override"
        overrides.append({"field": "plan.mode", "reason": f"taskRole={role}"})
    if plan_rule.get("requireFull") and profile["plan"]["mode"] != "full":
        profile["plan"]["mode"] = "full"
        profile["plan"]["source"] = "role_override"
        overrides.append({"field": "plan.mode", "reason": f"taskRole={role}"})
    if plan_rule.get("requireResumable"):
        profile["plan"]["resumable"] = True
        overrides.append({"field": "plan.resumable", "reason": f"taskRole={role}"})
    # 工具
    tool_rule = rule.get("tool") or {}
    if isinstance(tool_rule.get("maxTools"), int) and profile["tool"]["mode"] != "none":
        cur = profile["tool"].get("maxTools") or tool_rule["maxTools"]
        if tool_rule["maxTools"] < cur:
            profile["tool"]["maxTools"] = tool_rule["maxTools"]
            profile["tool"]["source"] = "role_override"
            overrides.append({"field": "tool.maxTools", "reason": f"taskRole={role}"})
    if tool_rule.get("requireRetry"):
        profile["tool"]["retry"] = True
        profile["tool"]["idempotencyKey"] = True
        overrides.append({"field": "tool.retry", "reason": f"taskRole={role}"})

    return {"capabilityProfile": profile,
            "derivedFrom": {"paradigm": paradigm, "taskRole": role},
            "overrides": overrides}


def _combo_rules() -> dict:
    """禁止组合：标签来自 paradigms.json.forbiddenCombos（唯一真源），谓词在此绑定。

    JSON 存不了谓词；任一侧新增而未绑定 → `conflicts()` 显式报"规则未实现"，
    不静默漂移（2026-11-10 F-7 收口）。
    """
    return {
        "单轮工具调用 + 反思回路":
            lambda p, pid, role: pid == "single_tool_call" and p["reflect"]["mode"] != "forbidden",
        "记忆 none + long_session":
            lambda p, pid, role: not p["memory"]["enabledTiers"] and role == "long_session",
        "反思 required_capped + loop 上界缺失":
            lambda p, pid, role: (p["reflect"]["mode"] == "required_capped"
                                  and (p["reflect"]["loop"]["maxIterations"] or 0) <= 0),
        "多 Agent + 记忆 none":
            lambda p, pid, role: pid == "multi_agent" and not p["memory"]["enabledTiers"],
        "工具 none + 任一需外部数据的范式":
            lambda p, pid, role: p["tool"]["mode"] == "none" and pid in NEEDS_TOOL,
    }


def conflicts(profile_row: dict) -> list[str]:
    """§1.4 禁止组合；按 paradigms.json 声明顺序逐条判定，任一命中即 FAIL。"""
    p = profile_row["capabilityProfile"]
    pid = profile_row["derivedFrom"]["paradigm"]
    role = profile_row["derivedFrom"]["taskRole"]
    rules = _combo_rules()
    labels = spec.load().get("forbiddenCombos") or list(rules)
    out: list[str] = []
    for label in labels:
        fn = rules.get(label)
        if fn is None:
            out.append(f"禁止组合规则未实现（声明与判定漂移）：{label}")
            continue
        if fn(p, pid, role):
            out.append(f"禁止组合：{label}")
    return out


def build(paradigm: str, task_role: str) -> dict:
    row = derive(paradigm, task_role)
    errs = conflicts(row)
    row["conflicts"] = errs
    row["ok"] = not errs
    return row
