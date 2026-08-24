#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
breakdown_check.py — task-breakdown 输出 JSON 的 schema 完整性与 deps 引用闭环机械校验器（W7）

背景（2026-08-15 裁定，gate-switch 机械门禁）：task-breakdown 交付前必须机械核验，
漏字段 / deps 悬空引用 / deps 成环会直接传染下游并行调度，判 B 打回修复。

校验项：
  1. 八字段齐全且非空：id/module/description/size/estimate/acceptance/deps/tech_stack
  2. size ∈ {S, M, L, XL}
  3. deps 为数组（缺失按 check=missing_field，非数组按 check=deps_type）
  4. deps 引用的 id 在任务集合内真实存在（引用闭环，check=dangling_dep）
  5. deps 无自引用（check=self_dep）
  6. deps 无环（DFS 检测，check=cycle，detail 列出环路径）
  7. id 全局唯一（check=duplicate_id）

用法：
  python3 breakdown_check.py --tasks <任务拆解JSON路径>
  输入自适应：顶层为任务数组，或含 "tasks" 键的对象。

输出 JSON：{pass, total_tasks, violations[{task_id, check, detail}]}
退出码：0 = 全部通过；1 = 存在违例或输入无法解析。
"""
import argparse
import json
import sys

REQUIRED_FIELDS = ["id", "module", "description", "size", "estimate",
                   "acceptance", "deps", "tech_stack"]
VALID_SIZES = {"S", "M", "L", "XL"}


def is_nonempty(v):
    """字段非空判定：None/空串/空数组/空对象 视为空。"""
    if v is None:
        return False
    if isinstance(v, str) and not v.strip():
        return False
    if isinstance(v, (list, dict)) and not v:
        return False
    return True


def render(violations, total, ok):
    # 单行紧凑 JSON：gate_switch.py 的 script_exit 只截取输出末行，单行可让违例详情完整进入门禁 violations
    return json.dumps({"pass": ok, "total_tasks": total, "violations": violations},
                      ensure_ascii=False, separators=(",", ":"))


def fail(violations, total, msg, code=1):
    print(render(violations, total, False))
    if msg:
        print(msg, file=sys.stderr)
    sys.exit(code)


def main():
    ap = argparse.ArgumentParser(description="task-breakdown 输出机械校验（schema + deps 闭环）")
    ap.add_argument("--tasks", required=True, help="任务拆解 JSON 路径（数组或含 tasks 键的对象）")
    args = ap.parse_args()

    violations = []

    # --- 输入解析（自适应：数组 或 {tasks: [...]}） ---
    try:
        with open(args.tasks, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        fail([], 0, "无法读取/解析 JSON: %s: %s" % (args.tasks, e))

    if isinstance(data, dict):
        tasks = data.get("tasks")
        if tasks is None:
            fail([], 0, "对象输入缺少 tasks 键: %s" % args.tasks)
    elif isinstance(data, list):
        tasks = data
    else:
        fail([], 0, "顶层必须为数组或含 tasks 键的对象: %s" % args.tasks)

    if not isinstance(tasks, list):
        fail([], 0, "tasks 必须为数组: %s" % args.tasks)

    total = len(tasks)

    # --- 逐任务 schema 校验 + 收集 id ---
    id_list = []
    for idx, t in enumerate(tasks):
        tid = t.get("id") if isinstance(t, dict) else None
        label = tid if is_nonempty(tid) else "#%d" % idx
        if not isinstance(t, dict):
            violations.append({"task_id": label, "check": "task_type",
                               "detail": "任务条目必须为对象: %r" % (t,)})
            continue
        for field in REQUIRED_FIELDS:
            if field not in t:
                violations.append({"task_id": label, "check": "missing_field",
                                   "detail": "缺少字段 %s" % field})
            elif field == "deps":
                if not isinstance(t["deps"], list):
                    violations.append({"task_id": label, "check": "deps_type",
                                       "detail": "deps 必须为数组，实际: %s" % type(t["deps"]).__name__})
            elif not is_nonempty(t[field]):
                violations.append({"task_id": label, "check": "empty_field",
                                   "detail": "字段 %s 为空" % field})
        if "size" in t and t["size"] not in VALID_SIZES:
            violations.append({"task_id": label, "check": "invalid_size",
                               "detail": "size=%r 不在 %s" % (t.get("size"), sorted(VALID_SIZES))})
        if is_nonempty(tid):
            id_list.append(tid)
        # 自引用
        if isinstance(t.get("deps"), list) and is_nonempty(tid) and tid in t["deps"]:
            violations.append({"task_id": label, "check": "self_dep",
                               "detail": "deps 自引用: %s -> %s" % (tid, tid)})

    # --- id 全局唯一 ---
    seen = set()
    for tid in id_list:
        if tid in seen:
            violations.append({"task_id": tid, "check": "duplicate_id",
                               "detail": "id 重复: %s" % tid})
        seen.add(tid)

    valid_ids = set(id_list)

    # --- deps 引用闭环（悬空引用） ---
    edges = {}  # tid -> [dep, ...]（仅保留指向已存在 id 的边，用于环检测）
    for t in tasks:
        if not isinstance(t, dict):
            continue
        tid = t.get("id")
        deps = t.get("deps")
        if not is_nonempty(tid) or not isinstance(deps, list):
            continue
        edges[tid] = []
        for d in deps:
            if not isinstance(d, str) or not d.strip():
                violations.append({"task_id": tid, "check": "invalid_dep",
                                   "detail": "deps 元素必须为非空字符串 id: %r" % (d,)})
            elif d not in valid_ids:
                violations.append({"task_id": tid, "check": "dangling_dep",
                                   "detail": "deps 引用不存在的任务 id: %s -> %s" % (tid, d)})
            elif d != tid:
                edges[tid].append(d)

    # --- deps 无环（DFS 三色标记，报告环路径） ---
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in edges}
    reported_cycles = set()

    def dfs(node, stack):
        color[node] = GRAY
        stack.append(node)
        for nxt in edges.get(node, []):
            c = color.get(nxt, WHITE)
            if c == GRAY:
                i = stack.index(nxt)
                cyc = stack[i:] + [nxt]
                key = frozenset(cyc[:-1])
                if key not in reported_cycles:
                    reported_cycles.add(key)
                    violations.append({"task_id": nxt, "check": "cycle",
                                       "detail": "deps 成环: " + " -> ".join(cyc)})
            elif c == WHITE:
                dfs(nxt, stack)
        stack.pop()
        color[node] = BLACK

    for tid in list(edges):
        if color.get(tid, WHITE) == WHITE:
            dfs(tid, [])

    ok = not violations
    print(render(violations, total, ok))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
