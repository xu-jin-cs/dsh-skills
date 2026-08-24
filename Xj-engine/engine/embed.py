"""embed.py — 嵌入计算（ETLEngine 自实现，与存量向量同模同参）。

模型契约唯一真源：contract_rules/storage.yaml `embedding.*`（台账 表1-#18 C5；
执行器禁写默认值与字面量，缺键即 RuleMissingError —— CONTRACT.md §一-2/§九-2）。
EMBED-LITERAL（2026-08-20 收口）：model/device/dimension 不再硬编码，
改读规则表；向量兼容前提 = 规则表值不被擅改（test_rules_consistency 看守）。
"""
import os

os.environ.setdefault("HF_HUB_OFFLINE", "0")        # standalone：首跑需拉取 BAAI/bge-m3 权重；离线环境显式置 1
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

from engine import rules_loader

_model = None


def _lazy_load():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(
            rules_loader.get("storage.embedding.model_name"),
            device=rules_loader.get("storage.embedding.device"),
        )


def compute_embeddings(texts: list[str]) -> list[list[float]]:
    """批量嵌入（与存量写入同语义：encode 默认参数，不归一化）。"""
    _lazy_load()
    return _model.encode(texts, show_progress_bar=False).tolist()
