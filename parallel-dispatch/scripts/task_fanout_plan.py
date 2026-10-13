#!/usr/bin/env python3
# task_fanout_plan.py — 任务扇出分流器（2026-10-13 v2 P0 重构判A · fanout_p0_rebuild_20261013.md）
#
# 定位：分流器。任务清单进来，必然输出执行拓扑——要么并行要么串行，附加分解标注。
#   必定有下文：无阻塞、无打回、无 verdict、无门槛。
# 判定逻辑（极简）：
#   分解：逐任务独立——size=M/L/XL 可分解；S 或缺省 → 不拆。混合合法。
#   并行：仅任务数≥2 触发——无依赖同 wave 并行；有依赖 wave 间串行。
# 缺省规则（2026-10-13 用户裁定"没那么复杂"）：deps 缺省=无依赖（可并行）；
#   size 缺省=不拆。静默处理不轰炸；仅成环/悬空/非法输入给异常级 notes。
# 用法：python3 task_fanout_plan.py --tasks <JSON文件路径 或 内联JSON串>，恒 exit 0。
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dag_layer import load_tasks  # 入参加载复用

BREAKDOWN_SIZES = {"M", "L", "XL"}


def split_waves(tasks: list) -> tuple[list, list]:
    """Kahn 分层变体：永不出错。deps 缺省=无依赖；成环/悬空仅 notes 提示。"""
    notes = []
    ids = {t.get("id") for t in tasks}
    declared = {}
    for t in tasks:
        tid = t.get("id") or "?"
        raw_deps = t.get("deps") or []
        dangling = [d for d in raw_deps if d not in ids]
        for m in dangling:
            notes.append(f"{tid}: deps 引用了不存在的 {m}，已忽略")
        declared[tid] = [d for d in raw_deps if d in ids]
    indeg = {tid: len(ds) for tid, ds in declared.items()}
    rdep = {tid: [] for tid in declared}
    for tid, ds in declared.items():
        for d in ds:
            rdep[d].append(tid)
    waves = []
    ready = sorted([t for t, dg in indeg.items() if dg == 0])
    done = set()
    while ready:
        waves.append(ready)
        nxt = []
        for tid in ready:
            done.add(tid)
            for m in rdep[tid]:
                indeg[m] -= 1
                if indeg[m] == 0:
                    nxt.append(m)
        ready = sorted(nxt)
    leftover = sorted(set(declared) - done)
    if leftover:
        notes.append(f"依赖成环 {leftover}：环内任务按序串行")
        for tid in leftover:
            waves.append([tid])
    return waves, notes


def make_plan(tasks: list) -> dict:
    """分流判定本体（闸内调用口）：tasks=[{id,size?,deps?}] → execution_plan。恒有输出。"""
    waves, notes = split_waves(tasks)
    breakdown = {t.get("id") or "?":
                 ("decomposable" if t.get("size") in BREAKDOWN_SIZES else "atomic")
                 for t in tasks}
    multi = len(tasks) >= 2
    width = max((len(w) for w in waves), default=1)
    return {
        "mode": "parallel" if (multi and width > 1) else "serial",
        "waves": [{"wave": i + 1, "tasks": w, "parallel": len(w) > 1}
                  for i, w in enumerate(waves)],
        "breakdown": breakdown,
        "parallel_width": width if multi else 1,
        "notes": notes,
        "rule": "分流结论即终局许可（2026-10-13 用户终裁·关卡合并）：符合并行直接并行扇出、符合分解直接分解，无需再扳并行闸；并行=任务独立谁完谁销，分解=母合并子事项后销；wave 内并行·wave 间串行。仅 width>5 或显式耦合才扳 dispatch_switch 复核（重型场景）",
    }


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True, help="任务清单 JSON 路径或内联串")
    args = ap.parse_args()
    try:
        data = load_tasks(args.tasks)
        tasks = data.get("tasks") if isinstance(data, dict) else data
        if not isinstance(tasks, list) or not tasks:
            raise ValueError("任务清单为空或非法")
        plan = make_plan(tasks)
    except Exception as e:
        plan = {"mode": "serial", "waves": [], "breakdown": {}, "parallel_width": 1,
                "notes": [f"输入解析失败（{e}），按串行原样执行"],
                "rule": "分流结论即终局许可（2026-10-13 用户终裁·关卡合并）：符合并行直接并行扇出、符合分解直接分解，无需再扳并行闸；并行=任务独立谁完谁销，分解=母合并子事项后销；wave 内并行·wave 间串行。仅 width>5 或显式耦合才扳 dispatch_switch 复核（重型场景）"}
    print(json.dumps({"execution_plan": plan}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
