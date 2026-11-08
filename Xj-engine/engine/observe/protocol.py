"""observe 上报协议 · **唯一机制层（引擎侧）**（2026-11-08 副本收口 + 机制上收）。

归属（用户 2026-11-08 裁定：一种机制，不散落）：
  声明 = 资产 `workflow.json` 的 `observe` 块（runtime / nodes / control）
  机制 = `engine/observe/`（本文件 + progress.py + control.py）
  适配 = backend 只做 HTTP+DB；宿主脚本只做"到边界叫一次"
客户端唯一实现仍是 `~/.agents/agent-observe/bin/observe_hook.py`（同一份枚举/规则）。

**禁止**：任何新增发射器直接拼 event dict 或直连 `/api/observe/nodes/runtime`。
新发射器必须先登记进 `~/.agents/agent-observe/channel_manifest.json`，并复用本模块
或 `observe_hook.emit_event()`。

权威定义见 `~/.agents/agent-observe/OFFICIAL_CHANNEL.md`。
"""
from __future__ import annotations

import hashlib
import os
import time

# 唯一合法事件枚举（与 engine/observe/contract_loader.py 的 EVENTS 逐字一致）
EVENTS = {"node_start", "node_end", "node_failed", "input_ready", "task_end"}

# 唯一交付物排除规则（原 observe_hook 有排除、engine_callback 无 → 两套口径）
ARTIFACT_EXCLUDE_PREFIXES = ("stage_cfg", ".")
ARTIFACT_EXCLUDE_SUFFIXES = (".report.json",)
ARTIFACT_GLOBS = ("*.md", "*.json", "*.txt", "*.yaml", "*.yml", "*.py")
TEXT_EXT = {".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".log", ".html", ".py"}


def dtype_of(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in {".json", ".yaml", ".yml"}:
        return "structured"
    return "text" if ext in TEXT_EXT else "binary"


def is_artifact_file(name: str) -> bool:
    """唯一排除口径：装配配置、报告文件、点文件不算业务交付物。"""
    if name.startswith(ARTIFACT_EXCLUDE_PREFIXES):
        return False
    if name.endswith(ARTIFACT_EXCLUDE_SUFFIXES):
        return False
    return True


def artifact_meta(path: str) -> dict | None:
    try:
        b = open(path, "rb").read()
    except OSError:
        return None
    if not b:
        return None
    dt = dtype_of(path)
    return {"storagePath": os.path.abspath(path), "deliverableType": dt,
            "sizeBytes": len(b), "sha256": hashlib.sha256(b).hexdigest(),
            "version": 1, "source": "agent", "replaceable": dt in ("text", "structured")}


def scan_artifacts(dir_path: str) -> list[dict]:
    """唯一目录扫描实现（排除规则见 is_artifact_file）。"""
    if not dir_path or not os.path.isdir(dir_path):
        return []
    import glob as _glob
    out = []
    for pat in ARTIFACT_GLOBS:
        for p in sorted(_glob.glob(os.path.join(dir_path, pat))):
            if not is_artifact_file(os.path.basename(p)):
                continue
            m = artifact_meta(p)
            if m:
                out.append(m)
    return out


def normalize_artifacts(items: list | None) -> list[dict]:
    """把发射器给的路径列表/元数据列表统一成协议格式，缺失文件显式标记。"""
    out = []
    for it in (items or []):
        if isinstance(it, dict):
            if it.get("storagePath"):
                out.append(it)
            continue
        m = artifact_meta(os.path.expanduser(str(it)))
        if m:
            out.append(m)
        else:
            # 文件缺失不得静默丢弃：带上 missing 标记，服务端据此可见
            out.append({"storagePath": os.path.abspath(os.path.expanduser(str(it))),
                        "deliverableType": "none", "sizeBytes": 0, "sha256": "",
                        "version": 1, "source": "agent", "replaceable": False,
                        "missing": True})
    return out


def build_event(*, task_id: str, asset_key: str, agent_id: str, node_id: str,
                event_type: str, seq: int, run_id: str = "", status: str | None = None,
                started_at: str | None = None, ended_at: str | None = None,
                duration_ms: int | None = None, error_code: str | None = None,
                artifacts: list | None = None, attempt: int = 1,
                event_id: str | None = None) -> dict:
    """唯一事件构造器。"""
    if event_type not in EVENTS:
        raise ValueError(f"eventType 非法：{event_type}")
    ev = {
        "eventId": event_id or hashlib.sha1(
            f"{task_id}|{agent_id}|{node_id}|{event_type}|{seq}".encode()).hexdigest(),
        "taskId": task_id, "runId": run_id or f"run_{task_id}",
        "assetKey": asset_key, "agentId": agent_id, "nodeId": node_id,
        "seq": int(seq), "eventType": event_type, "attempt": int(attempt),
    }
    if status:
        ev["status"] = status
    if started_at:
        ev["startedAt"] = started_at
    if ended_at:
        ev["endedAt"] = ended_at
    if duration_ms is not None:
        ev["durationMs"] = duration_ms
    if error_code:
        ev["errorCode"] = error_code
    arts = normalize_artifacts(artifacts)
    if arts:
        ev["artifacts"] = arts
    return ev


def validate_event(ev: dict) -> list[str]:
    errs = []
    for k in ("eventId", "taskId", "runId", "agentId", "nodeId", "seq", "eventType"):
        if ev.get(k) in (None, ""):
            errs.append(f"缺字段 {k}")
    if ev.get("eventType") not in EVENTS:
        errs.append(f"eventType 非法 {ev.get('eventType')!r}")
    return errs


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
