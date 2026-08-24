"""worker.py — 通用文档 ETL Worker（契约 §六-2：仅调度标准 steps 流水线，零硬编码业务逻辑）。

payload 组装 + kernel 调度 + pending 批跑 + 失败重试的唯一定义处；
CLI（scripts/general_etl.py）只是本模块的命令行壳。
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine import general_stages
from engine.general.filehash import md5_file
from engine.kernel import etl_engine

logger = logging.getLogger("etl_engine.general_worker")


def build_ingest_payload(source_path: str, tenant_id: str, biz_tag: str = "",
                         extra_keywords: list | None = None,
                         steps: list | None = None, options: dict | None = None,
                         trace_id: str = "") -> dict:
    """按契约 §2.1/2.2/2.3 组装 general_ingest payload。"""
    path = Path(source_path)
    payload: dict[str, Any] = {
        "op": "general_ingest",
        "trace_id": trace_id or f"general-ingest-{uuid.uuid4().hex[:12]}",
        "doc_meta": {
            "file_suffix": path.suffix.lower().lstrip("."),
            "file_size": path.stat().st_size,
            "original_filename": path.name,
            "clean_filename": path.name,
            "upload_time": datetime.now(timezone.utc).isoformat(),
            "operator": "cli",
        },
        "artifact": {
            "source_path": str(path),
            "file_md5": md5_file(path),
            "tenant_id": tenant_id,
            "biz_tag": biz_tag,
            "storage_source": "local",
            "extra_keywords": extra_keywords or [],
        },
    }
    if steps:
        payload["steps"] = steps
    if options:
        payload["options"] = options
    return payload


def ingest_file(source_path: str, tenant_id: str, deps=None, **kw) -> dict:
    return etl_engine(build_ingest_payload(source_path, tenant_id, **kw), deps=deps)


def _payload_from_route_cache(doc_unique_id: str, trace_id: str, db=None) -> dict | None:
    """从 step_cache 的 __route__ 记录重建 payload（断点续跑元数据补齐，契约 §2.5）。"""
    db = db or general_stages.make_db()
    route = db.get_step(doc_unique_id, "__route__")
    if not route or not route["payload_ref"]:
        return None
    info = json.loads(route["payload_ref"])
    return build_ingest_payload(
        info["source_path"], info["tenant_id"], biz_tag=info.get("biz_tag", ""),
        extra_keywords=info.get("extra_keywords", []), trace_id=trace_id)


def run_pending(limit: int = 10, deps=None) -> dict:
    """批跑 outbox pending 文档（CLI run 的实现）。"""
    db = (deps.db if deps is not None and deps.db is not None else general_stages.make_db())
    rows = db.outbox_pending_rows("pending")[:limit]
    results = {}
    for row in rows:
        doc_id = row["doc_unique_id"]
        payload = _payload_from_route_cache(doc_id, f"general-run-{uuid.uuid4().hex[:8]}", db=db)
        if payload is None:
            results[doc_id] = {"code": "error", "error": "路由信息缺失，无法重建 payload"}
            continue
        res = etl_engine(payload, deps=deps)
        results[doc_id] = {"code": res["code"], "error": res.get("error", "")}
    return {"processed": len(results), "results": results}


def retry_failed(limit: int = 10, deps=None) -> dict:
    """重试 etl_general_failed 到期记录；耗尽移死信（CLI retry-failed 的实现）。"""
    db = (deps.db if deps is not None and deps.db is not None else general_stages.make_db())
    now = datetime.now(timezone.utc).isoformat()
    due = [r for r in db.list_failed("pending")
           if not r["next_retry_at"] or r["next_retry_at"] <= now][:limit]
    results = {}
    for row in due:
        doc_id = row["doc_unique_id"]
        payload = _payload_from_route_cache(doc_id, f"general-retry-{uuid.uuid4().hex[:8]}", db=db)
        if payload is None:
            db.add_retry_dead(doc_id, row["source_key"], row["step"],
                              "路由信息缺失，无法重建 payload",
                              [{"retry_count": row["retry_count"], "error_type": row["error_type"]}])
            db.delete_failed(row["id"])
            results[doc_id] = {"code": "error", "error": "路由信息缺失 → 死信"}
            continue
        res = etl_engine(payload, deps=deps)
        if res["code"] == "success":
            db.delete_failed(row["id"])
            results[doc_id] = {"code": "success"}
            continue
        retry_count = int(row["retry_count"]) + 1
        if retry_count >= int(row["max_retries"]):
            db.add_retry_dead(doc_id, row["source_key"], row["step"], res.get("error", ""),
                              [{"retry_count": retry_count, "error_type": row["error_type"]}])
            db.delete_failed(row["id"])
            results[doc_id] = {"code": "dead", "error": res.get("error", "")}
        else:
            db.bump_failed_retry(row["id"])
            results[doc_id] = {"code": "error", "retry_count": retry_count,
                               "error": res.get("error", "")}
    return {"retried": len(results), "results": results}


def stats(deps=None) -> dict:
    """分片/失败队列/对账差异统计（CLI stats 的实现）。"""
    db = (deps.db if deps is not None and deps.db is not None else general_stages.make_db())
    store = (deps.store if deps is not None and deps.store is not None else general_stages.make_store())
    return {
        "lance_rows": store.count_rows(),
        "sqlite_docs": len(db.list_doc_ids()),
        "outbox_pending": len(db.outbox_pending_rows("pending")),
        "failed_rows": len(db.list_failed("pending")),
        "fatal_rows": len(db.list_fatal()),
        "dead_rows": len(db.list_retry_dead()),
        "empty_chunk_rows": len(db.list_empty_chunks()),
    }
