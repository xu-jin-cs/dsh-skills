#!/usr/bin/env python3
# task_fanout_plan.py — 任务扇出分流器（2026-10-13 用户终裁版）
#
# 定位：分流器，不是闸。任何任务清单进来，必然输出执行拓扑——
#   要么并行、要么串行，附加每个任务能否分解的标注。
#   必定有下文：不存在阻塞、打回、判A/判B。
# 判定逻辑（极简）：
#   分解：逐任务独立——size=M/L/XL 可分解（decomposable）；size=S 或缺失 → atomic 不拆。
#         混合合法，不要求全部可分解。
#   并行：仅多任务前提触发——任务数≥2 才判依赖；无依赖同 wave 并行，
#         有依赖 wave 间串行、wave 内并行。单任务无并行概念。
# 缺省规则（保守，notes 提示补标注可解锁）：
#   deps 缺失 → 该任务独立成 wave（保守串行），notes 提示声明 deps:[] 可并行；
#   size 缺失 → atomic；deps 成环 → 环内任务按 id 序串行收尾。
# 用法：python3 task_fanout_plan.py --tasks <JSON文件路径 或 内联JSON串>
# 出参：{"execution_plan": {...}}，恒 exit 0。
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dag_layer import load_tasks  # 仅复用入参加载

BREAKDOWN_SIZES = {"M", "L", "XL"}


def split_waves(tasks: list) -> tuple[list, list]:
    """Kahn 分层变体：永不出错。返回 (waves, notes)。
    deps 缺失的任务保守独立成 wave；成环残余按 id 序串行追加。"""
    notes = []
    declared = {}   # 显式声明 deps 的任务
    solo = []       # deps 缺失 → 保守独立 wave
    for t in tasks:
        tid = t.get("id") or "?"
        if "deps" not in t:
            solo.append(tid)
            notes.append(f"{tid}: 未声明 deps，保守串行（显式写 deps:[] 可解锁并行）")
        else:
            declared[tid] = [d for d in (t.get("deps") or []) if d in
                             {x.get("id") for x in tasks}]  # 悬空引用静默剔除并提示
            missing = [d for d in (t.get("deps") or []) if d not in {x.get("id") for x in tasks}]
            for m in missing:
                notes.append(f"{tid}: deps 引用了不存在的 {m}，已忽略该依赖")
    # Kahn 分层（仅对显式声明 deps 的任务）
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
        notes.append(f"依赖成环 {leftover}：环内任务按序串行，建议拆解后重新声明依赖")
        for tid in leftover:
            waves.append([tid])
    for tid in solo:
        waves.append([tid])
    return waves, notes


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True, help="任务清单 JSON 路径或内联串")
    args = ap.parse_args()
    try:
        data = load_tasks(args.tasks)
    except (json.JSONDecodeError, OSError) as e:
        # 输入都解析不了时也给出下文：无法分流，按串行原样执行
        print(json.dumps({"execution_plan": {
            "mode": "serial",
            "waves": [],
            "breakdown": {},
            "notes": [f"输入解析失败（{e}），按串行原样执行"],
        }}, ensure_ascii=False))
        return 0

    tasks = data.get("tasks") if isinstance(data, dict) else data
    if not isinstance(tasks, list) or not tasks:
        print(json.dumps({"execution_plan": {
            "mode": "serial", "waves": [], "breakdown": {},
            "notes": ["任务清单为空或非法，按串行原样执行"]}}, ensure_ascii=False))
        return 0

    waves, notes = split_waves(tasks)

    # 分解判定：逐任务独立
    breakdown = {}
    for t in tasks:
        tid = t.get("id") or "?"
        size = t.get("size")
        if size in BREAKDOWN_SIZES:
            breakdown[tid] = "decomposable"
        else:
            breakdown[tid] = "atomic"
            if not size:
                notes.append(f"{tid}: 未标 size，按不可分解处理（标 M/L/XL 可解锁拆解）")

    multi = len(tasks) >= 2
    width = max((len(w) for w in waves), default=1)
    plan = {
        "mode": "parallel" if (multi and width > 1) else "serial",
        "waves": [{"wave": i + 1, "tasks": w, "parallel": len(w) > 1}
                  for i, w in enumerate(waves)],
        "breakdown": breakdown,
        "parallel_width": width if multi else 1,
        "notes": notes,
        "rule": "wave 内并行 spawn 子 agent、wave 间串行；decomposable 任务到点先拆子任务再执行；"
                "并行安全性由 dispatch_switch --units <width> 复核（width>1 时）",
    }
    print(json.dumps({"execution_plan": plan}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
