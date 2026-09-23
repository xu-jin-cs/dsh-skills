#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rework_budget.py — 回炉计数与终止闸（2026-09-10 用户裁定，REFORM-GATE 判A，
块文件 ~/.agents/logs/reform_blocks/rework_budget_20260910.md）

裁定语义：计划闸/逻辑闸/收益闸既有驳回机制可多次驳回、循环驳回，须杜绝——
  · 回炉总预算 3 次，同一任务签名跨闸、跨驳回点累计不清零；
  · 故障类型隔离（2026-09-14 用户裁定整改）：思路回炉（thinking=逻辑驳回/
    VIOLATION/模板错误）与执行回炉（execution=超时/报错/双校验失败/顺位切换）
    各自上限 2 次，任一类型耗尽或全局 3 次耗尽均出【卡死裁定】——执行类临时
    故障不再烧掉思路缺陷的重试额度；类型由 --type 显式指定或按
    gate+point+reason 关键词机械推断，日志逐条记 type 字段；
  · 每次驳回必须标注「回炉第 N 次（上限 3）」，轮次照抄脚本输出禁止手写；
  · 第 3 次仍未过 → 不再发第 4 次驳回，脚本判 B 出【卡死裁定】，终止并转出
    【卡死点报告】，可复用产出留档附入；
  · 回炉只重跑驳回点对应部分，其余产出保留；禁止靠批量填 N/A 放水凑通过。

覆盖范围：计划闸 plan-select / 逻辑闸 logic_gate / 收益闸 reform_gate 及任何
带驳回路径的流水线。计数 key = 任务签名（一次流水线任务一个 key），同一 key 在
任意闸、任意驳回点的驳回都进同一本账（跨闸跨驳回点累计不清零）。

用法：
  驳回发出前：
    python3 rework_budget.py stamp --key <任务签名> --gate <闸名> --point <驳回点> --reason <理由>
    exit 0 → stdout 给「回炉第 N 次（上限 3）」标注，照抄进驳回通知，禁止手写 N；
    exit 2 → 【卡死裁定】：禁止第 4 次回炉，终止流水线转出【卡死点报告】，
              可复用产出留档附入。
  任务最终通过（销账）：
    python3 rework_budget.py pass --key <任务签名>
  查账：python3 rework_budget.py status --key <任务签名>

状态：~/.agents/logs/rework_budget/<key哈希>.json（账本真源）
留痕：~/.agents/logs/rework_budget.jsonl（每次 stamp/pass 追加，复盘数据源）
四态退出码：0=A / 2=B（卡死） / 3=CLARIFY / 4=VIOLATION（与 gate-switch 族一致）
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

MAX_REWORK = 3
MAX_PER_TYPE = 2  # 故障类型隔离（2026-09-14 用户裁定整改）：思路回炉/执行回炉各自上限 2，全局总上限 3 保留
REWORK_TYPES = ("thinking", "execution")
EXECUTION_HINTS = ("超时", "报错", "执行", "运行", "双校验", "权限", "timeout", "error", "crash")
DEFAULT_STATE_DIR = os.path.expanduser("~/.agents/logs/rework_budget")
DEFAULT_JSONL = os.path.expanduser("~/.agents/logs/rework_budget.jsonl")


def infer_rework_type(gate, point, reason):
    """故障类型机械推断：执行类信号（超时/报错/双校验/运行/权限）→ execution，否则 thinking。
    思路回炉=逻辑闸驳回/候选池 VIOLATION/模板错误；执行回炉=执行阶段超时/报错/顺位切换。"""
    blob = f"{gate} {point} {reason}".lower()
    return "execution" if any(h in blob for h in EXECUTION_HINTS) else "thinking"


def normalize_key(key):
    """任务签名归一化：去首尾空白、压缩连续空白、统一小写（去路径/措辞差异）。"""
    return re.sub(r"\s+", " ", (key or "").strip()).lower()


def state_path(state_dir, key_norm):
    digest = hashlib.sha1(key_norm.encode("utf-8")).hexdigest()[:16]
    return os.path.join(state_dir, f"{digest}.json")


def load_state(state_dir, key_norm):
    path = state_path(state_dir, key_norm)
    if not os.path.exists(path):
        return None, path
    with open(path, encoding="utf-8") as f:
        return json.load(f), path


def save_state(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def append_jsonl(jsonl_path, event):
    os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def cmd_stamp(args, state_dir, jsonl_path):
    key_norm = normalize_key(args.key)
    if not key_norm:
        print(json.dumps({"verdict": "CLARIFY", "reason": "任务签名为空，无法建账"},
                         ensure_ascii=False))
        return 3
    state, path = load_state(state_dir, key_norm)
    if state is None:
        state = {"key": key_norm, "count": 0, "status": "active", "history": []}
    state.setdefault("count_by_type", {t: 0 for t in REWORK_TYPES})
    rtype = args.rtype or infer_rework_type(args.gate, args.point, args.reason)
    if state["status"] == "passed":
        # 已通过销账的任务再次被驳回：重开账本（新一轮流水线，历史保留）
        state["status"] = "active"
        state["count"] = 0
        state["count_by_type"] = {t: 0 for t in REWORK_TYPES}
    entry = {"ts": now(), "gate": args.gate, "point": args.point,
             "reason": args.reason, "type": rtype}
    type_exhausted = state["count_by_type"].get(rtype, 0) >= MAX_PER_TYPE
    if state["status"] == "stuck" or state["count"] >= MAX_REWORK or type_exhausted:
        state["status"] = "stuck"
        entry["event"] = "stuck_verdict"
        state["history"].append(entry)
        save_state(path, state)
        append_jsonl(jsonl_path, {"ts": entry["ts"], "event": "stuck_verdict",
                                  "key": key_norm, "gate": args.gate,
                                  "point": args.point, "reason": args.reason,
                                  "type": rtype})
        budget_desc = (f"{rtype} 类回炉配额 {MAX_PER_TYPE} 次已耗尽" if type_exhausted
                       and state["count"] < MAX_REWORK else
                       f"回炉总预算 {MAX_REWORK} 次已耗尽（跨闸、跨驳回点累计）")
        print(json.dumps({
            "verdict": "B",
            "ruling": "【卡死裁定】",
            "type": rtype,
            "budget": budget_desc,
            "history": state["history"],
            "directive": (
                f"第 {MAX_REWORK} 次回炉仍未过 → 禁止发第 {MAX_REWORK + 1} 次驳回。"
                "照抄本【卡死裁定】，不再发驳回；流水线立即终止，"
                "凭本账 history 转出【卡死点报告】（任务签名/驳回历史/最后驳回点/原因）；"
                "被驳回方停止重跑，仍可复用的产出留档附入卡死点报告。"
                "判定禁止手写，照抄本输出。"
            ),
        }, ensure_ascii=False))
        return 2
    state["count"] += 1
    state["count_by_type"][rtype] = state["count_by_type"].get(rtype, 0) + 1
    n = state["count"]
    tn = state["count_by_type"][rtype]
    entry["event"] = "rework_stamp"
    entry["rework_round"] = n
    entry["type_round"] = tn
    state["history"].append(entry)
    save_state(path, state)
    append_jsonl(jsonl_path, {"ts": entry["ts"], "event": "rework_stamp",
                              "key": key_norm, "rework_round": n,
                              "gate": args.gate, "point": args.point,
                              "reason": args.reason, "type": rtype,
                              "type_round": tn})
    print(json.dumps({
        "verdict": "A",
        "label": f"回炉第 {n} 次（上限 {MAX_REWORK}）",
        "rework_round": n,
        "remaining": MAX_REWORK - n,
        "type": rtype,
        "type_round": tn,
        "type_remaining": MAX_PER_TYPE - tn,
        "directive": (
            f"驳回通知必须原样标注「回炉第 {n} 次（上限 {MAX_REWORK}）」，"
            f"并注明故障类型 {rtype}（该类配额第 {tn}/{MAX_PER_TYPE} 次），"
            "禁止手写轮次、禁止靠批量填 N/A 放水凑通过。"
            f"被驳回方按本轮次执行，只重跑驳回点（{args.point}）对应部分，"
            "其余产出保留不重跑。"
            + (f"警告：预算仅剩 {MAX_REWORK - n} 次，本轮仍未过即出【卡死裁定】"
               "终止流水线。" if n == MAX_REWORK else "")
        ),
    }, ensure_ascii=False))
    return 0


def cmd_pass(args, state_dir, jsonl_path):
    key_norm = normalize_key(args.key)
    state, path = load_state(state_dir, key_norm)
    if state is None:
        print(json.dumps({"verdict": "CLARIFY",
                          "reason": f"无此任务账本：{key_norm}"}, ensure_ascii=False))
        return 3
    state["status"] = "passed"
    save_state(path, state)
    append_jsonl(jsonl_path, {"ts": now(), "event": "rework_pass",
                              "key": key_norm, "used": state["count"],
                              "used_by_type": state.get("count_by_type", {})})
    print(json.dumps({"verdict": "A",
                      "directive": f"任务「{key_norm}」预算内通过，销账。"
                                   f"共用回炉 {state['count']}/{MAX_REWORK} 次，历史留档。"},
                     ensure_ascii=False))
    return 0


def cmd_status(args, state_dir, _jsonl_path):
    key_norm = normalize_key(args.key)
    state, _path = load_state(state_dir, key_norm)
    if state is None:
        print(json.dumps({"verdict": "CLARIFY",
                          "reason": f"无此任务账本：{key_norm}"}, ensure_ascii=False))
        return 3
    print(json.dumps({"verdict": "A", "key": key_norm, "count": state["count"],
                      "status": state["status"], "budget": MAX_REWORK,
                      "count_by_type": state.get("count_by_type", {}),
                      "budget_per_type": MAX_PER_TYPE,
                      "history": state["history"]}, ensure_ascii=False, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(description="回炉计数与终止闸（预算3次，第4次判B出卡死裁定）")
    sub = ap.add_subparsers(dest="action", required=True)
    for name in ("stamp", "pass", "status"):
        p = sub.add_parser(name)
        p.add_argument("--key", required=True, help="任务签名（一次流水线任务一个 key）")
        if name == "stamp":
            p.add_argument("--gate", required=True, help="驳回发出的闸（logic_gate/plan_select/reform_gate…）")
            p.add_argument("--point", required=True, help="驳回点（缺哪力/缺哪字段/哪步双校验失败）")
            p.add_argument("--reason", required=True, help="驳回理由")
            p.add_argument("--type", dest="rtype", choices=list(REWORK_TYPES), default=None,
                           help="故障类型：thinking=思路回炉（逻辑驳回/VIOLATION/模板错误）/"
                                "execution=执行回炉（超时/报错/双校验失败）；缺省按 gate+point+reason 机械推断")
        p.add_argument("--state-dir", default=os.environ.get("REWORK_BUDGET_DIR", DEFAULT_STATE_DIR),
                       help=argparse.SUPPRESS)
        p.add_argument("--jsonl", default=DEFAULT_JSONL, help=argparse.SUPPRESS)
    args = ap.parse_args()
    handler = {"stamp": cmd_stamp, "pass": cmd_pass, "status": cmd_status}[args.action]
    return handler(args, args.state_dir, args.jsonl)


if __name__ == "__main__":
    sys.exit(main())
