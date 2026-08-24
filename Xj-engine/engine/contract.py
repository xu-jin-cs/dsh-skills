"""ETLEngine 契约层（参考 AgentEngine et_contract：内核无写死业务规则，规则全来自 payload）。

Payload:
{
  "op": "write" | "delete" | "reconcile" | "batch"
      | "general_ingest" | "general_delete" | "general_reconcile",  # v2 general 族扩展
  "trace_id": "调用方追踪 id",
  "artifact": write→技能记录 {skill_id, content, role, project, severity, bug_type, keywords, sid?}
              delete→{skill_id}
              reconcile→{},
              general_ingest→{source_path, file_md5, tenant_id, biz_tag?, storage_source?, extra_keywords?}
              general_delete→{doc_unique_ids: [非空字符串数组], tenant_id}
              general_reconcile→{}（固定空，内核自动三源对账）,
  "options": {"rebuild_bm25": true, "legacy_sql": true},  # 可选，默认全 true（仅缺省链生效）
              # ★ v2：options 键必须 ∈ rules_loader.list_overridable()
              # （规则表中显式 overridable: true 的键），否则 reject——杜绝第二规则源
  "steps": ["write_lance", "bm25"]  # 可选（2026-08-16 契约可扩展性重写）：规则写入契约——
              # 显式声明步骤链，内核按 stages.STAGE_REGISTRY 查表执行；
              # 缺省回落内核固定链（含 options 开关），既有调用方零改动；
              # 仅 write/delete/general_ingest/general_delete 允许携带；未知步骤名 → reject
  "doc_meta": {file_suffix, file_size, ...}  # 仅 general_* 必填 dict；技能 op 携带即 reject
}

Output:
{
  "code": "success|reject|block|error",
  "op": ..., "trace_id": ...,
  "detail": {各层执行明细},
  "error": "失败原因（非 success 时）"
}
"""

from typing import Any, Protocol

from engine import rules_loader


class Stage(Protocol):
    """流水线步骤抽象契约。

    所有 stage（validate / parse / clean / chunk / write / post 等）统一签名：
        run(ctx, artifact) -> dict
    或直接作为可调用对象：
        stage(ctx, artifact) -> dict

    内核只依赖该协议，不依赖具体 stage 模块。
    """

    def __call__(self, ctx: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]: ...


class ContractViolationError(Exception):
    pass


_OPS = ("write", "delete", "reconcile", "batch",
        "general_ingest", "general_delete", "general_reconcile")
_GENERAL_OPS = ("general_ingest", "general_delete", "general_reconcile")
_STEPS_OPS = ("write", "delete", "general_ingest", "general_delete")
_WRITE_REQUIRED = ("skill_id", "content")
_GENERAL_INGEST_REQUIRED = ("source_path", "file_md5", "tenant_id")


def _validate_options(options) -> None:
    """★ v2 options 白名单：键必须 ∈ rules_loader.list_overridable()（缺省链生效时同样校验）。

    匹配规则：options 键命中 overridable 完整点号路径，或命中其叶子/相对后缀
    （如 'rebuild_bm25' 命中 'pipeline.general.default_chain' 下的可覆盖键，
    'max_token' 命中 'chunking.max_token'）。
    """
    if options is None:
        return
    if not isinstance(options, dict):
        raise ContractViolationError("options 必须是 dict")
    allowed = rules_loader.list_overridable()
    for key in options:
        if not any(p == str(key) or p.endswith("." + str(key)) for p in allowed):
            raise ContractViolationError(
                f"options 键 {key!r} 不在白名单（可覆盖键: {sorted(allowed)}）")


def validate_payload(payload: dict, valid_stages: set | None = None) -> None:
    if not isinstance(payload, dict):
        raise ContractViolationError("payload 必须是 dict")
    op = payload.get("op")
    if op not in _OPS:
        raise ContractViolationError(f"op 必须是 {_OPS} 之一: {op!r}")
    if not payload.get("trace_id"):
        raise ContractViolationError("缺少 trace_id")
    artifact = payload.get("artifact")
    if not isinstance(artifact, dict):
        raise ContractViolationError("artifact 必须是 dict")
    # ★ v2：options 白名单校验（所有 op 生效，缺省链同样校验）
    _validate_options(payload.get("options"))
    # ★ v2：doc_meta 双族门禁——general_ingest/delete 必填 dict（reconcile 无需，对齐清单 §6.3 示例）；
    # 技能 op 携带即 reject
    doc_meta = payload.get("doc_meta")
    if op in _GENERAL_OPS:
        if op != "general_reconcile" and not isinstance(doc_meta, dict):
            raise ContractViolationError(f"{op} 必须携带 doc_meta dict")
    elif doc_meta is not None:
        raise ContractViolationError(f"技能 op={op!r} 禁止携带 doc_meta")
    # steps 契约（2026-08-16）：规则写入契约的扩展点
    steps = payload.get("steps")
    if steps is not None:
        if op not in _STEPS_OPS:
            raise ContractViolationError(
                f"steps 仅 write/delete/general_ingest/general_delete 允许携带，当前 op={op!r}")
        if not isinstance(steps, list) or not steps:
            raise ContractViolationError("steps 必须是非空列表")
        known = valid_stages or set()
        for s in steps:
            if not isinstance(s, str) or not s.strip():
                raise ContractViolationError(f"steps 项非法: {s!r}")
            if s not in known:
                raise ContractViolationError(f"未知步骤: {s!r}（注册表: {sorted(known)}）")
    if op == "write":
        missing = [f for f in _WRITE_REQUIRED if not artifact.get(f)]
        if missing:
            raise ContractViolationError(f"write artifact 缺少字段: {missing}")
    if op == "delete" and not artifact.get("skill_id"):
        raise ContractViolationError("delete artifact 缺少 skill_id")
    if op == "batch":
        # 晋升合并事务（2026-08-16 裁定）：writes/deletes 至少其一非空，
        # 同事务执行、BM25 单次重建、逐项结果回传（失败项由调用方落积压，幂等重试可愈）
        writes = artifact.get("writes") or []
        deletes = artifact.get("deletes") or []
        if not writes and not deletes:
            raise ContractViolationError("batch 需要非空 writes 或 deletes")
        for w in writes:
            missing = [f for f in _WRITE_REQUIRED if not w.get(f)]
            if missing:
                raise ContractViolationError(f"batch write 项缺少字段 {missing}: {w.get('skill_id')!r}")
        for d in deletes:
            if not isinstance(d, str) or not d.strip():
                raise ContractViolationError(f"batch delete 项非法: {d!r}")
    # ★ v2：general 族 artifact 契约（改造清单 v2 §2.2）
    if op == "general_ingest":
        missing = [f for f in _GENERAL_INGEST_REQUIRED if not artifact.get(f)]
        if missing:
            raise ContractViolationError(f"general_ingest artifact 缺少字段: {missing}")
    if op == "general_delete":
        ids = artifact.get("doc_unique_ids")
        if (not isinstance(ids, list) or not ids
                or any(not isinstance(i, str) or not i.strip() for i in ids)):
            raise ContractViolationError("general_delete artifact.doc_unique_ids 必须是非空字符串数组")
        if not artifact.get("tenant_id"):
            raise ContractViolationError("general_delete artifact 缺少 tenant_id")
    if op == "general_reconcile" and artifact != {}:
        raise ContractViolationError("general_reconcile artifact 固定为 {}")


def validate_output(out: dict) -> dict:
    if out.get("code") not in ("success", "reject", "block", "error"):
        raise ContractViolationError(f"非法输出 code: {out.get('code')!r}")
    return out
