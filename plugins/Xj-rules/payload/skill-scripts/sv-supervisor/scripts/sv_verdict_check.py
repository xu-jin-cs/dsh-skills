#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sv_verdict_check.py — sv-supervisor 终裁 verdict 机械核验（2026-08-15 gate-switch 门禁配套）

用途：终裁结论（sv_verdict）禁止手写。sv-supervisor 输出 APPROVED/BLOCKED 前，
必须跑本脚本机械核验 .flow_state.json 与交付物，照抄输出结论。

核验项（按 sv-supervisor/SKILL.md §6.2/§6.3/§6.4 终裁清单能机械落地的部分）：
  1. state_parseable    .flow_state.json 可解析为 JSON 对象
  2. key_fields         关键字段非空（步骤标识 + sv_verdict 块）
  3. deliverable_hash   deliverables[] 登记 hash 与交付物实际 SHA256 重算一致（§6.4 雏形扩展）
  4. deliverable_arg    --deliverable 传入的文件存在且已在 deliverables[] 登记（如带 hash 则校验）
  5. count_equation     计数等式：total == passed + failed（execution_result/summary/api_count 类）
  6. verdict_enum       sv_verdict ∈ 合法枚举 {APPROVED, BLOCKED, REVIEW_REQUIRED, PENDING}
  7. violation_points   违规积分字段 < 3（SKILL §6.3④ 阈值；≥3 触发熔断）
  8. state_enum         状态机当前状态 ∈ 合法状态集合

用法：
  python3 sv_verdict_check.py --state <.flow_state.json> [--deliverable <文件> ...]

输出：stdout JSON {"pass": true|false, "violations": [{"check", "detail"}, ...]}
退出码：0 = 全部通过；1 = 存在违例（violations 即驳回理由）
纯 stdlib。
"""
import argparse
import hashlib
import json
import os
import sys

VERDICT_ENUM = {"APPROVED", "BLOCKED", "REVIEW_REQUIRED", "PENDING"}
STATE_ENUM = {"PENDING", "IN_PROGRESS", "RUNNING", "COMPLETED", "CLOSED",
              "BLOCKED", "PAUSED", "ABORTED", "FAILED", "REVIEW_REQUIRED"}
POINTS_THRESHOLD = 3  # SKILL §6.3④：违规积分 < 3；≥3 熔断
PATH_KEYS = ("path", "file", "file_path", "filepath")
HASH_KEYS = ("sha256", "hash", "sha256_hash")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def dig_any(d, keys):
    """在 dict 中按候选键名取第一个存在的值。"""
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d:
            return d[k]
    return None


def iter_dicts(obj):
    """递归产出所有 dict 节点。"""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from iter_dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_dicts(v)


def check_state(state_path, extra_deliverables):
    violations = []

    def fail(check, detail):
        violations.append({"check": check, "detail": detail})

    # 1. state_parseable
    if not os.path.isfile(state_path):
        fail("state_parseable", f".flow_state.json 不存在: {state_path}")
        return violations
    try:
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        fail("state_parseable", f".flow_state.json JSON 解析失败: {e}")
        return violations
    if not isinstance(data, dict):
        fail("state_parseable", ".flow_state.json 根节点不是 JSON 对象")
        return violations

    state_dir = os.path.dirname(os.path.abspath(state_path))

    # 2. key_fields：步骤标识 + sv_verdict 块非空
    step_val = None
    for k in ("current_step", "step", "current_status", "status"):
        if k in data and data[k] not in (None, "", [], {}):
            step_val = data[k]
            break
    if step_val is None:
        fail("key_fields", "缺少非空步骤标识字段（current_step/step/current_status/status）")
    sv = data.get("sv_verdict")
    if sv in (None, "", [], {}):
        fail("key_fields", "sv_verdict 字段缺失或为空")

    # 3. deliverable_hash：deliverables[] 登记 hash 与实际 SHA256 重算比对
    deliverables = data.get("deliverables")
    registered = {}  # 规范化绝对路径 -> entry
    if deliverables is None:
        fail("deliverable_hash", "deliverables[] 字段缺失（无法核验交付物登记）")
    elif not isinstance(deliverables, list):
        fail("deliverable_hash", "deliverables 字段不是数组")
    else:
        for i, entry in enumerate(deliverables):
            if not isinstance(entry, dict):
                fail("deliverable_hash", f"deliverables[{i}] 不是对象")
                continue
            rel = dig_any(entry, PATH_KEYS)
            if not rel:
                fail("deliverable_hash", f"deliverables[{i}] 缺少路径字段（path/file/file_path）")
                continue
            fpath = rel if os.path.isabs(rel) else os.path.join(state_dir, rel)
            fpath = os.path.abspath(fpath)
            registered[fpath] = entry
            if not os.path.isfile(fpath):
                fail("deliverable_hash", f"deliverables[{i}] 登记文件不存在: {fpath}")
                continue
            expected = dig_any(entry, HASH_KEYS)
            if not expected:
                fail("deliverable_hash", f"deliverables[{i}] 缺少 hash 字段（sha256/hash）: {fpath}")
                continue
            actual = sha256_file(fpath)
            if str(expected).lower() != actual:
                fail("deliverable_hash",
                     f"deliverables[{i}] HASH_MISMATCH: {fpath} "
                     f"expected={expected} actual={actual}")

    # 4. deliverable_arg：--deliverable 传入的文件存在且已登记
    for d in extra_deliverables:
        dpath = os.path.abspath(d)
        if not os.path.isfile(dpath):
            fail("deliverable_arg", f"--deliverable 文件不存在: {dpath}")
            continue
        if dpath not in registered:
            fail("deliverable_arg",
                 f"--deliverable 文件未在 deliverables[] 登记（登记缺失，hash 无从核验）: {dpath}")

    # 5. count_equation：total == passed + failed（含 api_count 变体）
    for node in iter_dicts(data):
        if all(isinstance(node.get(k), int) for k in ("total", "passed", "failed")):
            if node["total"] != node["passed"] + node["failed"]:
                fail("count_equation",
                     f"计数等式不成立: total={node['total']} != "
                     f"passed={node['passed']} + failed={node['failed']}")
        if all(isinstance(node.get(k), int) for k in ("api_count", "passed", "failed")):
            if node["api_count"] != node["passed"] + node["failed"]:
                fail("count_equation",
                     f"计数等式不成立: api_count={node['api_count']} != "
                     f"passed={node['passed']} + failed={node['failed']}")

    # 6. verdict_enum
    verdict = None
    if isinstance(sv, dict):
        verdict = sv.get("current") or sv.get("verdict") or sv.get("value")
    elif isinstance(sv, str):
        verdict = sv
    if verdict is not None and verdict not in VERDICT_ENUM:
        fail("verdict_enum",
             f"sv_verdict={verdict!r} 不在合法枚举 {sorted(VERDICT_ENUM)}")

    # 7. violation_points < 3（SKILL §6.3④）
    for node in iter_dicts(data):
        for k in ("violation_points", "violation_score", "points",
                  "deduction_points", "total_deduction"):
            v = node.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                if v >= POINTS_THRESHOLD:
                    fail("violation_points",
                         f"违规积分 {k}={v} ≥ 阈值 {POINTS_THRESHOLD}（熔断，禁止 APPROVED）")

    # 8. state_enum：状态机当前状态合法
    checked_state = False
    for node in iter_dicts(data):
        for k in ("status", "current_status", "state"):
            v = node.get(k)
            if isinstance(v, str) and v:
                checked_state = True
                if v not in STATE_ENUM:
                    fail("state_enum",
                         f"状态机状态 {k}={v!r} 不在合法状态集合 {sorted(STATE_ENUM)}")
    if not checked_state:
        fail("state_enum", "未找到任何状态字段（status/current_status/state）")

    return violations


def main():
    ap = argparse.ArgumentParser(
        description="sv-supervisor 终裁 verdict 机械核验（禁止手写 APPROVED）")
    ap.add_argument("--state", required=True, help=".flow_state.json 路径")
    ap.add_argument("--deliverable", dest="deliverables", action="append",
                    default=[], help="交付物路径（可多次），需已登记于 deliverables[]")
    args = ap.parse_args()

    violations = check_state(args.state, args.deliverables)
    out = {"pass": not violations, "violations": violations,
           "state": os.path.abspath(args.state)}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    # 末行单行摘要（gate_switch script_exit 取 stdout 末行作为违例详情）
    if violations:
        summary = "; ".join(f"{v['check']}: {v['detail']}" for v in violations)
        print(f"[sv_verdict_check] FAIL {len(violations)} 项: {summary}")
    else:
        print("[sv_verdict_check] PASS 全项机械核验通过")
    sys.exit(0 if not violations else 1)


if __name__ == "__main__":
    main()
