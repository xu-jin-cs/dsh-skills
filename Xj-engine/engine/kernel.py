"""ETLEngine 内核（standalone 版）— etl_engine() 统一执行入口（general 族专线）。

自历史内核裁剪：仅保留 general 族三 op
（general_ingest / general_delete / general_reconcile），历史族
write/delete/reconcile/batch 分支与 stages/store/bm25 依赖全部移除。

执行时序（内核固定，调用方不可改）：
  contract_validate → resource_control(前检) → 步骤链执行 → outbox 记账 → delivery

出参 code 四态：success / reject / block / error（语义见 engine.contract）。
"""
import time
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

from engine import general_stages, outbox, rules_loader
from engine.contract import ContractViolationError, validate_output, validate_payload
from engine.deps import Deps


def _resolve_db(deps: Deps | None):
    """按依赖注入契约解析 DB 实例；未注入时回退默认工厂。"""
    if deps is not None:
        if deps.db is not None:
            return deps.db
        if deps.db_factory is not None:
            return deps.db_factory()
    return general_stages.make_db()


def _resolve_store(deps: Deps | None):
    """按依赖注入契约解析 Store 实例；未注入时回退默认工厂。"""
    if deps is not None:
        if deps.store is not None:
            return deps.store
        if deps.store_factory is not None:
            return deps.store_factory()
    return general_stages.make_store()


def _resolve_stages(deps: Deps | None) -> dict:
    """解析 stage 注册表；未注入时回退默认 general_stages 注册表。"""
    if deps is not None and deps.stages is not None:
        return deps.stages
    return general_stages.GENERAL_STAGE_REGISTRY


def _resolve_doc_id(deps: Deps | None):
    """解析文档 ID 生成函数；未注入时回退默认实现。"""
    if deps is not None and deps.doc_id_factory is not None:
        return deps.doc_id_factory
    return general_stages.make_doc_id


def _resolve_classifier(deps: Deps | None):
    """解析异常分类函数；未注入时回退默认实现。"""
    if deps is not None and deps.exception_classifier is not None:
        return deps.exception_classifier
    return general_stages.classify_exception


def _resource_control_general(store) -> tuple[bool, str]:
    """前检：general 族 Store 可达性（list_doc_ids 可执行即视为可用）。"""
    try:
        store.list_doc_ids()
        return True, ""
    except Exception as exc:
        return False, f"general Store 不可达: {type(exc).__name__}: {exc}"


def etl_engine(payload: dict[str, Any], deps: Deps | None = None) -> dict[str, Any]:
    """引擎内核统一入口（standalone 仅受理 general_* op）。

    依赖注入：
      deps.db / deps.store：直接传入已构造实例；
      deps.db_factory / deps.store_factory：传入无参工厂，由内核按需调用；
      不传时回退默认工厂，保持原有行为。

    入参/出参契约见 engine.contract。
    """
    t0 = time.monotonic()
    try:
        validate_payload(payload, valid_stages=set(_resolve_stages(deps)))
    except ContractViolationError as exc:
        return validate_output({"code": "reject", "op": payload.get("op") if isinstance(payload, dict) else None,
                                "trace_id": payload.get("trace_id") if isinstance(payload, dict) else None,
                                "detail": {}, "error": str(exc)})

    op = payload["op"]
    if not op.startswith("general_"):
        return validate_output({"code": "reject", "op": op, "trace_id": payload["trace_id"],
                                "detail": {}, "error": f"standalone 版仅受理 general_* op，收到: {op}"})
    return _general_op(payload, t0, deps)


def _general_op(payload: dict[str, Any], t0: float, deps: Deps | None = None) -> dict[str, Any]:
    op = payload["op"]
    artifact = payload["artifact"]
    options = payload.get("options") or {}
    doc_meta = payload.get("doc_meta") or {}
    detail: dict[str, Any] = {"steps": {}}

    store = _resolve_store(deps)
    ok, why = _resource_control_general(store)
    if not ok:
        return validate_output({"code": "block", "op": op, "trace_id": payload["trace_id"],
                                "detail": detail, "error": why})
    db = _resolve_db(deps)
    rules = rules_loader.load_rules()
    registry = _resolve_stages(deps)
    try:
        if op == "general_ingest":
            chain = payload.get("steps") or rules["pipeline"]["general"]["default_chain"]
            first = rules["pipeline"]["general"]["require_first_step"]
            if not chain or chain[0] != first:
                raise RuntimeError(f"自定义链缺失前置校验步骤 {first}（契约 §2.4）")
            tenant_id = artifact["tenant_id"]
            doc_id = _resolve_doc_id(deps)(tenant_id, artifact["file_md5"])
            done_steps = {s["step"] for s in db.get_steps(doc_id) if s["status"] == "success"}
            db.outbox_record(doc_id, "write", "pending")
            hit = done_steps & set(chain)
            ctx: dict[str, Any] = {
                "doc_unique_id": doc_id, "options": options, "doc_meta": doc_meta,
                "db": db, "store": store,
                # force 语义（契约 §2.5-4）：resume_partial 断点续跑 / idempotent_replay 知情幂等重放；
                # MD5 去重始终判定不误杀自身
                "force_reparse": bool(hit),
                "force_reparse_reason": (("idempotent_replay" if set(chain) <= done_steps
                                          else "resume_partial") if hit else ""),
                "trace_id": payload["trace_id"],
            }
            for name in chain:
                try:
                    r = registry[name](ctx, artifact)
                except Exception as exc:
                    db.set_step(doc_id, name, "failed", last_error=str(exc))
                    raise
                db.set_step(doc_id, name, "success")
                detail["steps"][name] = r
            detail["chunk_ids"] = ctx.get("chunk_ids", [])
            detail["doc_unique_id"] = doc_id

        elif op == "general_delete":
            ids = artifact["doc_unique_ids"]
            deleted_chunk_ids: list[int] = []
            write_detail: dict[str, Any] = {}
            for doc_id in ids:
                rows = store.fetch_doc_rows(doc_id)
                store.delete_doc(doc_id)
                n_sql = db.delete_doc_chunks(doc_id)
                chunk_ids = [int(r["chunk_id"]) for r in rows]
                db.outbox_record(doc_id, "write", "deleted", chunk_ids)
                deleted_chunk_ids.extend(chunk_ids)
                write_detail[doc_id] = {"lance_deleted": len(rows), "sqlite_deleted": n_sql}
            detail["steps"]["general_write"] = write_detail
            ctx = {"options": options, "doc_meta": doc_meta, "db": db, "store": store}
            detail["steps"]["general_post"] = registry["general_post"](ctx, artifact)
            detail["deleted_doc_count"] = len(ids)
            detail["deleted_chunk_ids"] = deleted_chunk_ids

        elif op == "general_reconcile":
            detail["reconcile"] = _general_reconcile(store, db)

        detail["elapsed_ms"] = round((time.monotonic() - t0) * 1000, 1)
        return validate_output({"code": "success", "op": op, "trace_id": payload["trace_id"],
                                "detail": detail, "error": ""})

    except Exception as exc:
        _general_queue_failure(op, artifact, exc, deps)
        return validate_output({"code": "error", "op": op, "trace_id": payload["trace_id"],
                                "detail": detail,
                                "error": f"{type(exc).__name__}: {exc}",
                                "_traceback": traceback.format_exc()[-500:]})


def _general_queue_failure(op: str, artifact: dict, exc: Exception,
                          deps: Deps | None = None) -> None:
    """异常按 retry_exception.yaml 分类落三级队列（落队列失败不掩盖主异常）。"""
    try:
        cls = _resolve_classifier(deps)(exc)
        db = _resolve_db(deps)
        if op == "general_delete":
            doc_id = (artifact.get("doc_unique_ids") or ["?"])[0]
        else:
            doc_id = _resolve_doc_id(deps)(artifact.get("tenant_id", "?"),
                                           artifact.get("file_md5", "?"))
        source_key = artifact.get("source_path", "")
        step = "unknown"
        queue, name = cls["queue"], type(exc).__name__
        if queue == "etl_general_failed":
            retry_at = (datetime.now(timezone.utc)
                        + timedelta(seconds=int(cls["backoff_seconds"]))).isoformat()
            db.add_failed(doc_id, source_key, step, name, str(exc),
                          int(cls["max_retries"]), next_retry_at=retry_at)
        elif queue == "etl_general_fatal":
            db.add_fatal(doc_id, source_key, step, name, str(exc))
        elif queue == "etl_general_empty_chunk":
            db.add_empty_chunk(doc_id, source_key, str(exc))
        db.outbox_record(doc_id, "write", "failed", last_error=str(exc))
    except Exception:
        pass


def _general_reconcile(store, db) -> dict[str, Any]:
    """三方对账（契约 §2.2 general_reconcile）：SQLite ↔ LanceDB ↔ outbox，孤儿向量回补 SQLite。"""

    lance_docs = set(store.list_doc_ids())
    sqlite_docs = set(db.list_doc_ids())

    orphan_chunk_ids: list[str] = []
    healed = 0
    for doc_id in sorted(lance_docs - sqlite_docs):
        rows = store.fetch_doc_rows(doc_id)
        orphan_chunk_ids.extend(str(int(r["chunk_id"])) for r in rows)
        backfill = [{
            "chunk_id": int(r["chunk_id"]), "doc_unique_id": doc_id,
            "tenant_id": str(r.get("tenant_id", "")), "biz_tag": str(r.get("biz_tag", "")),
            "chunk_seq": int(r.get("chunk_seq", 0)), "section_type": str(r.get("section_type", "")),
            "chunk_text": str(r.get("chunk_text", "")), "file_suffix": str(r.get("file_suffix", "")),
            "file_md5": str(r.get("file_md5", "")), "source_filename": str(r.get("source_filename", "")),
        } for r in rows]
        healed += len(db.write_chunks(backfill))

    missing_chunk_ids: list[str] = []
    for doc_id in sorted(sqlite_docs):
        lance_ids = {int(r["chunk_id"]) for r in store.fetch_doc_rows(doc_id)}
        sqlite_ids = {int(r["chunk_id"]) for r in db.fetch_doc_chunks(doc_id)}
        missing_chunk_ids.extend(str(c) for c in sorted(sqlite_ids - lance_ids))

    unready = sorted({r["doc_unique_id"] for r in db.outbox_pending_rows("pending")}
                     | {r["doc_unique_id"] for r in db.outbox_pending_rows("failed")})
    return {
        "orphan_lance_chunks": orphan_chunk_ids,
        "missing_sqlite_chunks": missing_chunk_ids,
        "outbox_unready_docs": unready,
        "self_healed": healed,
    }
