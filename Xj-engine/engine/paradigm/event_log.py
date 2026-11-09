"""结构化日志：选型链路每一步一条 JSONL（原文脱敏可选、打分表、选中、置信、校验、人工标记）。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from . import spec

LOG_FILE = spec.LOG_DIR / "paradigm_selection.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit(stage: str, **fields) -> dict:
    """stage ∈ input | match | decide | gate | override | escape。返回写入的行。"""
    row = {"id": f"pse_{uuid.uuid4().hex[:12]}", "ts": _now(), "stage": stage,
           "paradigmVersion": spec.paradigm_version()}
    row.update(fields)
    try:
        spec.LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return row
