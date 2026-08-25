"""task_complete_hook.py — 任务完成埋点 hook。

设计（2026-08-25 用户裁定：只用 hook，不追加额外标记）：
  完成埋点触发 → 本 hook 调 task.complete → task.complete 追加权威完成记录
  （状态 pending→completed + TASK_COMPLETE 审计），该记录本身就是完成标记。

要点：
  - 引擎 `et()` 已支持 ET payload 的 `task` 块（见 kernel.py 任务生命周期段），
    本 hook 只是把"构造合法 payload + 调用 et()"封装成可被埋点一键触发的入口。
  - 递归安全：hook 挂在执行侧完成埋点（todo 完成处），不是引擎的 TASK_COMPLETE
    审计输出，故 task.complete → 审计不会再回勾本 hook。
  - task.complete 经 ensure_instance 自动建任务实例，无需预先登记；
    evidence 必须非空（引擎强制校验）。

用法：
  from xj_engine.task_complete_hook import task_complete_hook
  result = task_complete_hook(task_id="xxx", evidence={"output": "result.json"})

CLI：
  xj-engine complete --task-id xxx --evidence '{"output":"result.json"}'
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from .kernel import et


def build_payload(
    task_id: str,
    evidence: dict[str, Any],
    artifact: dict[str, Any] | None = None,
    trace_id: str | None = None,
    targets: list[str] | None = None,
) -> dict[str, Any]:
    """构造一个合法 ET payload，携带 task.complete 块（artifact + trace_id 为契约必填）。"""
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError("task.complete 必须携带非空 evidence（完成证据）")
    return {
        "artifact": artifact if artifact is not None else {
            "type": "task",
            "id": task_id,
            "status": "completed",
        },
        "trace_id": trace_id or str(uuid.uuid4()),
        "task": {
            "action": "complete",
            "task_id": task_id,
            "evidence": evidence,
            "targets": targets or [],
        },
    }


def task_complete_hook(
    task_id: str,
    evidence: dict[str, Any],
    artifact: dict[str, Any] | None = None,
    trace_id: str | None = None,
    targets: list[str] | None = None,
) -> dict[str, Any]:
    """完成埋点 hook：构造 payload 并调用引擎 et() → task.complete。

    返回引擎出参（含 task_result / audit）。code==success 即完成记录已权威落库。
    """
    payload = build_payload(task_id, evidence, artifact=artifact,
                            trace_id=trace_id, targets=targets)
    return et(payload)


def main_cli(task_id: str, evidence_text: str, trace_id: str = "") -> int:
    """CLI 入口（由 cli.py 调用）。"""
    evidence = json.loads(evidence_text)
    result = task_complete_hook(task_id, evidence, trace_id=trace_id or None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("code") == "success" else 1
