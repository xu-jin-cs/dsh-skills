#!/usr/bin/env python3
# task_fanout_plan.py — 通用任务扇出判定计算件（2026-10-13 REFORM-GATE 判A · task_fanout_plan_20261013.md）
#
# 定位：独立于 task-breakdown 的通用调度判定层。任何入口（普通对话/PM 流程/手动）
#       新建任务（单个或多个）时，先过本脚本拿"母 agent 执行拓扑"。
# 两件判定：
#   ① 任务间并行性（多任务时）：deps → Kahn 分层（复用 dag_layer 同目录函数）
#   ② 逐任务可拆性：size==S → atomic（单子 agent 直接执行）；
#                   size∈{M,L,XL} → needs_breakdown（母 agent 先拆子任务，
#                   子任务清单回来后【递归再调本脚本】直到全部 atomic）
# 本件只判定不执行：真并行 spawn 由母 Agent（Agent 工具）或 node_executor 完成；
#                   并行安全性由 dispatch_switch 闸复核（units=本件输出 width）。
# 用法：python3 task_fanout_plan.py --tasks <JSON文件路径 或 内联JSON串>
# 出参 verdict：A=拓扑产出；B=标注违例（漏标/悬空/成环/缺size/no_dep_reason），violations 即修复指令。
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dag_layer import load_tasks, validate_structure, kahn_layers  # 复用分层件，口径唯一

BREAKDOWN_SIZES = {"M", "L", "XL"}   # 非 S 即需拆解


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True, help="任务清单 JSON 路径或内联串")
    args = ap.parse_args()
    try:
        data = load_tasks(args.tasks)
    except json.JSONDecodeError as e:
        print(json.dumps({"verdict": "B", "violations": [f"JSON 解析失败: {e}"]}, ensure_ascii=False))
        return 2

    tasks, violations = validate_structure(data)
    # 本件额外要求：size 必填（可拆性判定依据）
    for t in tasks:
        if not t.get("size"):
            violations.append(f"{t.get('id')}: size 字段缺失——可拆性判定需要 S/M/L/XL 标注")
    if violations:
        print(json.dumps({"verdict": "B", "violations": violations}, ensure_ascii=False))
        return 2
    layers, cyc = kahn_layers(tasks)
    if cyc:
        print(json.dumps({"verdict": "B", "violations": cyc}, ensure_ascii=False))
        return 2

    per_task = {}
    for t in tasks:
        if t["size"] == "S":
            per_task[t["id"]] = {"mode": "atomic"}
        else:
            per_task[t["id"]] = {"mode": "needs_breakdown",
                                 "reason": f"size={t['size']}（非 S），母 agent 先拆子任务，"
                                           f"子任务清单递归再调本脚本直到全部 atomic"}

    waves = []
    for i, layer in enumerate(layers, 1):
        waves.append({
            "wave": i,
            "parallel_sub_agents": layer,
            "width": len(layer),
            "modes": {tid: per_task[tid]["mode"] for tid in layer},
        })
    width = max(len(l) for l in layers)
    plan = {
        "task_layers": layers,
        "per_task": per_task,
        "spawn_topology": {
            "mother_agent": "主 Agent（母）",
            "waves": waves,
            "rule": "wave 内并行 spawn 子 agent；wave 间按依赖就绪串行推进；"
                    "needs_breakdown 任务先拆解再递归判定",
        },
        "dispatch_hint": {
            "units": width,
            "cmd": f"python3 ~/.agents/skills/parallel-dispatch/scripts/dispatch_switch.py "
                   f"--units {width} --desc \"<任务摘要>\"",
            "note": "width>1 时派发前必须扳并行闸复核安全性；width==1 全串行免扳",
        },
    }
    print(json.dumps({"verdict": "A", "fanout_plan": plan, "violations": []}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
