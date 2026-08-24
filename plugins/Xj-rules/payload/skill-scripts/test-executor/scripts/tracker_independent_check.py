#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tracker_independent_check.py — test-executor 执行追踪器独立证据源校验（2026-08-17 块3）

治「执行追踪器自报自验」结构性盲点：
  tracker 的 browser_launch_count / executed_cases 由 executor 自己写自己查，
  sv 监督读的也是同一份自报数据 → 漏记/误记即违规隐身。
本脚本只从独立证据源（audit.log / manifest.json，执行产物，非 tracker 自报文件）取证，
完成三项机械校验：
  ① 浏览器启动事件计数 ≤ max（默认 1，超出=多浏览器并行违例，对应规则1）
  ② case_id 集合无重复执行（重复=规则2 违例）
  ③ 独立计数与 tracker 自报值交叉比对（不一致=tracker 漏记/误记违例）

退出码：0=全过 / 2=违例（清单逐条打印，末行为汇总，供 gate-switch script_exit 截尾）。

用法：
  python3 tracker_independent_check.py --evidence <证据目录> [--tracker <tracker.json>]
    [--audit <audit.log 路径>] [--manifest <manifest.json 路径>]
    [--max-browser-launch 1]
  默认 audit=<evidence>/audit.log，manifest=<evidence>/manifest.json。
  --tracker 缺省时跳过交叉比对（只做 ①② 独立判据）。
"""
import argparse
import json
import os
import re
import sys

# 浏览器启动事件行特征（audit.log 逐行 grep，大小写不敏感）
BROWSER_LAUNCH_PATTERNS = [
    r"browser[_\s\-]?launch",
    r"launch[_\s\-]?browser",
    r"launch_browser",
    r"browser[_\s\-]?start(?:ed)?",
    r"new[_\s\-]?browser",
    r"browser[_\s\-]?open(?:ed)?",
]
BROWSER_LAUNCH_RE = re.compile("|".join(BROWSER_LAUNCH_PATTERNS), re.IGNORECASE)

# audit.log 中 case_id 提取（兼容 JSON 行与 "case_id: xxx" / "case TC-xxx" 文本行）
CASE_ID_RES = [
    re.compile(r'"case_id"\s*:\s*"([^"]+)"'),
    re.compile(r"\bcase[_\- ]?id\b[\"'\s:=]+([A-Za-z0-9_\-]+)", re.IGNORECASE),
    re.compile(r"\b(?:executing|execute|start|run|finished|done)\s+case\s+([A-Za-z0-9_\-]+)", re.IGNORECASE),
]


def _collect_case_ids_from_json(obj, out):
    """递归收集 JSON 结构中所有键名为 case_id 的值。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "case_id" and isinstance(v, (str, int)):
                out.append(str(v))
            else:
                _collect_case_ids_from_json(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _collect_case_ids_from_json(item, out)


def count_browser_launches(audit_path):
    """从 audit.log 独立 grep 浏览器启动事件行数。文件不存在返回 None。"""
    if not os.path.isfile(audit_path):
        return None
    count = 0
    with open(audit_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if BROWSER_LAUNCH_RE.search(line):
                count += 1
    return count


def collect_executed_case_ids(audit_path, manifest_path):
    """从 manifest.json 与 audit.log 独立收集已执行 case_id。
    返回 (per_source: {源名: [case_id...]}, union: 全集)。
    重复判定按源内计数（同一 case 同时出现在 manifest 与 audit.log 是正常双记录，不算重复执行）。
    """
    per_source = {}
    if manifest_path and os.path.isfile(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as f:
                data = json.load(f)
            ids = []
            _collect_case_ids_from_json(data, ids)
            if ids:
                per_source["manifest.json"] = ids
        except Exception:
            pass  # manifest 非 JSON/解析失败：落 audit.log 兜底
    if audit_path and os.path.isfile(audit_path):
        ids = []
        with open(audit_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                for rx in CASE_ID_RES:
                    for m in rx.finditer(line):
                        ids.append(m.group(1))
        if ids:
            per_source["audit.log"] = ids
    union = set()
    for ids in per_source.values():
        union.update(ids)
    return per_source, union


def find_dups(ids):
    seen, dups = set(), set()
    for cid in ids:
        if cid in seen:
            dups.add(cid)
        seen.add(cid)
    return sorted(dups)


def main():
    ap = argparse.ArgumentParser(description="test-executor 追踪器独立证据源校验")
    ap.add_argument("--evidence", required=True, help="证据目录（audit.log/manifest.json 所在）")
    ap.add_argument("--audit", default=None, help="audit.log 路径（默认 <evidence>/audit.log）")
    ap.add_argument("--manifest", default=None, help="manifest.json 路径（默认 <evidence>/manifest.json）")
    ap.add_argument("--tracker", default=None, help="tracker 自报文件（可选，提供则交叉比对）")
    ap.add_argument("--max-browser-launch", type=int, default=1, help="浏览器启动事件上限（默认 1）")
    args = ap.parse_args()

    audit_path = args.audit or os.path.join(args.evidence, "audit.log")
    manifest_path = args.manifest or os.path.join(args.evidence, "manifest.json")

    violations = []

    # 证据产物存在性（缺失=独立证据源断链，属违例）
    audit_exists = os.path.isfile(audit_path)
    manifest_exists = os.path.isfile(manifest_path)
    if not audit_exists:
        violations.append(f"E0-AUDIT-MISSING: 独立证据源 audit.log 缺失（{audit_path}）")
    if not manifest_exists:
        violations.append(f"E0-MANIFEST-MISSING: 独立证据源 manifest.json 缺失（{manifest_path}）")

    # ① 浏览器启动事件计数 ≤ max（独立判据，不读 tracker）
    launch_count = count_browser_launches(audit_path)
    if launch_count is not None and launch_count > args.max_browser_launch:
        violations.append(
            f"E1-BROWSER-PARALLEL: audit.log 独立计数 browser_launch={launch_count} "
            f"> 上限 {args.max_browser_launch}（规则1 多浏览器并行违例）"
        )

    # ② case_id 集合无重复执行（独立判据，按源内重复计数）
    per_source, case_union = collect_executed_case_ids(audit_path, manifest_path)
    for src, ids in per_source.items():
        dups = find_dups(ids)
        if dups:
            violations.append(
                f"E2-DUP-CASE: 独立证据源 {src} 源内发现重复执行 case_id: {dups}（规则2 违例）"
            )

    # ③ 独立计数与 tracker 自报值交叉比对（提供 --tracker 时）
    if args.tracker:
        if not os.path.isfile(args.tracker):
            violations.append(f"E3-TRACKER-MISSING: tracker 自报文件缺失（{args.tracker}）")
        else:
            try:
                with open(args.tracker, encoding="utf-8") as f:
                    tracker = json.load(f)
            except Exception as e:
                violations.append(f"E3-TRACKER-PARSE: tracker 自报文件解析失败（{args.tracker}）: {e}")
                tracker = None
            if tracker is not None:
                # 3a 浏览器计数交叉比对
                if launch_count is not None:
                    claimed = tracker.get("browser_launch_count")
                    if claimed is None:
                        violations.append("E3-TRACKER-NOLAUNCH: tracker 自报缺 browser_launch_count 字段")
                    elif claimed != launch_count:
                        violations.append(
                            f"E3-TRACKER-LAUNCH-DIFF: 独立计数 browser_launch={launch_count} "
                            f"≠ tracker 自报 {claimed}（tracker 漏记/误记违例）"
                        )
                # 3b case_id 集合交叉比对（独立证据源并集 vs tracker 记录集）
                tracker_cases = [str(c.get("case_id", c)) if isinstance(c, dict) else str(c)
                                 for c in tracker.get("executed_cases", [])]
                tracker_set = set(tracker_cases)
                missing_in_tracker = case_union - tracker_set
                extra_in_tracker = tracker_set - case_union
                if missing_in_tracker:
                    violations.append(
                        f"E3-TRACKER-CASE-UNDER: 独立证据源已执行但 tracker 未记录: {sorted(missing_in_tracker)}（tracker 漏记）"
                    )
                if extra_in_tracker:
                    violations.append(
                        f"E3-TRACKER-CASE-OVER: tracker 记录但独立证据源无执行痕迹: {sorted(extra_in_tracker)}（tracker 误记）"
                    )

    if violations:
        for v in violations:
            print(f"VIOLATION: {v}")
        print(f"violations={len(violations)}: " + " | ".join(v.split(":", 1)[0] for v in violations))
        sys.exit(2)

    launch_desc = f"browser_launch={launch_count}" if launch_count is not None else "browser_launch=N/A(audit缺失)"
    cross = "交叉比对通过" if args.tracker else "未提供tracker(跳过交叉比对)"
    src_desc = "+".join(per_source.keys()) or "无"
    total_ids = sum(len(v) for v in per_source.values())
    print(f"PASS: 独立证据源校验全过（{launch_desc} ≤ {args.max_browser_launch}; "
          f"case_id 源内无重复({total_ids}条,来源:{src_desc}); {cross}）")
    sys.exit(0)


if __name__ == "__main__":
    main()
