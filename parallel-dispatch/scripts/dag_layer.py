#!/usr/bin/env python3
# dag_layer.py — 并行层机械分层计算件（parallel_layer_gate 计算件，非闸本体）
# 依据：problem_gate 判A（parallel_layer_problem_20261013.md）+ REFORM-GATE 判A（parallel_layer_reform_20261013.md）
#
# 职责：task-breakdown 拆解 JSON（tasks+deps）→ Kahn 拓扑分层 → parallel_plan。
# 治病：「本可并行漏标」——并行计划由算法产出，不再靠 LLM 自觉标记。
# 漏标拦截铁律：deps 字段缺失（键不存在）= 漏标 → reject；
#              deps: []（显式空数组）= 确认无依赖 → 放行进入第 0 层。
# 用法：python3 dag_layer.py --tasks <拆解JSON文件路径 或 内联JSON串>
# 出参 verdict：A=分层成功；B=漏标/悬空/成环/自引用/id重复，violations 即修复指令。
import json
import sys


def load_tasks(raw: str) -> dict:
    """入参为文件路径或内联 JSON 串。"""
    try:
        with open(raw, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, UnicodeDecodeError):
        return json.loads(raw)


def validate_structure(data: dict) -> tuple[list, list]:
    """结构校验：返回 (tasks, violations)。口径与 task_breakdown.json 闸一致并追加漏标拦截。"""
    violations = []
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return [], ["tasks 字段缺失或为空数组"]
    seen = set()
    for t in tasks:
        tid = t.get("id")
        if not tid:
            violations.append("存在缺 id 的任务")
            continue
        if tid in seen:
            violations.append(f"id 重复: {tid}")
        seen.add(tid)
        if "deps" not in t:
            # 漏标拦截：键缺失 ≠ 显式无依赖。显式空数组 [] 才是合法的无依赖声明。
            violations.append(f"{tid}: deps 字段缺失（漏标）——无依赖须显式写 deps: [] 并填 no_dep_reason")
        elif t["deps"] == [] and not t.get("no_dep_reason"):
            violations.append(f"{tid}: 声明无依赖但未填 no_dep_reason（为什么不需要上游任何产物）")
        elif not isinstance(t.get("deps"), list):
            violations.append(f"{tid}: deps 必须是数组")
    ids = {t.get("id") for t in tasks if t.get("id")}
    for t in tasks:
        for d in t.get("deps") or []:
            if d not in ids:
                violations.append(f"{t.get('id')}: deps 悬空引用 {d}")
            if d == t.get("id"):
                violations.append(f"{t.get('id')}: 自引用")
    return tasks, violations


def kahn_layers(tasks: list) -> tuple[list, list]:
    """Kahn 拓扑分层。返回 (layers, violations)；成环时 violations 非空。"""
    deps = {t["id"]: list(t.get("deps") or []) for t in tasks}
    indeg = {tid: len(ds) for tid, ds in deps.items()}
    # 反向邻接：被谁依赖
    rdep = {tid: [] for tid in deps}
    for tid, ds in deps.items():
        for d in ds:
            rdep[d].append(tid)
    layers = []
    ready = sorted([tid for tid, dg in indeg.items() if dg == 0])
    done = set()
    while ready:
        layers.append(ready)
        nxt = []
        for tid in ready:
            done.add(tid)
            for m in rdep[tid]:
                indeg[m] -= 1
                if indeg[m] == 0:
                    nxt.append(m)
        ready = sorted(nxt)
    if len(done) != len(deps):
        leftover = sorted(set(deps) - done)
        return layers, [f"deps 成环，剩余任务无法分层: {leftover}"]
    return layers, []


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True, help="拆解 JSON 文件路径或内联 JSON 串")
    args = ap.parse_args()
    try:
        data = load_tasks(args.tasks)
    except json.JSONDecodeError as e:
        print(json.dumps({"verdict": "B", "violations": [f"JSON 解析失败: {e}"]}, ensure_ascii=False))
        return 2

    tasks, violations = validate_structure(data)
    if violations:
        print(json.dumps({"verdict": "B", "violations": violations}, ensure_ascii=False))
        return 2
    layers, cyc = kahn_layers(tasks)
    if cyc:
        print(json.dumps({"verdict": "B", "violations": cyc}, ensure_ascii=False))
        return 2

    width = max(len(l) for l in layers)
    plan = {
        "layers": layers,
        "parallel_width": width,
        "layer_count": len(layers),
        "rule": "层内并行、层间串行；parallel_width 喂 dispatch_switch --units",
    }
    print(json.dumps({"verdict": "A", "parallel_plan": plan,
                      "violations": []}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
