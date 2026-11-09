"""范式层规格加载（唯一真源：~/.agents/agent-paradigms/paradigms.json）。

引擎为唯一载体：打分/置信/三门/缓存/回流/逃逸全部在此包内，agent 侧只做薄转发。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

PARADIGM_FILE = Path.home() / ".agents" / "agent-paradigms" / "paradigms.json"
SCHEMA_FILE = Path.home() / ".agents" / "agent-paradigms" / "schema" / "agent_paradigm.schema.json"
STATE_DIR = Path.home() / ".agents" / "agent-paradigms" / "state"
LOG_DIR = Path.home() / ".agents" / "logs"

# 轻 → 重（同分取更靠前者）。**派生视图**：真源是 paradigms.json.matchOrder（重→轻）；
# 本常量仅作 paradigms.json 不可读时兜底，禁止单独改它（2026-11-10 F-14 收口）。
ORDER = ("single_tool_call", "react", "plan_execute", "reflexion", "multi_agent")

DATA: dict | None = None


def order() -> tuple[str, ...]:
    """判定顺序唯一入口：从 paradigms.json.matchOrder 反推（重→轻 ⇒ 轻→重）。"""
    mo = load().get("matchOrder") or None
    if isinstance(mo, list) and mo:
        return tuple(reversed(mo))
    return ORDER


def load(force: bool = False) -> dict:
    global DATA
    if DATA is None or force:
        if not PARADIGM_FILE.is_file():
            raise FileNotFoundError(f"范式层未安装：{PARADIGM_FILE}")
        DATA = json.loads(PARADIGM_FILE.read_text(encoding="utf-8"))
    return DATA


def paradigm_version() -> str:
    d = load()
    return str(d.get("paradigmVersion") or d.get("schemaVersion") or "")


def matcher_cfg() -> dict:
    return load().get("matcher") or {}


def thresholds() -> tuple[float, float]:
    cfg = matcher_cfg()
    return (float(cfg.get("autoThreshold", 0.6)), float(cfg.get("reviewThreshold", 0.3)))


def bounds_cfg() -> dict:
    return load().get("bounds") or {}


def match_mode() -> str:
    """lexical（默认，零依赖）/ semantic（需本地嵌入模型，禁止联网下载）。"""
    return os.environ.get("PARADIGM_MATCH_MODE", matcher_cfg().get("mode", "lexical")).lower()


def skip_selector() -> bool:
    """skip_paradigm_selector 开关：默认关闭；开启才允许跳过整套选型。"""
    v = os.environ.get("PARADIGM_SKIP_SELECTOR", "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def signals(paradigm: dict) -> dict:
    s = paradigm.get("matchSignals") or {}
    return {"strong": list(s.get("strong") or []),
            "weak": list(s.get("weak") or []),
            "negative": list(s.get("negative") or [])}


def paradigms() -> list[dict]:
    return list(load().get("paradigms") or [])


def by_id(pid: str) -> dict | None:
    return next((p for p in paradigms() if p.get("id") == pid), None)


def schema() -> dict:
    return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
