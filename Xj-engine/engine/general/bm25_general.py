"""general/bm25_general.py — 通用文档单分区 BM25 索引（ETLEngine 自实现）。

tokenize 与 engine/bm25.py 同法（中文按字 + 英文按词），索引兼容前提。
落盘 {index_dir}/general.pkl，格式 {documents, chunk_ids, metadata}
与既有 BM25Partition 同构，检索方读取无感。index_dir 由参数注入，无默认值。
"""
import logging
import os
import pickle
import re

from rank_bm25 import BM25Okapi

logger = logging.getLogger("etl_engine.general.bm25")

INDEX_FILENAME = "general.pkl"  # 单分区固定文件名（清单 §一架构登记，非业务规则）


def tokenize(text: str) -> list[str]:
    """中文按字 + 英文按词（与 engine/bm25.py 同法）。"""
    return re.findall(r"[一-鿿]|[a-zA-Z0-9]+", text)


def rebuild(store, index_dir: str) -> dict:
    """从 GeneralLanceStore 全量扫描重建单分区 BM25 并落盘。返回分区文档数。"""
    if not index_dir:
        raise ValueError("index_dir 必须由参数注入（storage.yaml），禁写默认值")
    n = store.count_rows()
    if n == 0:
        return {"general": 0, "skipped": "empty table"}
    df = store.full_scan()
    os.makedirs(index_dir, exist_ok=True)
    docs = df["chunk_text"].astype(str).tolist()
    chunk_ids = [str(c) for c in df["chunk_id"].tolist()]
    metadata = [{"doc_unique_id": str(d), "tenant_id": str(t),
                 "biz_tag": str(b), "section_type": str(s)}
                for d, t, b, s in zip(df["doc_unique_id"].tolist(),
                                      df["tenant_id"].tolist(),
                                      df["biz_tag"].tolist(),
                                      df["section_type"].tolist())]
    tokenized = [tokenize(d) for d in docs]
    index = BM25Okapi(tokenized)  # noqa: F841  (构建即校验；持久化存语料，加载方重建)
    path = os.path.join(index_dir, INDEX_FILENAME)
    with open(path, "wb") as f:
        pickle.dump({"documents": docs, "chunk_ids": chunk_ids,
                     "metadata": metadata}, f)
    logger.info("BM25 [general] 重建完成: %d 文档 → %s", len(docs), path)
    return {"general": len(docs), "path": path}
