"""general/general_db.py — general_etl.db SQLite 原语（raw sqlite3，风格对齐 engine/outbox.py）。

db 路径由参数注入（storage.yaml → sqlite 节），本文件禁写默认路径。
7 表：doc_chunk_general / general_doc_etl_step_cache / outbox /
etl_general_failed / etl_general_fatal / etl_general_retry_dead / etl_general_empty_chunk。
表名即契约（台账 #19 / 清单 §五），由本文件 DDL 自举，不作规则注入。
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

_DDL = """
CREATE TABLE IF NOT EXISTS doc_chunk_general (
    chunk_id INTEGER PRIMARY KEY,
    doc_unique_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    biz_tag TEXT NOT NULL DEFAULT '',
    chunk_seq INTEGER NOT NULL,
    section_type TEXT NOT NULL DEFAULT '',
    chunk_text TEXT NOT NULL,
    file_suffix TEXT NOT NULL DEFAULT '',
    file_md5 TEXT NOT NULL DEFAULT '',
    source_filename TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dcg_doc ON doc_chunk_general(doc_unique_id);

CREATE TABLE IF NOT EXISTS general_doc_etl_step_cache (
    doc_unique_id TEXT NOT NULL,
    step TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_ref TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (doc_unique_id, step)
);

CREATE TABLE IF NOT EXISTS outbox (
    doc_unique_id TEXT NOT NULL,
    op TEXT NOT NULL,
    status TEXT NOT NULL,
    chunk_ids TEXT NOT NULL DEFAULT '[]',
    expected_chunks INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (doc_unique_id, op)
);

CREATE TABLE IF NOT EXISTS etl_general_failed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_unique_id TEXT NOT NULL,
    source_key TEXT NOT NULL DEFAULT '',
    step TEXT NOT NULL DEFAULT '',
    error_type TEXT NOT NULL DEFAULT '',
    error_msg TEXT NOT NULL DEFAULT '',
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS etl_general_fatal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_unique_id TEXT NOT NULL,
    source_key TEXT NOT NULL DEFAULT '',
    step TEXT NOT NULL DEFAULT '',
    error_type TEXT NOT NULL DEFAULT '',
    error_msg TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS etl_general_retry_dead (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_unique_id TEXT NOT NULL,
    source_key TEXT NOT NULL DEFAULT '',
    last_step TEXT NOT NULL DEFAULT '',
    final_error TEXT NOT NULL DEFAULT '',
    retry_history_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS etl_general_empty_chunk (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_unique_id TEXT NOT NULL,
    source_key TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now().isoformat()


class GeneralDB:
    def __init__(self, path: str):
        if not path:
            raise ValueError("db path 必须由参数注入（storage.yaml），禁写默认值")
        self._path = Path(path).expanduser()  # storage.yaml 含 ~ 家目录缩写必须展开
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(_DDL)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._path), timeout=10)

    # ---------------------------------------------------------- step_cache
    def set_step(self, doc_unique_id: str, step: str, status: str,
                 payload_ref: str = "", last_error: str = "") -> None:
        """步骤断点写入（upsert；attempts 自增，供断点续跑按 trace 恢复）。"""
        with self._conn() as c:
            c.execute(
                "INSERT INTO general_doc_etl_step_cache "
                "(doc_unique_id, step, status, payload_ref, last_error, attempts, updated_at) "
                "VALUES (?,?,?,?,?,1,?) "
                "ON CONFLICT(doc_unique_id, step) DO UPDATE SET status=excluded.status, "
                "payload_ref=excluded.payload_ref, last_error=excluded.last_error, "
                "attempts=attempts+1, updated_at=excluded.updated_at",
                (doc_unique_id, step, status, payload_ref, last_error, _now()))

    def get_step(self, doc_unique_id: str, step: str) -> dict | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT step, status, payload_ref, last_error, attempts, updated_at "
                "FROM general_doc_etl_step_cache WHERE doc_unique_id=? AND step=?",
                (doc_unique_id, step)).fetchone()
        if not row:
            return None
        return {"step": row[0], "status": row[1], "payload_ref": row[2],
                "last_error": row[3], "attempts": row[4], "updated_at": row[5]}

    def get_steps(self, doc_unique_id: str) -> list[dict]:
        with self._conn() as c:
            cur = c.execute(
                "SELECT step, status, payload_ref, last_error, attempts, updated_at "
                "FROM general_doc_etl_step_cache WHERE doc_unique_id=? ORDER BY updated_at",
                (doc_unique_id,))
            return [{"step": r[0], "status": r[1], "payload_ref": r[2],
                     "last_error": r[3], "attempts": r[4], "updated_at": r[5]}
                    for r in cur.fetchall()]

    # ---------------------------------------------------------- outbox
    def outbox_record(self, doc_unique_id: str, op: str, status: str,
                      chunk_ids: list | None = None, expected_chunks: int = 0,
                      last_error: str = "") -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO outbox (doc_unique_id, op, status, chunk_ids, "
                "expected_chunks, last_error, updated_at) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(doc_unique_id, op) DO UPDATE SET status=excluded.status, "
                "chunk_ids=excluded.chunk_ids, expected_chunks=excluded.expected_chunks, "
                "last_error=excluded.last_error, updated_at=excluded.updated_at",
                (doc_unique_id, op, status, json.dumps(chunk_ids or []),
                 expected_chunks, last_error, _now()))

    def outbox_status_of(self, doc_unique_id: str, op: str = "write") -> str | None:
        with self._conn() as c:
            row = c.execute("SELECT status FROM outbox WHERE doc_unique_id=? AND op=?",
                            (doc_unique_id, op)).fetchone()
            return row[0] if row else None

    def outbox_pending_rows(self, status: str = "pending") -> list[dict]:
        with self._conn() as c:
            cur = c.execute(
                "SELECT doc_unique_id, op, status, chunk_ids, expected_chunks, "
                "last_error, updated_at FROM outbox WHERE status=?", (status,))
            return [{"doc_unique_id": r[0], "op": r[1], "status": r[2],
                     "chunk_ids": json.loads(r[3]), "expected_chunks": r[4],
                     "last_error": r[5], "updated_at": r[6]} for r in cur.fetchall()]

    def outbox_mark_done(self, doc_unique_id: str, op: str,
                         status: str = "ready") -> None:
        with self._conn() as c:
            c.execute("UPDATE outbox SET status=?, updated_at=? "
                      "WHERE doc_unique_id=? AND op=?",
                      (status, _now(), doc_unique_id, op))

    # ---------------------------------------------------------- failed（可重试队列）
    def add_failed(self, doc_unique_id: str, source_key: str, step: str,
                   error_type: str, error_msg: str, max_retries: int,
                   next_retry_at: str = "") -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO etl_general_failed (doc_unique_id, source_key, step, "
                "error_type, error_msg, retry_count, max_retries, next_retry_at, "
                "status, created_at) VALUES (?,?,?,?,?,0,?,?,'pending',?)",
                (doc_unique_id, source_key, step, error_type, error_msg,
                 max_retries, next_retry_at, _now()))
            return int(cur.lastrowid)

    def list_failed(self, status: str = "pending") -> list[dict]:
        with self._conn() as c:
            cur = c.execute(
                "SELECT id, doc_unique_id, source_key, step, error_type, error_msg, "
                "retry_count, max_retries, next_retry_at, status, created_at "
                "FROM etl_general_failed WHERE status=? ORDER BY id", (status,))
            return [{"id": r[0], "doc_unique_id": r[1], "source_key": r[2],
                     "step": r[3], "error_type": r[4], "error_msg": r[5],
                     "retry_count": r[6], "max_retries": r[7],
                     "next_retry_at": r[8], "status": r[9], "created_at": r[10]}
                    for r in cur.fetchall()]

    def bump_failed_retry(self, failed_id: int, next_retry_at: str = "",
                          last_status: str = "pending") -> None:
        """重试计数 +1 并更新下次重试时间。"""
        with self._conn() as c:
            c.execute("UPDATE etl_general_failed SET retry_count=retry_count+1, "
                      "next_retry_at=?, status=? WHERE id=?",
                      (next_retry_at, last_status, failed_id))

    def delete_failed(self, failed_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM etl_general_failed WHERE id=?", (failed_id,))

    # ---------------------------------------------------------- fatal（致命死信）
    def add_fatal(self, doc_unique_id: str, source_key: str, step: str,
                  error_type: str, error_msg: str) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO etl_general_fatal (doc_unique_id, source_key, step, "
                "error_type, error_msg, created_at) VALUES (?,?,?,?,?,?)",
                (doc_unique_id, source_key, step, error_type, error_msg, _now()))
            return int(cur.lastrowid)

    def list_fatal(self) -> list[dict]:
        with self._conn() as c:
            cur = c.execute(
                "SELECT id, doc_unique_id, source_key, step, error_type, error_msg, "
                "created_at FROM etl_general_fatal ORDER BY id")
            return [{"id": r[0], "doc_unique_id": r[1], "source_key": r[2],
                     "step": r[3], "error_type": r[4], "error_msg": r[5],
                     "created_at": r[6]} for r in cur.fetchall()]

    def delete_fatal(self, fatal_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM etl_general_fatal WHERE id=?", (fatal_id,))

    # ---------------------------------------------------------- retry_dead（重试耗尽）
    def add_retry_dead(self, doc_unique_id: str, source_key: str, last_step: str,
                       final_error: str, retry_history: list) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO etl_general_retry_dead (doc_unique_id, source_key, "
                "last_step, final_error, retry_history_json, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (doc_unique_id, source_key, last_step, final_error,
                 json.dumps(retry_history), _now()))
            return int(cur.lastrowid)

    def list_retry_dead(self) -> list[dict]:
        with self._conn() as c:
            cur = c.execute(
                "SELECT id, doc_unique_id, source_key, last_step, final_error, "
                "retry_history_json, created_at FROM etl_general_retry_dead ORDER BY id")
            return [{"id": r[0], "doc_unique_id": r[1], "source_key": r[2],
                     "last_step": r[3], "final_error": r[4],
                     "retry_history": json.loads(r[5]), "created_at": r[6]}
                    for r in cur.fetchall()]

    def delete_retry_dead(self, dead_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM etl_general_retry_dead WHERE id=?", (dead_id,))

    # ---------------------------------------------------------- empty_chunk（空文档登记）
    def add_empty_chunk(self, doc_unique_id: str, source_key: str, reason: str) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO etl_general_empty_chunk (doc_unique_id, source_key, "
                "reason, created_at) VALUES (?,?,?,?)",
                (doc_unique_id, source_key, reason, _now()))
            return int(cur.lastrowid)

    def list_empty_chunks(self) -> list[dict]:
        with self._conn() as c:
            cur = c.execute(
                "SELECT id, doc_unique_id, source_key, reason, created_at "
                "FROM etl_general_empty_chunk ORDER BY id")
            return [{"id": r[0], "doc_unique_id": r[1], "source_key": r[2],
                     "reason": r[3], "created_at": r[4]} for r in cur.fetchall()]

    def delete_empty_chunk(self, empty_id: int) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM etl_general_empty_chunk WHERE id=?", (empty_id,))

    # ---------------------------------------------------------- chunk 元数据
    def write_chunks(self, rows: list[dict]) -> list[int]:
        """chunk 元数据批量写（chunk_id 主键 REPLACE，重试幂等）。

        row 键：chunk_id/doc_unique_id/tenant_id/biz_tag/chunk_seq/section_type/
        chunk_text/file_suffix/file_md5/source_filename（created_at 缺省补当前）。
        """
        if not rows:
            return []
        with self._conn() as c:
            c.executemany(
                "INSERT OR REPLACE INTO doc_chunk_general (chunk_id, doc_unique_id, "
                "tenant_id, biz_tag, chunk_seq, section_type, chunk_text, file_suffix, "
                "file_md5, source_filename, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [(int(r["chunk_id"]), r["doc_unique_id"], r["tenant_id"],
                  r.get("biz_tag", ""), int(r["chunk_seq"]), r.get("section_type", ""),
                  r["chunk_text"], r.get("file_suffix", ""), r.get("file_md5", ""),
                  r.get("source_filename", ""), r.get("created_at") or _now())
                 for r in rows])
        return [int(r["chunk_id"]) for r in rows]

    def delete_doc_chunks(self, doc_unique_id: str) -> int:
        """按 doc 删除 chunk 元数据，返回删除行数。"""
        with self._conn() as c:
            cur = c.execute("DELETE FROM doc_chunk_general WHERE doc_unique_id=?",
                            (doc_unique_id,))
            return int(cur.rowcount)

    def count_doc_chunks(self, doc_unique_id: str) -> int:
        with self._conn() as c:
            row = c.execute("SELECT COUNT(*) FROM doc_chunk_general "
                            "WHERE doc_unique_id=?", (doc_unique_id,)).fetchone()
            return int(row[0])

    def fetch_doc_chunks(self, doc_unique_id: str) -> list[dict]:
        """按 doc 回读 chunk 元数据（对账/断点续跑元数据补齐用）。"""
        with self._conn() as c:
            cur = c.execute(
                "SELECT chunk_id, doc_unique_id, tenant_id, biz_tag, chunk_seq, "
                "section_type, chunk_text, file_suffix, file_md5, source_filename, "
                "created_at FROM doc_chunk_general WHERE doc_unique_id=? "
                "ORDER BY chunk_seq", (doc_unique_id,))
            keys = ["chunk_id", "doc_unique_id", "tenant_id", "biz_tag", "chunk_seq",
                    "section_type", "chunk_text", "file_suffix", "file_md5",
                    "source_filename", "created_at"]
            return [dict(zip(keys, r)) for r in cur.fetchall()]

    def list_doc_ids(self) -> list[str]:
        """doc_chunk_general 全量文档 ID（三方对账数据源，U3 集成补登）。"""
        with self._conn() as c:
            cur = c.execute("SELECT DISTINCT doc_unique_id FROM doc_chunk_general")
            return [r[0] for r in cur.fetchall()]
