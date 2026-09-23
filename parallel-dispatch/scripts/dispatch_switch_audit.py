#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dispatch_switch_audit.py — dispatch_switch B/A 比率月度审计（接通「B/A 比率纳入复盘审计」宣言）。

输出：①全量与近30天 A/B/CLARIFY/VIOLATION 分布与 B/A 比率 ②冒烟测试批识别与剔除（同一时间戳秒级 ≥3 条）
③B 档注水嫌疑清单（dep_reason <10 字符或为空） ④ALERT 告警段（作战 B/A > 1.5 或存在 VIOLATION）。
默认 exit 0（审计工具）；--strict 时有 ALERT 则 exit 1。纯 stdlib。

用法：
  python3 dispatch_switch_audit.py            # 月度审计（默认读 ~/.agents/logs/dispatch_switch.jsonl）
  python3 dispatch_switch_audit.py --strict   # 有 ALERT 时 exit 1（供 cron/复盘门禁）
"""
import argparse
import collections
import datetime
import json
import sys
from pathlib import Path

DEFAULT_LOG = Path.home() / ".agents" / "logs" / "dispatch_switch.jsonl"
SMOKE_MIN = 3          # 同一时间戳秒级 ≥N 条视为冒烟测试批
WATERMARK_LEN = 10     # B 档 dep_reason 短于该长度视为注水嫌疑
BA_ALERT = 1.5         # 作战 B/A 比率告警阈值
RECENT_DAYS = 30
VERDICTS = ("A", "B", "CLARIFY", "VIOLATION")


def load_entries(path):
    entries = []
    for ln, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            print(f"  [WARN] 第 {ln} 行 JSON 解析失败，跳过", file=sys.stderr)
            continue
        try:
            e["_dt"] = datetime.datetime.fromisoformat(e.get("ts", ""))
        except ValueError:
            e["_dt"] = None
        entries.append(e)
    return entries


def dist(rows):
    c = collections.Counter(r.get("verdict") for r in rows)
    return {v: c.get(v, 0) for v in VERDICTS}


def ba_ratio(d):
    a, b = d["A"], d["B"]
    return None if a == 0 else b / a


def fmt_ratio(r):
    return "N/A（A=0）" if r is None else f"{r:.2f}"


def main():
    ap = argparse.ArgumentParser(description="dispatch_switch B/A 比率月度审计")
    ap.add_argument("--log", default=str(DEFAULT_LOG), help="留痕 jsonl 路径")
    ap.add_argument("--strict", action="store_true", help="有 ALERT 时 exit 1")
    args = ap.parse_args()

    path = Path(args.log).expanduser()
    if not path.exists():
        print(f"留痕文件不存在: {path}")
        sys.exit(0)

    entries = load_entries(path)
    now = datetime.datetime.now()
    if entries and all(e["_dt"] and e["_dt"] > now for e in entries):
        now = max(e["_dt"] for e in entries)  # 留痕时间晚于系统时钟时以留痕为准
    cutoff = now - datetime.timedelta(days=RECENT_DAYS)

    # ② 冒烟测试批识别：同一时间戳（秒级）≥SMOKE_MIN 条
    by_ts = collections.defaultdict(list)
    for e in entries:
        by_ts[e.get("ts")].append(e)
    smoke_ts = {ts for ts, rows in by_ts.items() if len(rows) >= SMOKE_MIN}
    smoke = [e for e in entries if e.get("ts") in smoke_ts]
    combat = [e for e in entries if e.get("ts") not in smoke_ts]
    recent = [e for e in combat if e["_dt"] and e["_dt"] >= cutoff]

    d_all, d_recent, d_smoke = dist(combat), dist(recent), dist(smoke)
    r_all, r_recent = ba_ratio(d_all), ba_ratio(d_recent)

    # ③ B 档注水嫌疑：dep_reason 为空或 <WATERMARK_LEN 字符
    # （单体任务自然串行免理由，不列入；只查多任务串行 / 人工强制串行）
    watered = []
    for e in combat:
        if e.get("verdict") != "B":
            continue
        inp = e.get("inputs") or {}
        n = inp.get("units") if inp.get("units") is not None else inp.get("files")
        natural = (n is None or n <= 1) and not e.get("force_serial")
        if natural:
            continue
        reason = (inp.get("dep_reason") or "").strip()
        if len(reason) < WATERMARK_LEN:
            watered.append((e.get("ts"), reason, inp.get("desc")))

    # ④ ALERT 判定
    alerts = []
    if r_all is not None and r_all > BA_ALERT:
        alerts.append(f"作战 B/A 比率 {r_all:.2f} > {BA_ALERT}（故意串行化倾向，须逐条复核 B 档理由）")
    if d_all["VIOLATION"] > 0:
        alerts.append(f"作战留痕存在 VIOLATION ×{d_all['VIOLATION']}（B 档无理由拒扳，门禁被硬闯）")

    print("━━ dispatch_switch B/A 比率月度审计 ━━━━━━━━━━━━━━━━━")
    print(f"留痕: {len(entries)} | 作战: {len(combat)} | 冒烟测试批: {len(smoke)}（{len(smoke_ts)} 批，已剔除） | 近{RECENT_DAYS}天作战: {len(recent)}")

    print(f"\n① 分布与 B/A 比率（作战口径，已剔除冒烟批）:")
    print(f"  全量:        A={d_all['A']} B={d_all['B']} CLARIFY={d_all['CLARIFY']} VIOLATION={d_all['VIOLATION']} | B/A={fmt_ratio(r_all)}")
    print(f"  近{RECENT_DAYS}天:     A={d_recent['A']} B={d_recent['B']} CLARIFY={d_recent['CLARIFY']} VIOLATION={d_recent['VIOLATION']} | B/A={fmt_ratio(r_recent)}")

    print(f"\n② 冒烟测试批（同秒 ≥{SMOKE_MIN} 条，单列不计入作战统计）: {'无' if not smoke_ts else ''}")
    for ts in sorted(smoke_ts):
        d = dist(by_ts[ts])
        print(f"  {ts}: {len(by_ts[ts])} 条（A={d['A']} B={d['B']} CLARIFY={d['CLARIFY']} VIOLATION={d['VIOLATION']}）")

    print(f"\n③ B 档注水嫌疑（dep_reason <{WATERMARK_LEN} 字符或为空）: {'无' if not watered else ''}")
    for ts, reason, desc in watered:
        print(f"  {ts}: reason={reason!r} desc={str(desc)[:40]!r}")

    print(f"\n④ ALERT: {'无' if not alerts else ''}")
    for a in alerts:
        print(f"  [ALERT] {a}")

    if alerts and args.strict:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
