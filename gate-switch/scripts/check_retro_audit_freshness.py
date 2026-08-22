#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_retro_audit_freshness.py — retro 命中审计新鲜度闸（3 天周期，系统级调度被拒后的体系内替代）。
retro_match_trend.jsonl 末行时间戳距今 ≤3 天 → exit 0（A）；超期/缺失 → exit 2（B）。
挂接：复盘着陆前与 AGENTS.md 触发清单（会话开始时人工可扳）。
"""
import json
import os
import sys
from datetime import datetime, timedelta

TREND = os.path.expanduser("~/.agents/logs/retro_match_trend.jsonl")
MAX_AGE = timedelta(days=3)

try:
    lines = [l for l in open(TREND, encoding="utf-8") if l.strip()]
    last = json.loads(lines[-1])
    ts = datetime.fromisoformat(last["ts"])
    age = datetime.now() - ts
    if age <= MAX_AGE:
        print(f"RETRO_AUDIT_FRESHNESS: PASS last={last['ts']} age={age.days}d")
        sys.exit(0)
    print(f"RETRO_AUDIT_FRESHNESS: FAIL last={last['ts']} age={age.days}d > 3d → 先跑 periodic_match_audit.sh")
    sys.exit(2)
except Exception as e:
    print(f"RETRO_AUDIT_FRESHNESS: FAIL 无法读取趋势日志（{e}）→ 先跑 periodic_match_audit.sh")
    sys.exit(2)
