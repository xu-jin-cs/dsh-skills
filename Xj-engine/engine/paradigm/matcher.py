"""matchSignals 打分匹配器（唯一实现）。

固化公式（2026-11-09 用户规格）：
    Score = 强正向命中数 × 2 + 弱正向命中数 × 1 − 负向命中数 × 2
    confidence = (最高分 − 次高分) / (最高分 + 1)      # 差距法，衡量第一与第二拉开多少

三档判定：
    confidence ≥ autoThreshold(0.6)      → auto     自动采信
    reviewThreshold(0.3) ≤ c < auto      → review   人工复核（可覆盖）
    c < reviewThreshold                  → blocked  强制人工指定，禁止自动流转

同分：按 spec.order()（paradigms.json.matchOrder 派生）取更轻范式作为「建议项」；但同分会让 confidence=0 → 仍进入 blocked，
这是规格 1.2（同分取轻）与 1.3（低置信阻断）的叠加结果，必须在日志里显式标注 tie。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from . import spec

CACHE_FILE = spec.STATE_DIR / "match_cache.json"
CACHE_MAX = 2000


def normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def input_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()[:16]


# ── 语义模式（可插拔；缺模型即显式降级，不许假装） ──────────────
_SEM_CACHE: dict = {}


def _load_embedder(model_path: str):
    if model_path in _SEM_CACHE:
        return _SEM_CACHE[model_path]
    try:
        from sentence_transformers import SentenceTransformer  # noqa: WPS433
        m = SentenceTransformer(model_path)
        _SEM_CACHE[model_path] = m
        return m
    except Exception:  # noqa: BLE001 缺依赖/缺模型都回落词法
        _SEM_CACHE[model_path] = None
        return None


def _semantic_hit(text: str, phrase: str, model, threshold: float) -> bool:
    try:
        import numpy as np
        a, b = model.encode([text, phrase], normalize_embeddings=True)
        return float(np.dot(a, b)) >= threshold
    except Exception:  # noqa: BLE001
        return False


# ── 打分 ────────────────────────────────────────────────────────
def score_all(text: str, mode: str | None = None, embed_model: str | None = None,
              verbose: bool = False) -> tuple[list[dict], list[str], str]:
    low = normalize(text)
    mode = (mode or spec.match_mode()).lower()
    warnings: list[str] = []
    model = None
    threshold = float(spec.matcher_cfg().get("semanticThreshold", 0.75))
    if mode == "semantic":
        mp = embed_model or os.environ.get("PARADIGM_EMBED_MODEL", "")
        model = _load_embedder(mp) if mp else None
        if model is None:
            warnings.append("semantic_unavailable_fallback_lexical："
                            f"本地嵌入模型不可用（PARADIGM_EMBED_MODEL={mp!r}），已回退词法匹配")
            mode = "lexical"

    rows = []
    for p in spec.paradigms():
        sig = spec.signals(p)
        hit = {}
        for key in ("strong", "weak", "negative"):
            if mode == "semantic" and model is not None:
                hits = [w for w in sig[key] if _semantic_hit(low, w, model, threshold)]
            else:
                hits = [w for w in sig[key] if w.lower() in low]
            hit[key] = hits
        score = 2 * len(hit["strong"]) + 1 * len(hit["weak"]) - 2 * len(hit["negative"])
        row = {"paradigm": p["id"], "score": score,
               "strongHits": hit["strong"], "weakHits": hit["weak"],
               "negativeHits": hit["negative"]}
        if verbose:
            row["hitSignalList"] = [f"{k}:{w}" for k in ("strong", "weak", "negative") for w in hit[k]]
        rows.append(row)
    return rows, warnings, mode


def confidence_of(rows: list[dict]) -> tuple[int, int, float, bool]:
    ordered = sorted(rows, key=lambda r: r["score"], reverse=True)
    top = ordered[0]["score"] if ordered else 0
    second = ordered[1]["score"] if len(ordered) > 1 else 0
    denom = top + 1
    conf = (top - second) / denom if denom > 0 else 0.0
    conf = max(0.0, min(1.0, conf))
    tie = top == second
    return top, second, round(conf, 4), tie


def _cache_get(key: str) -> dict | None:
    try:
        d = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return (d.get("entries") or {}).get(key)
    except (OSError, ValueError):
        return None


def _cache_put(key: str, value: dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        d = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.is_file() else {}
        entries = d.get("entries") or {}
        entries[key] = value
        if len(entries) > CACHE_MAX:                      # 简单 FIFO 截断
            for k in list(entries)[: len(entries) - CACHE_MAX]:
                entries.pop(k, None)
        CACHE_FILE.write_text(json.dumps(
            {"paradigmVersion": spec.paradigm_version(), "entries": entries},
            ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def decide(text: str, *, override: str | None = None, mode: str | None = None,
           use_cache: bool = True, embed_model: str | None = None,
           skip: bool | None = None) -> dict:
    """返回完整判定；不写业务库、不联网（语义模式只读本地模型）。"""
    skip = spec.skip_selector() if skip is None else skip
    h = input_hash(text)
    cfg = spec.matcher_cfg()
    auto_th, review_th = spec.thresholds()

    if override:
        if not spec.by_id(override):
            raise ValueError(f"override 范式不存在：{override!r}")
        # G6：override 必须留痕原始自动建议，不得把 suggested 覆盖成 override 本身
        _rows, _warns, _ = score_all(text, mode=mode, embed_model=embed_model, verbose=False)
        _top, _second, _conf, _tie = confidence_of(_rows)
        _best = max(_rows, key=lambda r: r["score"]) if _rows else {"paradigm": None}
        _auto = (not _tie) and _top >= 2 and _second < _top and _conf >= auto_th
        return {"inputHash": h, "mode": "override", "skip": skip, "override": True,
                "paradigm": override, "suggested": override, "confidence": 1.0,
                "decision": "override", "tie": False, "cacheHit": False,
                "suggestedByMatch": {"paradigm": _best.get("paradigm"),
                                     "confidence": _conf, "top": _top, "second": _second,
                                     "decision": "auto" if _auto else ("review" if _conf >= review_th else "blocked")},
                "scores": _rows, "warnings": ["human_override：人工指定优先；原始建议见 suggestedByMatch"],
                "thresholds": {"auto": auto_th, "review": review_th}}

    cached = _cache_get(h) if (use_cache and cfg.get("cacheEnabled", True)) else None
    if cached:
        out = dict(cached)
        out["cacheHit"] = True
        return out

    rows, warnings, mode_used = score_all(text, mode=mode, embed_model=embed_model, verbose=True)
    top, second, conf, tie = confidence_of(rows)
    light_order = spec.order()
    best = max(rows, key=lambda r: (r["score"], -light_order.index(r["paradigm"])
                                    if r["paradigm"] in light_order else 0))
    suggested = best["paradigm"]

    if top <= 0:
        decision = "blocked"
        warnings.append("no_signal：五个范式均无正向命中，禁止自动选择")
    elif conf >= auto_th and top >= 2 and second < top and not tie:
        # G6：单词命中或并列不得 auto（原 top=2/second=0 即 auto，实为单信号）
        decision = "auto"
    elif conf >= review_th:
        decision = "review"
    else:
        decision = "blocked"
    if tie:
        warnings.append("tie：最高分与次高分相同，confidence=0；按 matchOrder 仅作为建议项，仍需人工确认")

    out = {"inputHash": h, "mode": mode_used, "skip": skip, "override": False,
           "paradigm": suggested, "suggested": suggested,
           "confidence": conf, "decision": decision, "tie": tie, "cacheHit": False,
           "top": top, "second": second, "scores": rows, "warnings": warnings,
           "thresholds": {"auto": auto_th, "review": review_th}}
    if use_cache and cfg.get("cacheEnabled", True) and not warnings:
        _cache_put(h, {k: v for k, v in out.items() if k != "cacheHit"})
    return out
