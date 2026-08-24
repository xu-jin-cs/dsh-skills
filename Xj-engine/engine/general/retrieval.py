"""retrieval.py — 通用文档检索层（契约 §六-3：与 PDF 老检索、技能检索完全隔离）。

只读 general_doc_db（bge-m3 1024 维），出参复用顶层 code/trace_id 规范，
chunk 携带 source="general" 来源标识区分文档类型。
"""
import uuid
from typing import Any

from engine import embed, general_stages


def search(query: str, tenant_id: str = "", top_k: int = 5,
           trace_id: str = "", store=None) -> dict[str, Any]:
    out = {"code": "success", "op": "general_search",
           "trace_id": trace_id or f"general-search-{uuid.uuid4().hex[:12]}",
           "detail": {"chunks": []}, "error": ""}
    if not query.strip():
        out["code"] = "reject"
        out["error"] = "query 不能为空"
        return out
    try:
        store = store or general_stages.make_store()
        vec = embed.compute_embeddings([query])[0]
        q = store._tbl().search(vec)
        if tenant_id:
            # FIX-TENANT-ESC（2026-08-22 短板修复）：tenant_id 单引号转义，
            # 与 store.py / lance_store.py 的 where 拼接口径一致，堵注入面。
            escaped = str(tenant_id).replace("'", "''")
            q = q.where(f"tenant_id = '{escaped}'")
        df = q.limit(int(top_k)).to_pandas()
        chunks = [{
            "chunk_id": int(r["chunk_id"]),
            "doc_unique_id": str(r["doc_unique_id"]),
            "tenant_id": str(r.get("tenant_id", "")),
            "section_type": str(r.get("section_type", "")),
            "source": "general",
            "score": float(r.get("_distance", 0.0)),
            "chunk_text": str(r["chunk_text"]),
        } for _, r in df.iterrows()]
        out["detail"] = {"chunks": chunks, "hit_count": len(chunks)}
        return out
    except Exception as exc:
        out["code"] = "error"
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
