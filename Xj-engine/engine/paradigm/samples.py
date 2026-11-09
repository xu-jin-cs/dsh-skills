"""样本回流 / 告警放行 / 校验失败 / 逃逸告警 的落盘（追加式，永不改写历史）。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from . import spec


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append(name: str, row: dict) -> str:
    spec.LOG_DIR.mkdir(parents=True, exist_ok=True)
    p = spec.LOG_DIR / name
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return str(p)


def override_sample(text: str, decision: dict, reason: str = "", source: str = "manual") -> str:
    """人工覆盖 → 增量样本（用于后续词库/阈值调优）。"""
    return _append("paradigm_samples.jsonl", {
        "id": f"ps_{uuid.uuid4().hex[:12]}", "ts": _now(), "source": source,
        "text": text, "inputHash": decision.get("inputHash"),
        "suggested": decision.get("suggested"), "chosen": decision.get("paradigm"),
        "confidence": decision.get("confidence"), "decision": decision.get("decision"),
        "scores": decision.get("scores"), "reason": reason,
        "paradigmVersion": spec.paradigm_version(), "label": "human_override"})


def gate_failure(spec_path: str, result: dict, expected: str | None) -> str:
    """P0 阻断 → 回流范式层 + 推送双法合流评审（本函数只留痕，实际派发由调用方决定）。"""
    return _append("paradigm_gate_failures.jsonl", {
        "id": f"pgf_{uuid.uuid4().hex[:12]}", "ts": _now(), "spec": spec_path,
        "expectedParadigm": expected, "errors": result.get("errors"),
        "dualMethodPush": True, "paradigmVersion": spec.paradigm_version()})


def waiver(spec_path: str, result: dict, operator: str = "manual") -> str:
    """P1 人工强放 → 永久标记，后续作为负样本来源。"""
    return _append("paradigm_waivers.jsonl", {
        "id": f"pw_{uuid.uuid4().hex[:12]}", "ts": _now(), "spec": spec_path,
        "warnings": result.get("warnings"), "operator": operator,
        "forceReleased": True, "runtimeWatch": True,
        "paradigmVersion": spec.paradigm_version()})


def escape_alert(asset_key: str, declared: str, alert: dict) -> str:
    """逃逸告警：轻范式跑了重回路 / 单轮被拆多 Agent 等。"""
    return _append("paradigm_escape_alerts.jsonl", {
        "id": f"pea_{uuid.uuid4().hex[:12]}", "ts": _now(), "assetKey": asset_key,
        "declaredParadigm": declared, "alert": alert,
        "actions": ["pause_agent", "push_to_guide_master", "feedback_to_matcher"],
        "paradigmVersion": spec.paradigm_version()})
