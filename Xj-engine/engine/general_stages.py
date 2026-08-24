"""general_stages.py — general 族 6 个参数化执行器（改造清单 v2 §2.4）。

铁律（契约 §一-2）：执行器读规则执行，代码零业务规则字面量；
规则全部经 rules_loader 注入，缺键即 RuleMissingError，无默认值兜底。
统一签名 (ctx, artifact) -> dict；GENERAL_STAGE_REGISTRY 由 stages.py 合并进 STAGE_REGISTRY。

异常类类名即 retry_exception.yaml classification 键（内核按类名查表分流）。
"""
import hashlib
import html as _html
import json
import logging
import re
import shutil
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from engine import embed, rules_loader
from engine.general import bm25_general, general_db as gdb_mod
from engine.general import lance_store as ls_mod
from engine.general import magic, parsers
from engine.general.filehash import md5_file

logger = logging.getLogger("etl_engine.general_stages")

# ── 并发串行化与 BM25 节流（2026-08-17 契约 §6 线1，单文件改造点）──
# general_write：LanceDB write_overwrite + SQLite write_chunks + outbox_record + 写后校验
# 整段串行化，防并发下双源写入交错。
_WRITE_LOCK = threading.Lock()
# BM25 重建节流：判定锁只护"判定+计数"，重建本身由重建锁互斥、在判定锁外执行。
# 规则：距上次重建 <60s 且期间文档数 <10 → 跳过本次重建。
_BM25_LOCK = threading.Lock()
_BM25_REBUILD_LOCK = threading.Lock()
_BM25_STATE = {"last_rebuild_ts": 0.0, "docs_since_last_rebuild": 0}
_BM25_THROTTLE_SECONDS = 60.0
_BM25_THROTTLE_DOCS = 10
# embed 串行化（2026-08-17 契约 §R3，解禁范围内增量）：consumer 6 线程并发 encode
# 共享单个 bge-m3/MPS 模型，GPU 争抢实测单文档 embed 90029ms（正常 371ms，劣化 240 倍）；
# 串行化消灭长尾，总吞吐不变。
_EMBED_LOCK = threading.Lock()


# ── 异常类（类名 = retry_exception.yaml classification 键，禁止改名）──
class ValidationException(Exception):
    pass


class FormatNotSupported(Exception):
    pass


class SizeExceeded(Exception):
    pass


class MagicMismatch(Exception):
    pass


class CorruptFile(Exception):
    pass


class EmptyContentException(Exception):
    pass


class EmbeddingTimeout(Exception):
    pass


# ── 规则访问与共享工厂 ──────────────────────────────────────────

def _rules() -> dict:
    return rules_loader.load_rules()


def make_db() -> "gdb_mod.GeneralDB":
    return gdb_mod.GeneralDB(rules_loader.get("storage.sqlite.path"))


def make_store() -> "ls_mod.GeneralLanceStore":
    store = ls_mod.GeneralLanceStore(
        rules_loader.get("storage.lancedb.uri"),
        rules_loader.get("storage.lancedb.table"),
    )
    store.create_if_missing(ls_mod.build_schema(rules_loader.get("storage.lancedb.vector_dim")))
    return store


def make_doc_id(tenant_id: str, file_md5: str) -> str:
    """稳定文档 ID：同租户同内容同 ID，重跑幂等覆写不膨胀。"""
    prefix = rules_loader.get("chunking.doc_id_prefix")
    return f"{prefix}-{tenant_id}-{file_md5[:16]}"


def _markers() -> dict:
    """cleaning.protected_markers 列表 → parsers 消费的键控字典（机械映射，如 [TABLE_START]→table_start）。"""
    out = {}
    for m in rules_loader.get("cleaning.protected_markers"):
        key = m.strip("[]").lower()
        out[key] = m
    return out


def _opt(ctx: dict, full_path: str, leaf: str):
    """options 覆盖取值（完整路径或叶子后缀），缺省回落规则表。契约保证 options 键已过白名单。"""
    options = ctx.get("options") or {}
    if full_path in options:
        return options[full_path]
    if leaf in options:
        return options[leaf]
    return rules_loader.get(full_path)


def _est_tokens(text: str) -> int:
    """token 粗估（中英文混合）：约 2 字符 1 token。"""
    return max(1, len(text) // 2)


# ── 步骤 1：general_validate ────────────────────────────────────

def general_validate(ctx: dict, artifact: dict) -> dict:
    val = _rules()["validation"]
    path = Path(artifact["source_path"])
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    doc_meta = ctx.get("doc_meta") or {}
    ext = str(doc_meta.get("file_suffix") or path.suffix.lower().lstrip(".")).lower()
    if ext in val["blocklist"] or ext not in val["whitelist"]:
        raise FormatNotSupported(f"Format not supported or blocked: {ext}")

    size = path.stat().st_size
    tiers = _opt(ctx, "validation.size_tiers", "size_tiers")
    if size > int(tiers["absolute_max_mb"]) * 1024 * 1024:
        raise SizeExceeded(f"File size {size} exceeds absolute_max_mb={tiers['absolute_max_mb']}")
    # 大小阈值仅用于 absolute_max_mb 硬拦截；引擎无异步队列/worker，
    # 所有文件不分层、同步走全链（FIX-ASYNC 拆桩：原 sync/async 打标零消费方，名存实亡已移除）

    fn = val["filename"]
    clean_name = path.name
    for ch in fn["forbidden_chars"]:
        clean_name = clean_name.replace(ch, "_")
    clean_name = "".join(c for c in clean_name if ord(c) >= 32)
    clean_name = clean_name[: int(fn["max_length"])]

    mg = val["magic"]
    if mg["enabled"] and ext in mg["check_extensions"]:
        if not magic.check_magic_bytes(str(path), ext):
            raise MagicMismatch(f"Magic bytes mismatch for extension: {ext}")

    file_md5 = artifact.get("file_md5") or md5_file(path)
    tenant_id = artifact["tenant_id"]
    doc_id = make_doc_id(tenant_id, file_md5)

    dedup_enabled = _opt(ctx, "validation.md5_dedup.enabled", "md5_dedup_enabled")
    db = ctx.get("db") or make_db()
    is_dup = False
    if dedup_enabled:
        # FIX-DEDUP-BYPASS（2026-08-22 短板修复）：去重判定优先于 force_reparse——
        # 判定始终执行并经 is_duplicate 上报（ctx.force_reparse_reason 标明放行语义）；
        # doc_id 由 tenant+md5 派生，已有 chunk 即重复（scope_key=tenant_id，台账 C6）
        is_dup = db.count_doc_chunks(doc_id) > 0
        # 仅 force_reparse（断点续跑/知情幂等重放）放行；无 force 的重复文档依旧拒绝
        if is_dup and not ctx.get("force_reparse"):
            raise ValidationException(f"Duplicate document in tenant {tenant_id} (md5={file_md5})")

    # 路由信息全量落 step_cache payload_ref（run/retry 重建 payload 的唯一依据，契约 §2.5）
    route_info = {
        "source_path": str(path), "file_md5": file_md5, "tenant_id": tenant_id,
        "biz_tag": artifact.get("biz_tag", ""), "storage_source": artifact.get("storage_source", "local"),
        "extra_keywords": artifact.get("extra_keywords", []),
    }
    db.set_step(doc_id, "__route__", "success", payload_ref=json.dumps(route_info, ensure_ascii=False))

    ctx.update({
        "doc_unique_id": doc_id,
        "file_md5": file_md5,
        "file_info": {"ext": ext, "size": size, "clean_filename": clean_name},
        "is_duplicate": is_dup,
    })
    return {"file_size": size, "is_duplicate": is_dup}


# ── 步骤 2：general_parse ───────────────────────────────────────

def general_parse(ctx: dict, artifact: dict) -> dict:
    p = _rules()["parsing"]
    fb = dict(p["fallback"])
    parser_rules = {
        "markdown": p["markdown"], "word": p["word"], "spreadsheet": p["spreadsheet"],
        "presentation": p["presentation"], "html": p["html"],
        "fallback": fb, "markers": _markers(),
        "parser_versions": p["parser_versions"],
    }
    try:
        doc = parsers.parse(artifact["source_path"], ctx["file_info"]["ext"], parser_rules)
    except parsers.CorruptFileError as exc:
        raise CorruptFile(str(exc)) from exc
    ctx["raw_document"] = doc
    return {
        "section_count": len(doc["sections"]),
        "parser_name": doc.get("parser_name", ""),
        "parser_version": doc.get("parser_version", ""),
        "is_degrade": doc.get("is_degrade", False),
    }


# ── 步骤 3：general_clean ───────────────────────────────────────

def _normalize(text: str, norm: dict) -> str:
    if norm["nfkc"]:
        text = unicodedata.normalize("NFKC", text)
    if norm["newline_to_lf"]:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    if norm["unescape_html_md"]:
        text = _html.unescape(text)
    if norm["fullwidth_halfwidth"]:
        text = "".join(
            chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else (" " if c == "　" else c)
            for c in text)
    if norm["collapse_spaces"]:
        text = re.sub(rf" {{{int(norm['space_threshold'])},}}", " ", text)
    if norm["strip_line_edges"]:
        text = "\n".join(line.strip() for line in text.split("\n"))
    return text.strip()


def _filter_redundancy(text: str, red: dict, protected: list[str]) -> str:
    if not red["enabled"]:
        return text
    out, prev, streak = [], None, 0
    dup_max = int(red["consecutive_duplicate_lines"])
    for line in text.split("\n"):
        if any(m in line for m in protected):
            out.append(line)
            prev, streak = None, 0
            continue
        s = line.strip()
        if red["drop_empty_lines"] and not s:
            continue
        if red["drop_pure_number_symbol_lines"] and len(line) < int(red["pure_number_symbol_max_len"]):
            if not any("一" <= c <= "鿿" for c in line) and re.match(r"^[\d\s\W]+$", line):
                continue
        if red["drop_single_letter_index"] and (re.match(r"^[a-zA-Z]$", s) or re.match(r"^\d+[.)]?$", s)):
            continue
        if red["drop_long_separator_lines"] and re.match(r"^[-*_=~]{10,}$", s):
            continue
        if line == prev:
            streak += 1
            if streak >= dup_max - 1:
                continue
        else:
            streak, prev = 0, line
        out.append(line)
    return "\n".join(out).strip()


def general_clean(ctx: dict, artifact: dict) -> dict:
    cfg = _rules()["cleaning"]
    norm, red = cfg["normalize"], cfg["redundancy"]
    protected = list(cfg["protected_markers"])
    nodes = []
    for sec in ctx["raw_document"]["sections"]:
        text = sec.get("text", "")
        if sec.get("type") == "code":
            text = _normalize(text, {**norm, "unescape_html_md": False,
                                     "fullwidth_halfwidth": False, "collapse_spaces": False})
        else:
            text = _filter_redundancy(_normalize(text, norm), red, protected)
        if text:
            nodes.append({**sec, "text": text})
    ctx["section_nodes"] = nodes
    ctx["clean_text"] = "\n".join(s["text"] for s in nodes)
    return {"sections_in": len(ctx["raw_document"]["sections"]), "sections_out": len(nodes)}


# ── 步骤 4：general_chunk ───────────────────────────────────────

def _chunk_id(tenant_id: str, doc_id: str, seq: int, text: str) -> int:
    tpl = _rules()["chunking"]["chunk_id_formula"]["general"]["template"]
    raw = tpl.format(tenant_id=tenant_id, doc_unique_id=doc_id, seq=seq, clean_text=text)
    h = hashlib.md5(raw.encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") & 0x7FFFFFFFFFFFFFFF


_SENT_BOUNDARY_CHARS = "。！？；.!?\n"


def _hard_split_oversized(chunks: list[dict], max_tok: int, overlap: int,
                          preserve: set) -> list[dict]:
    """超大 chunk 硬切兜底（2026-08-17 REFORM-GATE 判A，用户裁定）。

    单段自身超 max_tok 时（典型：无空行的长 txt/md/json 经 _parse_txt 成单段），
    段落累积逻辑不会切分，本后处理按窗口顺序切：窗口后半段内优先在句子边界
    （。！？；.!? 换行）断开，找不到则硬切；相邻块携带 overlap 字符尾巴衔接。
    preserve 类型（code 等）与 table（已有自切逻辑）不干预。
    """
    max_chars = max_tok * 2  # _est_tokens 口径：约 2 字符 1 token
    out: list[dict] = []
    for c in chunks:
        if c["section_type"] in preserve or _est_tokens(c["text"]) <= max_tok:
            out.append(c)
            continue
        text, start = c["text"], 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            if end < len(text):
                half = start + max_chars // 2
                for i in range(end - 1, half - 1, -1):
                    if text[i] in _SENT_BOUNDARY_CHARS:
                        end = i + 1
                        break
            piece = text[start:end].strip()
            if piece:
                out.append({"text": piece, "section_type": c["section_type"]})
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
    return out


def general_chunk(ctx: dict, artifact: dict) -> dict:
    ch = _rules()["chunking"]
    max_tok = int(_opt(ctx, "chunking.max_token", "max_token"))
    min_tok, overlap = int(ch["min_token"]), int(ch["overlap_token"])
    table_max = int(ch["table_max_single"])
    preserve = set(ch["preserve"]) | {"code"}  # code_block 契约名 ↔ section type code
    tenant_id, doc_id = artifact["tenant_id"], ctx["doc_unique_id"]

    chunks: list[dict] = []

    def emit(text: str, sec_type: str) -> None:
        chunks.append({"text": text, "section_type": sec_type})

    cur, cur_type = "", "paragraph"

    def flush() -> None:
        nonlocal cur
        if cur.strip():
            emit(cur.strip(), cur_type)
        cur = ""

    for sec in ctx["section_nodes"]:
        stype, text = sec.get("type", "paragraph"), sec.get("text", "")
        if stype == "title":
            flush()
            cur, cur_type = text, "paragraph"  # 标题带入下一 chunk（标题边界强制）
            continue
        if stype in ("table", "slide", "code"):
            flush()
            if stype == "table" and _est_tokens(text) > table_max:
                lines = text.split("\n")
                header, buf = lines[0], lines[0]
                for line in lines[1:]:
                    if _est_tokens(buf) + _est_tokens(line) > table_max and buf != header:
                        emit(buf, "table")
                        buf = header + "\n" + line
                    else:
                        buf += "\n" + line
                emit(buf, "table")
            else:
                emit(text, stype)
            continue
        # 段落/列表：累积到 max_token，带出 overlap 尾巴
        if cur and _est_tokens(cur) + _est_tokens(text) > max_tok:
            tail = cur[-overlap:] if overlap else ""
            flush()
            cur = tail + text
        else:
            cur = (cur + "\n" + text) if cur else text
        cur_type = "paragraph"
    flush()

    if ch["merge_small_chunks"]:
        merged: list[dict] = []
        for c in chunks:
            if (merged and _est_tokens(c["text"]) < min_tok
                    and c["section_type"] not in preserve
                    and merged[-1]["section_type"] not in preserve):
                merged[-1]["text"] += "\n" + c["text"]
            else:
                merged.append(c)
        chunks = merged

    # 超大 chunk 硬切兜底（merge 之后执行，兼捕 merge 回粘超限）：
    # 单段自身超 max_tok 时累积逻辑不会切（无空行长 txt/md/json 实证缺陷，2026-08-17 REFORM-GATE 判A）
    chunks = _hard_split_oversized(chunks, max_tok, overlap, preserve)

    if not chunks:
        raise EmptyContentException("No chunks produced after split")

    for i, c in enumerate(chunks, 1):
        c["chunk_id"] = _chunk_id(tenant_id, doc_id, i, c["text"])
        c["chunk_seq"] = i
    ctx["chunk_list"] = chunks
    ctx["chunk_ids"] = [c["chunk_id"] for c in chunks]
    return {"chunk_count": len(chunks), "chunk_ids": ctx["chunk_ids"]}


# ── 步骤 5：general_write ───────────────────────────────────────

def general_write(ctx: dict, artifact: dict) -> dict:
    emb_cfg = _rules()["storage"]["embedding"]
    chunks = ctx["chunk_list"]
    texts = [c["text"] for c in chunks]
    if emb_cfg["empty_text_skip"]:
        pairs = [(c, t) for c, t in zip(chunks, texts) if t.strip()]
    else:
        pairs = list(zip(chunks, texts))
    if not pairs:
        raise EmptyContentException("All chunks empty after skip")

    vectors: list[list[float]] = []
    bs = int(emb_cfg["batch_size"])
    last_exc: Exception | None = None
    t_embed_start = time.perf_counter()
    with _EMBED_LOCK:  # embed 串行化（契约 §R3）：encode 全程互斥，消灭 MPS 争抢长尾
        for i in range(0, len(pairs), bs):
            batch = [t for _, t in pairs[i:i + bs]]
            for attempt in range(int(emb_cfg["max_retries"])):
                try:
                    vectors.extend(embed.compute_embeddings(batch))
                    last_exc = None
                    break
                except Exception as exc:  # 资源类故障按表重试
                    last_exc = exc
                    time.sleep(int(emb_cfg["retry_interval_seconds"]))
            if last_exc is not None:
                raise EmbeddingTimeout(f"embedding batch {i // bs} failed: {last_exc}")
    embed_ms = (time.perf_counter() - t_embed_start) * 1000.0

    file_info = ctx["file_info"]
    tenant_id, doc_id = artifact["tenant_id"], ctx["doc_unique_id"]
    now = datetime.now(timezone.utc).isoformat()
    store = ctx.get("store") or make_store()
    # 文档级聚合锚（chunking.yaml meta_assembly_anchor，2026-08-24 用户提案）：
    # 首 chunk 的 chunk_id 注入所有 chunk 的 meta，重组契约见 docs/reassembly_contract.md
    anchor_cfg = rules_loader.get("chunking.meta_assembly_anchor")
    parent_chunk_id = pairs[0][0]["chunk_id"] if (anchor_cfg.get("enabled") and pairs) else None
    anchor_field = anchor_cfg.get("field", "parent_chunk_id")
    lance_rows, db_rows = [], []
    for (c, _), vec in zip(pairs, vectors):
        meta = {"id_meta": {"channel": "general", "tenant_id": tenant_id},
                "biz_tag": artifact.get("biz_tag", ""),
                "keywords": artifact.get("extra_keywords", [])}
        if parent_chunk_id is not None:
            meta[anchor_field] = parent_chunk_id
        lance_rows.append({
            "chunk_id": c["chunk_id"], "doc_unique_id": doc_id, "tenant_id": tenant_id,
            "biz_tag": artifact.get("biz_tag", ""), "chunk_text": c["text"], "vector": vec,
            "file_suffix": file_info["ext"], "file_md5": ctx["file_md5"],
            "chunk_seq": c["chunk_seq"], "section_type": c["section_type"],
            "source_filename": file_info["clean_filename"], "created_at": now,
            "meta": json.dumps(meta, ensure_ascii=False),
        })
        db_rows.append({
            "chunk_id": c["chunk_id"], "doc_unique_id": doc_id, "tenant_id": tenant_id,
            "biz_tag": artifact.get("biz_tag", ""), "chunk_seq": c["chunk_seq"],
            "section_type": c["section_type"], "chunk_text": c["text"],
            "file_suffix": file_info["ext"], "file_md5": ctx["file_md5"],
            "source_filename": file_info["clean_filename"], "created_at": now,
        })
    t_write_start = time.perf_counter()
    t_lock_start = time.monotonic()
    _WRITE_LOCK.acquire()  # 写段串行化（契约 §6）+ lock_wait 显式计时（契约 §R3）
    lock_wait_ms = (time.monotonic() - t_lock_start) * 1000.0
    try:
        chunk_ids = store.write_overwrite(lance_rows)
        db = ctx.get("db") or make_db()
        db.write_chunks(db_rows)
        db.outbox_record(doc_id, "write", "ready", chunk_ids, expected_chunks=len(lance_rows))

        # 写后校验：双源计数一致（不一致 → 未登记异常走 resource 重试 + 对账兜底）
        actual = len(store.fetch_doc_rows(doc_id))
    finally:
        _WRITE_LOCK.release()
    write_ms = (time.perf_counter() - t_write_start) * 1000.0
    if actual != len(lance_rows):
        raise RuntimeError(f"post-write verify mismatch: expected={len(lance_rows)} actual={actual}")

    total_ms = embed_ms + write_ms
    logger.info("[ETL-PROF] doc=%s embed=%.0fms lance=%.0fms lock_wait=%.0fms chunks=%d total=%.0fms",
                doc_id, embed_ms, write_ms, lock_wait_ms, len(lance_rows), total_ms)

    result = {"lance_write_count": len(lance_rows), "sqlite_write_count": len(db_rows)}
    ctx["vector_write_result"] = result
    ctx["outbox_record_id"] = doc_id
    return result


# ── 步骤 6：general_post ────────────────────────────────────────

def general_post(ctx: dict, artifact: dict) -> dict:
    doc_id = ctx.get("doc_unique_id", artifact.get("doc_unique_id", ""))
    t_bm25_start = time.perf_counter()

    # BM25 重建节流（契约 §6）：判定锁只护"判定+计数"，重建在锁外由重建锁互斥执行。
    # 规则：距上次重建 <60s 且期间文档数 <10 → 跳过本次重建。
    skipped = False
    skip_reason = ""
    do_rebuild = False
    with _BM25_LOCK:
        _BM25_STATE["docs_since_last_rebuild"] += 1
        since_last = time.monotonic() - _BM25_STATE["last_rebuild_ts"]
        if (since_last < _BM25_THROTTLE_SECONDS
                and _BM25_STATE["docs_since_last_rebuild"] < _BM25_THROTTLE_DOCS):
            skipped = True
            skip_reason = (f"throttled: {since_last:.1f}s<{_BM25_THROTTLE_SECONDS:.0f}s "
                           f"and docs={_BM25_STATE['docs_since_last_rebuild']}<{_BM25_THROTTLE_DOCS}")
        else:
            do_rebuild = True

    index_stats: dict = {"skipped": skipped}
    if do_rebuild:
        with _BM25_REBUILD_LOCK:  # 重建互斥：并发 ingest 只许一路做全量重建
            store = ctx.get("store") or make_store()
            index_stats = bm25_general.rebuild(store, rules_loader.get("storage.bm25_index_dir"))
            with _BM25_LOCK:
                _BM25_STATE["last_rebuild_ts"] = time.monotonic()
                _BM25_STATE["docs_since_last_rebuild"] = 0

    bm25_ms = (time.perf_counter() - t_bm25_start) * 1000.0
    if skipped:
        logger.info("[ETL-PROF] doc=%s bm25=%.0fms skipped=%s reason=%s",
                    doc_id, bm25_ms, skipped, skip_reason)
    else:
        logger.info("[ETL-PROF] doc=%s bm25=%.0fms skipped=%s", doc_id, bm25_ms, skipped)

    retention = _opt(ctx, "validation.tmp_retention", "tmp_retention")
    tmp_dir = Path(rules_loader.get("storage.tmp_dir")).expanduser()
    cleaned = 0
    if tmp_dir.exists():
        db = ctx.get("db") or make_db()
        now = datetime.now(timezone.utc)
        for doc_dir in (d for d in tmp_dir.iterdir() if d.is_dir()):
            status = db.outbox_status_of(doc_dir.name, "write")
            hours = retention["success_hours"] if status == "ready" else retention["failure_hours"]
            mtime = datetime.fromtimestamp(doc_dir.stat().st_mtime, tz=timezone.utc)
            if mtime < now - timedelta(hours=int(hours)):
                shutil.rmtree(doc_dir, ignore_errors=True)
                cleaned += 1
    ctx["index_status"] = index_stats
    ctx["temp_clean_count"] = cleaned
    return {"bm25": index_stats, "temp_cleaned": cleaned}


# ── 异常分类（内核消费：类名查表 → 队列/重试策略）─────────────

def classify_exception(exc: Exception) -> dict:
    cfg = _rules()["retry_exception"]
    name = type(exc).__name__
    hit = cfg["classification"].get(name) or cfg["defaults"].get(name) or cfg["defaults"]["unregistered"]
    return dict(hit)


GENERAL_STAGE_REGISTRY = {
    "general_validate": general_validate,
    "general_parse": general_parse,
    "general_clean": general_clean,
    "general_chunk": general_chunk,
    "general_write": general_write,
    "general_post": general_post,
}
