"""sync_failed ↔ 宿主 deliverables 对账脚本（2026-11-04 双法合流审核 P1 修复项）。

背景（实测口径）：
  图层上报宿主失败时，callback._safe_sync 指数退避重试 3 次后仅往
  execution_trace 记 status=sync_failed 留痕，无补传队列——宿主侧因此
  "有痕无数据"。本脚本是该盲区的对账收口：扫 checkpoint 库找出全部
  sync_failed 痕迹，逐一对照宿主 deliverables 现状，产出待补传清单。

设计：
  - 直读 SQLite state_json 文本层（json.loads 后走 dict），不经 FlowState
    模型校验——物理存储里无论存的是 NodeExecution 还是 callback 兼容 shim
    均可解析，避免校验歧义漏报。
  - 宿主对照走 GET /api/instances/{thread_id}/deliverables（thread_id 即
    instance_id，integration.assign_thread_id 平迁契约）。宿主不可达时不静默：
    显式标 host_unreachable 并计入告警输出，退出码仍由 sync_failed 事实决定。
  - 只读：对 checkpoint 库仅 SELECT，对宿主仅 GET，零写操作。

退出码：
  0 = 无 sync_failed 待处理
  1 = 存在 sync_failed 痕迹（有待对账项，附明细）
  2 = 运行错误（库不存在/读取失败）

用法：
  python3 scripts/reconcile_sync_failed.py [--db <checkpoints.db>] [--json]
  env：HARNESS_API_BASE（默认 http://127.0.0.1:8001/api）、HARNESS_API_TOKEN
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urljoin

SYNC_FAILED_STATUS = "sync_failed"


def _iter_latest_states(db_path: str):
    """产出 (thread_id, state_dict)。直读 checkpoints 表最新快照的 state_json。"""
    import sqlite3

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT c.thread_id, c.state_json, c.create_ts
               FROM checkpoints c
               JOIN (
                   SELECT thread_id, MAX(create_ts) AS max_ts
                   FROM checkpoints GROUP BY thread_id
               ) latest ON c.thread_id = latest.thread_id AND c.create_ts = latest.max_ts"""
        ).fetchall()
        for r in rows:
            try:
                yield r["thread_id"], json.loads(r["state_json"])
            except json.JSONDecodeError as exc:
                print(f"[WARN] {r['thread_id']} state_json 解析失败，跳过: {exc}",
                      file=sys.stderr)
    finally:
        conn.close()


def _collect_sync_failed(db_path: str) -> list[dict]:
    """聚合全部 sync_failed 痕迹。兼容 status 字段缺失/非 dict 项。"""
    findings: list[dict] = []
    for thread_id, state in _iter_latest_states(db_path):
        trace = state.get("execution_trace") or []
        if not isinstance(trace, list):
            continue
        for idx, entry in enumerate(trace):
            if not isinstance(entry, dict):
                continue
            if entry.get("status") != SYNC_FAILED_STATUS:
                continue
            findings.append({
                "thread_id": thread_id,
                "trace_index": idx,
                "summary": str(entry.get("summary") or "")[:200],
                "error": str(entry.get("error") or "")[:200],
                "node": str((entry.get("node_type") or {}).get("value")
                            if isinstance(entry.get("node_type"), dict)
                            else entry.get("node_type") or ""),
            })
    return findings


def _fetch_host_deliverables(thread_id: str) -> dict:
    """查宿主该实例 deliverables 现状。失败显式返回 host_unreachable，不静默。"""
    base = os.environ.get("HARNESS_API_BASE", "http://127.0.0.1:8001/api").rstrip("/")
    token = os.environ.get("HARNESS_API_TOKEN", "")
    url = urljoin(base + "/", f"instances/{thread_id}/deliverables")
    try:
        import requests
    except ImportError:
        return {"host_unreachable": True, "reason": "requests 库不可用"}
    try:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        resp = requests.get(url, headers=headers, timeout=(3, 5))
        if not resp.ok:
            return {"host_unreachable": True,
                    "reason": f"HTTP {resp.status_code}: {resp.text[:120]}"}
        data = resp.json()
        items = data if isinstance(data, list) else data.get("deliverables") or []
        return {"host_unreachable": False, "count": len(items)}
    except Exception as exc:  # noqa: BLE001 — 对账工具不吞异常，转显式告警
        return {"host_unreachable": True, "reason": f"{type(exc).__name__}: {exc}"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="sync_failed ↔ 宿主 deliverables 对账")
    parser.add_argument("--db", default=None,
                        help="checkpoint 库路径（默认经 resolve_default_checkpoint_dir 解析）")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args(argv)

    if args.db:
        db_path = args.db
    else:
        try:
            from engine.flow.checkpoint import resolve_default_checkpoint_dir
            db_path = os.path.join(resolve_default_checkpoint_dir(), "checkpoints.db")
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] 解析默认 checkpoint 目录失败: {exc}", file=sys.stderr)
            return 2
    if not os.path.isfile(db_path):
        print(f"[ERROR] checkpoint 库不存在: {db_path}", file=sys.stderr)
        return 2

    findings = _collect_sync_failed(db_path)

    if not args.json:
        print(f"对账库: {db_path}")
        print(f"sync_failed 痕迹: {len(findings)} 条")
    for f in findings:
        host = _fetch_host_deliverables(f["thread_id"])
        f["host_deliverables"] = host
        if not args.json:
            flag = "宿主不可达!" if host.get("host_unreachable") else f"宿主现有 {host.get('count')} 条"
            print(f"  - [{f['thread_id']}] node={f['node']} idx={f['trace_index']} "
                  f"| {f['summary']} | {flag}")
            if f["error"]:
                print(f"      error: {f['error']}")

    if args.json:
        print(json.dumps({"db": db_path, "sync_failed_count": len(findings),
                          "findings": findings}, ensure_ascii=False, indent=1))
    else:
        if findings:
            print("结论: 存在待对账项——按上方明细核对宿主交付物后补传/重跑对应节点。")
        else:
            print("结论: 无 sync_failed 待处理，宿主侧与本地痕迹一致。")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
