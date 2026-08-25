#!/usr/bin/env python3
"""
flow_kernel.py — PM 工作流流程内核（通用，零 PM 规则硬编码）。

设计原则（与 Xj-engine 的 et() 契约同构）：
  - 流程规则（节点拓扑 / 分支条件 / 状态机 / 交付物模板）全部是**入参数据**，
    来自 --rules 指向的 flow.yml；内核不持有任何一条 PM 规则；
  - 内核只做四件事：交付物 Schema 校验 → 分支解析 → 状态机合法流转校验
    → 输出下一步指令（含状态同步命令）；
  - 出参 code 机械可判：
      success —— 交付物校验通过 + 流转合法，给出 next_node 与 sync 命令
      reject  —— 交付物缺失 / Schema 不符 / 文件为空
      block   —— 状态机非法流转 / 分支无出口 / 节点未定义
      error   —— 内核自身异常（规则文件损坏等）

用法：
  # 节点完成，请求流转判定
  python3 flow_kernel.py advance \
      --rules flow.yml \
      --state <项目根>/.flow_state.json \
      --node be --outcome completed_pass \
      --deliverable backend_status.json --deliverable .api-schema.json

  # 仅查询节点出口（不校验交付物）
  python3 flow_kernel.py routes --rules flow.yml --node be

出参（JSON 到 stdout，全程留痕到 stderr 不污染管道）：
  {
    "code": "success|reject|block|error",
    "node": "be",
    "outcome": "completed_pass",
    "next_node": "pm_quality_gate" | null,
    "sync_commands": ["<状态同步命令>", ...],
    "checks": { "deliverables": [...], "transition": {...}, "branch": {...} },
    "reasons": ["..."]
  }

状态同步命令：内核不绑定任何宿主，同步命令模板由环境变量
`PM_HARNESS_SYNC_CMD` 提供（Python str.format 模板，可用占位符
{project} {state} {title} {operator}）。未设置时默认只输出一条
状态流转提示，适配方应将其指向所接引擎（如 Xj-engine）的状态同步入口。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import jsonschema
import yaml

# 特殊出口标记（不属于具体节点）
SPECIAL_TARGETS = {"__end__", "__freeze__", "__flow_b__"}
# 并行汇合标记（__wait_xxx__ / __parallel_xxx__）
PARALLEL_PREFIXES = ("__wait_", "__parallel_")

# 状态同步命令模板（环境变量可配置，不绑定私有宿主）
_DEFAULT_SYNC_CMD = (
    'echo "[pm] 状态流转 -> {state} ({title})，操作者 {operator}；'
    '将此处接入你的引擎状态同步入口（如 xj-engine）"'
)
SYNC_CMD_TPL = os.environ.get("PM_HARNESS_SYNC_CMD", _DEFAULT_SYNC_CMD)


# ═══════════════════════════════════════════════════════════════
# 规则加载（入参）
# ═══════════════════════════════════════════════════════════════

def load_rules(path: str) -> dict[str, Any]:
    with open(os.path.abspath(os.path.expanduser(path)), "r", encoding="utf-8") as f:
        rules = yaml.safe_load(f)
    if not isinstance(rules, dict) or not rules.get("agents"):
        raise ValueError(f"规则文件缺少 agents 定义: {path}")
    return rules


def node_index(rules: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {a["name"]: a for a in rules.get("agents", [])}


# ═══════════════════════════════════════════════════════════════
# ① 交付物校验（Schema 模板来自规则入参）
# ═══════════════════════════════════════════════════════════════

def check_deliverables(
    node: dict[str, Any], deliverable_paths: list[str], project_root: str
) -> dict[str, Any]:
    specs = node.get("deliverables") or []
    results: list[dict[str, Any]] = []
    failures: list[str] = []

    provided = {os.path.basename(p): os.path.abspath(os.path.expanduser(p))
                for p in deliverable_paths}

    for spec in specs:
        fname = spec["filename"]
        item: dict[str, Any] = {"filename": fname, "passed": True, "reason": ""}
        path = provided.get(fname) or os.path.join(project_root, fname)

        if not os.path.isfile(path):
            item.update(passed=False, reason=f"交付物缺失: {fname}")
            failures.append(item["reason"])
            results.append(item)
            continue
        if os.path.getsize(path) == 0:
            item.update(passed=False, reason=f"交付物为空（0 字节）: {fname}")
            failures.append(item["reason"])
            results.append(item)
            continue

        # JSON 交付物：按规则内 template（JSON Schema）机械校验
        if fname.endswith(".json") and spec.get("template"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                schema = json.loads(spec["template"])
                jsonschema.validate(data, schema)
            except json.JSONDecodeError as exc:
                item.update(passed=False, reason=f"{fname} JSON 解析失败: {exc}")
                failures.append(item["reason"])
            except (jsonschema.ValidationError, jsonschema.SchemaError) as exc:
                item.update(passed=False, reason=f"{fname} Schema 不符: {exc.message}")
                failures.append(item["reason"])
        results.append(item)

    return {"passed": not failures, "results": results, "failures": failures}


# ═══════════════════════════════════════════════════════════════
# ② 分支解析（branch_conditions 来自规则入参）
# ═══════════════════════════════════════════════════════════════

def resolve_branch(node: dict[str, Any], outcome: str,
                   idx: dict[str, dict[str, Any]]) -> dict[str, Any]:
    branches = node.get("branch_conditions") or {}
    if not branches:
        return {"passed": False, "target": None,
                "reason": f"节点 [{node['name']}] 未定义 branch_conditions"}
    target = branches.get(outcome)
    if target is None:
        return {"passed": False, "target": None,
                "reason": f"节点 [{node['name']}] 无出口匹配 outcome={outcome}（可选: {list(branches)}）"}
    if target in SPECIAL_TARGETS or target.startswith(PARALLEL_PREFIXES):
        return {"passed": True, "target": target, "reason": ""}
    if target not in idx:
        return {"passed": False, "target": target,
                "reason": f"分支目标 [{target}] 未在 agents 中定义"}
    return {"passed": True, "target": target, "reason": ""}


# ═══════════════════════════════════════════════════════════════
# ③ 状态机合法流转校验（transitions 来自规则入参 state_model）
# ═══════════════════════════════════════════════════════════════

def check_transitions(
    rules: dict[str, Any], current_state: str, sync_states: list[str]
) -> dict[str, Any]:
    transitions = (rules.get("state_model") or {}).get("transitions") or {}
    results: list[dict[str, Any]] = []
    cur = current_state
    for target in sync_states:
        allowed = transitions.get(cur, [])
        ok = cur == target or target in allowed
        results.append({"from": cur, "to": target, "passed": ok,
                        "reason": "" if ok else f"非法跳步: {cur} → {target}（允许: {allowed}）"})
        if ok:
            cur = target  # 链式推进：下一跳以前一跳目标为源
    failures = [r["reason"] for r in results if not r["passed"]]
    return {"passed": not failures, "results": results, "failures": failures}


# ═══════════════════════════════════════════════════════════════
# 内核唯一入口：advance
# ═══════════════════════════════════════════════════════════════

def advance(
    rules: dict[str, Any],
    state: dict[str, Any],
    node_name: str,
    outcome: str,
    deliverable_paths: list[str],
    project_name: str,
    operator: str,
) -> dict[str, Any]:
    idx = node_index(rules)
    node = idx.get(node_name)
    if node is None:
        return {"code": "block", "node": node_name, "outcome": outcome,
                "next_node": None, "sync_commands": [], "checks": {},
                "reasons": [f"节点 [{node_name}] 未在规则文件中定义"]}

    checks: dict[str, Any] = {}
    reasons: list[str] = []

    # ① 交付物校验（节点声明了 deliverables 才校验）
    project_root = state.get("project_path") or os.getcwd()
    if node.get("deliverables"):
        d = check_deliverables(node, deliverable_paths, project_root)
        checks["deliverables"] = d
        if not d["passed"]:
            return {"code": "reject", "node": node_name, "outcome": outcome,
                    "next_node": None, "sync_commands": [], "checks": checks,
                    "reasons": d["failures"]}

    # ② 分支解析
    b = resolve_branch(node, outcome, idx)
    checks["branch"] = b
    if not b["passed"]:
        return {"code": "block", "node": node_name, "outcome": outcome,
                "next_node": None, "sync_commands": [], "checks": checks,
                "reasons": [b["reason"]]}
    reasons.extend([b["reason"]] if b["reason"] else [])

    # ③ 状态机校验（节点声明 harness_sync 才校验）
    sync_commands: list[str] = []
    sync_states: list[str] = []
    for sync in node.get("harness_sync") or []:
        sync_states.append(sync["state"])
        title = sync.get("title", sync["state"])
        sync_commands.append(
            SYNC_CMD_TPL.format(
                project=project_name, state=sync["state"],
                title=title, operator=operator,
            )
        )
    if sync_states:
        current_state = state.get("current_state") or "PENDING"
        t = check_transitions(rules, current_state, sync_states)
        checks["transition"] = t
        if not t["passed"]:
            return {"code": "block", "node": node_name, "outcome": outcome,
                    "next_node": None, "sync_commands": [], "checks": checks,
                    "reasons": t["failures"]}

    return {"code": "success", "node": node_name, "outcome": outcome,
            "next_node": b["target"], "sync_commands": sync_commands,
            "checks": checks, "reasons": reasons}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PM 流程内核（规则全入参）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_adv = sub.add_parser("advance", help="节点完成，请求流转判定")
    p_adv.add_argument("--rules", required=True)
    p_adv.add_argument("--state", required=True)
    p_adv.add_argument("--node", required=True)
    p_adv.add_argument("--outcome", required=True)
    p_adv.add_argument("--deliverable", action="append", default=[])
    p_adv.add_argument("--project", default="")
    p_adv.add_argument("--operator", default="PM")

    p_rt = sub.add_parser("routes", help="查询节点全部出口")
    p_rt.add_argument("--rules", required=True)
    p_rt.add_argument("--node", required=True)

    args = parser.parse_args(argv)

    try:
        rules = load_rules(args.rules)
        if args.cmd == "routes":
            idx = node_index(rules)
            node = idx.get(args.node)
            if node is None:
                out = {"code": "block", "reasons": [f"节点 [{args.node}] 未定义"]}
            else:
                out = {"code": "success", "node": args.node,
                       "branches": node.get("branch_conditions") or {},
                       "next_agents": node.get("next_agents") or [],
                       "parallel_group": node.get("parallel_group")}
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 0 if out["code"] == "success" else 2

        with open(os.path.abspath(os.path.expanduser(args.state)), "r", encoding="utf-8") as f:
            state = json.load(f)
        project_name = args.project or state.get("project_name") or "unknown"
        out = advance(rules, state, args.node, args.outcome,
                      args.deliverable, project_name, args.operator)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return {"success": 0, "reject": 2, "block": 3}.get(out["code"], 4)
    except Exception as exc:
        print(json.dumps({"code": "error", "reasons": [str(exc)]},
                         ensure_ascii=False, indent=2))
        return 4


if __name__ == "__main__":
    sys.exit(main())
