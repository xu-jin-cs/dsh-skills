"""outbox 记账（参考 ETL v3.0：每文档 pending → ready / failed，reconcile 自愈兜底）。

独立 SQLite 默认落 ./data/etl_engine_outbox.db，可通过环境变量 ETL_OUTBOX_DB 覆盖；
不依赖任何外部平台数据库。
"""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

_DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "etl_engine_outbox.db"
DB_PATH = Path(os.environ.get("ETL_OUTBOX_DB", str(_DEFAULT_DB)))

_DDL = """
CREATE TABLE IF NOT EXISTS etl_outbox (
    doc_unique_id TEXT NOT NULL,
    op TEXT NOT NULL,               -- write / delete
    status TEXT NOT NULL,           -- pending / ready / failed / deleted
    chunk_ids TEXT NOT NULL DEFAULT '[]',
    detail TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (doc_unique_id, op)
)
"""


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), timeout=10)
    c.execute(_DDL)
    return c


def record(doc_unique_id: str, op: str, status: str, chunk_ids: list | None = None, detail: str = ""):
    with _conn() as c:
        c.execute(
            "INSERT INTO etl_outbox (doc_unique_id, op, status, chunk_ids, detail, updated_at) "
            "VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(doc_unique_id, op) DO UPDATE SET status=excluded.status, "
            "chunk_ids=excluded.chunk_ids, detail=excluded.detail, updated_at=excluded.updated_at",
            (doc_unique_id, op, status, json.dumps(chunk_ids or []), detail,
             datetime.now().isoformat()),
        )


def status_of(doc_unique_id: str, op: str = "write") -> str | None:
    with _conn() as c:
        row = c.execute(
            "SELECT status FROM etl_outbox WHERE doc_unique_id=? AND op=?",
            (doc_unique_id, op)).fetchone()
        return row[0] if row else None


def all_rows() -> list[dict]:
    with _conn() as c:
        cur = c.execute("SELECT doc_unique_id, op, status, chunk_ids, detail, updated_at FROM etl_outbox")
        return [{"doc_unique_id": r[0], "op": r[1], "status": r[2],
                 "chunk_ids": json.loads(r[3]), "detail": r[4], "updated_at": r[5]}
                for r in cur.fetchall()]
