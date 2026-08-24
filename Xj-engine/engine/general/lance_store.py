"""general/lance_store.py — general_doc_db LanceDB 原语（风格对齐 engine/store.py）。

uri/table 一律由参数注入（storage.yaml → lancedb 节），本文件禁写默认路径。
操作面：建表 / 覆写写入（merge_insert 幂等）/ 按文档删 / 按 chunk_id 删 /
按文档回读 / 文档清单 / 行数 / 存在性校验 / 全表扫描（BM25 重建数据源）。
"""
from typing import Any

import lancedb


def build_schema(vector_dim: int) -> "Any":
    """general_doc_chunks 表结构（维度由 storage.yaml embedding 节注入）。

    chunk_id int64 / doc_unique_id / tenant_id / biz_tag / chunk_text /
    vector list<float32>[dim] / file_suffix / file_md5 / chunk_seq int32 /
    section_type / source_filename / created_at / meta(json string)
    """
    import pyarrow as pa
    return pa.schema([
        pa.field("chunk_id", pa.int64()),
        pa.field("doc_unique_id", pa.string()),
        pa.field("tenant_id", pa.string()),
        pa.field("biz_tag", pa.string()),
        pa.field("chunk_text", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), vector_dim)),
        pa.field("file_suffix", pa.string()),
        pa.field("file_md5", pa.string()),
        pa.field("chunk_seq", pa.int32()),
        pa.field("section_type", pa.string()),
        pa.field("source_filename", pa.string()),
        pa.field("created_at", pa.string()),
        pa.field("meta", pa.string()),
    ])


class GeneralLanceStore:
    def __init__(self, uri: str, table: str):
        if not uri or not table:
            raise ValueError("uri/table 必须由参数注入（storage.yaml），禁写默认值")
        self._db = lancedb.connect(uri)
        self._table_name = table
        self._table = None

    def _tbl(self):
        if self._table is None:
            self._table = self._db.open_table(self._table_name)
        return self._table

    def create_if_missing(self, schema) -> bool:
        """表不存在时按注入 schema 建表。返回是否新建。"""
        # lancedb 新版 list_tables() 返回 ListTablesResponse 对象（.tables 才是名单），
        # 直接 `name in response` 恒 False（实测）；旧版 table_names() 返回 list。
        lt = (self._db.list_tables() if hasattr(self._db, "list_tables")
              else self._db.table_names())
        names = getattr(lt, "tables", lt)
        if self._table_name in names:
            return False
        self._table = self._db.create_table(self._table_name, schema=schema)
        return True

    def write_overwrite(self, rows: list[dict[str, Any]]) -> list[int]:
        """按 chunk_id 覆写（同 ID 更新、新 ID 追加；重试不膨胀）。"""
        if not rows:
            return []
        import pyarrow as pa
        tbl = pa.Table.from_pylist(rows, schema=self._tbl().schema)
        (self._tbl().merge_insert("chunk_id")
         .when_matched_update_all().when_not_matched_insert_all().execute(tbl))
        return [int(r["chunk_id"]) for r in rows]

    def delete_doc(self, doc_unique_id: str) -> None:
        """按 doc_unique_id 删除该文档全部行。"""
        escaped = str(doc_unique_id).replace("'", "''")
        self._tbl().delete(f"doc_unique_id = '{escaped}'")

    def delete_chunk_ids(self, chunk_ids: list[int]) -> int:
        if not chunk_ids:
            return 0
        lit = ", ".join(str(int(c)) for c in chunk_ids)
        self._tbl().delete(f"chunk_id IN ({lit})")
        return len(chunk_ids)

    def fetch_doc_rows(self, doc_unique_id: str) -> list[dict[str, Any]]:
        """按 doc_unique_id 精确回读该文档全部行。"""
        escaped = str(doc_unique_id).replace("'", "''")
        df = (self._tbl().search().where(f"doc_unique_id = '{escaped}'")
              .limit(self._tbl().count_rows()).to_pandas())
        return df.to_dict("records") if not df.empty else []

    def list_doc_ids(self) -> list[str]:
        df = (self._tbl().search().select(["doc_unique_id"])
              .limit(self._tbl().count_rows()).to_pandas())
        return df["doc_unique_id"].dropna().unique().tolist() if not df.empty else []

    def count_rows(self) -> int:
        return self._tbl().count_rows()

    def check_chunks_exist(self, chunk_ids: list[int]) -> dict[int, bool]:
        if not chunk_ids:
            return {}
        lit = ", ".join(str(int(c)) for c in chunk_ids)
        df = (self._tbl().search().select(["chunk_id"])
              .where(f"chunk_id IN ({lit})").limit(len(chunk_ids)).to_pandas())
        found = set(int(c) for c in df["chunk_id"].tolist()) if not df.empty else set()
        return {int(c): int(c) in found for c in chunk_ids}

    def full_scan(self) -> "Any":
        """全表扫描（BM25 重建数据源；调用方自行裁剪列）。"""
        return self._tbl().search().limit(self._tbl().count_rows()).to_pandas()
