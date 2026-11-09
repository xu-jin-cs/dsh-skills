"""运行时接线：消费点清单 + 启动自检 + fail-closed 判定。

原则：声明即契约，未接线即失败。第⑥步通过 ≠ 功能生效。
本模块只做"判定 + 留痕"；真正的暂停/派发由平台执行（见 actions）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import spec

REPORT_FILE = spec.LOG_DIR / "paradigm_wiring_report.json"

# 每个声明字段 → 当前仓内的消费点。status: wired | partial | absent
# kind: security/cost = 阻断类（strict 下必须阻断）；experience = 可降级
MANIFEST = [
    {"field": "plan.mode", "kind": "cost",
     "consumer": "engine/flow/workflow_compiler.py#compile_workflow_json",
     "status": "partial",
     "note": "编排只消费 workflow.stages/topo_order；模板 pipeline.taskTree 尚无执行器读取"},
    {"field": "tool.mode/tool_spec", "kind": "security",
     "consumer": "（本仓无工具调度器）",
     "status": "absent",
     "note": "调用前白名单校验未接线：engine/backend 均无 tool dispatcher"},
    {"field": "memory.enabledTiers", "kind": "experience",
     "consumer": "agent-harness/backend/retrieval（RAG 检索）",
     "status": "partial",
     "note": "知识库检索有记忆式召回；agent 级 working/episodic 落盘与装载未接线"},
    {"field": "reflect.mode/loop.maxIterations", "kind": "cost",
     "consumer": "engine/model/router.py#on_verify",
     "status": "partial",
     "note": "返工上限 maxRework 有守卫；loop.maxIterations 无运行时循环守卫"},
    {"field": "promptContract.allow_actions", "kind": "security",
     "consumer": "（本仓无动作拦截器）",
     "status": "absent",
     "note": "出动作前的动作集比对未接线"},
]


def manifest() -> list[dict]:
    return [dict(m) for m in MANIFEST]


def check(asset: dict, *, strict: bool = False) -> dict:
    """启动自检：声明字段 → 消费点是否存在。strict=True 时阻断类缺口返回 1。"""
    declared = (asset.get("capabilityProfile") or {}).get("capabilityProfile") or {}
    gaps = []
    for m in MANIFEST:
        gaps.append({**m, "declared": _declared(asset, declared, m["field"])})
    blocking = [g for g in gaps if g["status"] != "wired" and g["kind"] in ("security", "cost")]
    degradable = [g for g in gaps if g["status"] != "wired" and g["kind"] == "experience"]
    if strict and blocking:
        code, verdict = 1, "FAIL"
    elif gaps and (blocking or degradable):
        code, verdict = (2 if not strict else (1 if blocking else 2)), "WARN"
    else:
        code, verdict = 0, "PASS"
    out = {"code": code, "verdict": verdict, "strict": strict,
           "declaredFrom": (asset.get("capabilityProfile") or {}).get("derivedFrom"),
           "gaps": gaps, "blocking": [g["field"] for g in blocking],
           "degradable": [g["field"] for g in degradable],
           "actions": (["pause_start", "require_wiring_fix"] if (strict and blocking)
                       else ["warn_only"]),
           "paradigmVersion": spec.paradigm_version()}
    try:
        REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        REPORT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    return out


def _declared(asset: dict, prof: dict, field: str) -> object:
    if field == "plan.mode":
        return (prof.get("plan") or {}).get("mode")
    if field == "tool.mode/tool_spec":
        return {"mode": (prof.get("tool") or {}).get("mode"),
                "tools": len(((asset.get("promptContract") or {}).get("tool_spec")) or [])}
    if field == "memory.enabledTiers":
        return (prof.get("memory") or {}).get("enabledTiers")
    if field == "reflect.mode/loop.maxIterations":
        return {"mode": (prof.get("reflect") or {}).get("mode"),
                "maxIterations": ((prof.get("reflect") or {}).get("loop") or {}).get("maxIterations")}
    return ((asset.get("promptContract") or {}).get("allow_actions")) or []


# ── 运行期 fail-closed 判定（供宿主/平台调用；纯函数） ──────────
def check_tool_call(name: str, *, allow_actions: list[str],
                    whitelist: list[str]) -> dict:
    if name not in whitelist:
        return {"allow": False, "code": "TOOL_NOT_IN_GLOBAL_WHITELIST",
                "reason": f"{name} 不在全局白名单", "checkId": f"wc_{name}"}
    if name not in allow_actions:
        return {"allow": False, "code": "TOOL_NOT_ALLOWED_BY_AGENT",
                "reason": f"{name} 不在该 agent 的 allow_actions", "checkId": f"wc_{name}"}
    return {"allow": True, "code": "OK", "checkId": f"wc_{name}"}


def check_plan(task_tree) -> dict:
    if not task_tree:
        return {"allow": False, "code": "FAIL_DECLARED_NOT_CONSUMED",
                "reason": "声明了 plan 但调度前 taskTree 为空"}
    return {"allow": True, "code": "OK"}


def check_memory_snapshot(snapshot_dir: str | None, *, persist: bool) -> dict:
    if not persist:
        return {"allow": True, "code": "OK", "note": "persist=false，无需落盘"}
    d = Path(os.path.expanduser(snapshot_dir or ""))
    if not snapshot_dir or not d.is_dir():
        return {"allow": False, "code": "MEMORY_NOT_PERSISTED",
                "reason": f"声明落盘但快照目录不存在：{snapshot_dir!r}",
                "consequence": "标记任务「记忆不可复现」，禁止断点续跑"}
    return {"allow": True, "code": "OK"}


def check_reflect_iteration(current: int, max_iterations: int) -> dict:
    if not isinstance(max_iterations, int) or max_iterations <= 0:
        return {"allow": False, "code": "REFLECT_UNBOUNDED",
                "reason": f"反思上界非法：{max_iterations!r}"}
    if current > max_iterations:
        return {"allow": False, "code": "REFLECT_LIMIT_EXCEEDED",
                "reason": f"迭代 {current} > 上限 {max_iterations}",
                "actions": ["circuit_break", "escalate_human", "feedback_to_matcher"]}
    return {"allow": True, "code": "OK"}
