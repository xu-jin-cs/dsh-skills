#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dispatch_switch.py — 调度单刀双掷开关（2026-08-15 用户裁定，parallel-dispatch 唯一出口）

物理原型：单刀双掷（SPDT）——一个刀闸、两个掷点，电流必走一路，无悬空态。
多任务触发并行判定后、执行前，必须扳动本开关，输出必然二选一：

  掷点 A（执行并行）：无依赖单元 ≥2，按数量轴机制扇出（subagent / 分组 / workflow）
  掷点 B（不执行并行）：串行 —— 但多任务串行必须携带依赖链理由，空理由即 VIOLATION

设计要点：
  1. 开关是机械脚本不是 prompt 指令：判定逻辑在脚本内，模型只照抄输出，想错判无机会；
  2. 判断逻辑可插拔：v1 复用 dispatch_probe 本地规则；未来可在 decide() 层挂引擎签发，开关外形不变；
  3. 每次扳动留痕 ~/.agents/logs/dispatch_switch.jsonl（时间/输入/掷点/理由），B/A 比率进复盘。

退出码（供 shell 路由）：
  0 = A（执行并行）   2 = B（合法串行）   3 = CLARIFY（信号不足/会话日志不可定位，禁止扳动）   4 = VIOLATION（B 档无理由 / 掷点 A 前置缺失）

掷点 A 机械前置三道闸（2026-08-16 用户裁定："用扳手解决概率触发问题"/"都做，N 可量化"）：
  闸1 清单登记：本 turn 必须已存在 todo/write 事件且条目数 ≥ 扇出单元数
      （缺失/覆盖不全 → exit 4，先补 todo_write 再重扳）。
  闸2 基线存在：有效文件数 ≥ 4（BASELINE_MIN_FILES，对齐规模轴 ≤3 免评估）时
      必须 --baseline 携带上下文基线文件路径，且每个文件真实存在且非空
      （缺失 → exit 4，先产出基线文件再重扳）。治"各分身上下文不一致"。
  闸3 探针实证：扇出单元数 ≥ 6（PROBE_MIN_FANOUT 收益拐点量化：净收益
      f(N)=p·C·N−c−摩擦(N)，c≈0.3路、retro-pm-124 实证 p≈5% → N*=c/p≈6，
      且与数量轴 6~9 分组档起点重合，双轴同数）时，会话日志
      必须存在 30 分钟（PROBE_FRESH_SECONDS）内已完成往返的扇出类调用实证
      （缺失 → exit 4，先以前台模式派 1 个极小探针任务，回执到达后重扳）。
      治 retro-pm-124"通道盲扇出"。

用法：
  python3 dispatch_switch.py --files 5 --units 4 --desc "改 4 个页面"
  python3 dispatch_switch.py --files 6 --units 3 --coupled --dep-reason "三任务共用同一会话状态表"
  python3 dispatch_switch.py --files 5 --units 4 --session-log <会话jsonl.zstd路径>  # 自动定位失败时显式指定
"""
import argparse
import datetime
import glob
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dispatch_probe import decide as probe_decide  # noqa: E402
import session_log_compat as slog  # noqa: E402

DEFAULT_LOG = os.path.expanduser("~/.agents/logs/dispatch_switch.jsonl")

EXIT_A, EXIT_B, EXIT_CLARIFY, EXIT_VIOLATION = 0, 2, 3, 4

# ---- 掷点 A 前置：机械校验三闸（2026-08-16 裁定） ----
# 2026-08-24 Kimi Code 迁移：会话日志定位/解析移交 session_log_compat
# （旧版 zstd + Kimi wire.jsonl 双格式）。
TODO_GATE_FRESH_SECONDS = 900  # 会话日志活跃窗口：窗口内被写入才视为"当前会话"
BASELINE_MIN_FILES = 4       # 有效文件数 ≥4（规模轴 >3）强制上下文基线文件
PROBE_MIN_FANOUT = 6         # 扇出单元 ≥6 强制最小探针（收益拐点 N*=c/p≈0.3/0.05，对齐数量轴 6~9 档）
PROBE_FRESH_SECONDS = 1800   # 探针实证 30 分钟有效窗
FANOUT_TOOL_NAMES = slog.LEGACY_FANOUT_TOOLS + slog.KIMI_FANOUT_TOOLS


def resolve_session_log(session_log=None):
    """定位当前会话日志（旧版/Kimi 双格式），返回 (path, source)。"""
    return slog.resolve_session_log(session_log, TODO_GATE_FRESH_SECONDS)


def scan_turn_todos(path):
    """扫描会话日志，返回当前 turn 的任务清单条目数；无登记返回 0，读取失败返回 None。

    todos 投影随 turn 起点清空（last-write-wins），故只认最后一个
    turn 起点之后的最后一次清单登记（旧版 todo/write / Kimi TodoList）。
    """
    lines = slog.read_session_lines(path)
    if lines is None:
        return None
    cur_todos = None
    for ev in slog.iter_events(lines, slog.is_kimi_log(path)):
        if ev["kind"] == "turn_start":
            cur_todos = None
        elif ev["kind"] == "todo_write":
            cur_todos = len(ev["todos"])
    return cur_todos if cur_todos is not None else 0


def todo_gate_check(n, session_log=None):
    """掷点 A 前置校验：ok=True 放行 / ok=False 拒扳 / ok=None 无法判定（CLARIFY）。"""
    path, source = resolve_session_log(session_log)
    if path is None:
        return {"ok": None,
                "reason": "无法定位当前会话日志（旧版/Kimi 均未命中）→ 用 --session-log 显式指定后重扳"}
    count = scan_turn_todos(path)
    if count is None:
        return {"ok": None,
                "reason": f"会话日志读取失败：{path}"}
    if count == 0:
        return {"ok": False, "log": path, "log_source": source, "todos": 0,
                "reason": "当前 turn 无任务清单登记事件（todo/write 或 TodoList）→ 扇出前任务清单未登记（GUI 无清单/进度可展示）"}
    if n is not None and count < n:
        return {"ok": False, "log": path, "log_source": source, "todos": count,
                "reason": f"当前 turn 任务清单仅 {count} 条 < 扇出单元 {n} → 清单覆盖不全"}
    return {"ok": True, "log": path, "log_source": source, "todos": count}


def baseline_gate_check(baseline, files_effective):
    """闸2 基线存在：有效文件数达到 BASELINE_MIN_FILES 时基线文件必须真实非空。"""
    if files_effective is None or files_effective < BASELINE_MIN_FILES:
        return {"ok": True, "skipped": True,
                "reason": "有效文件数 %s < %s → 免评估档，基线闸跳过" % (files_effective, BASELINE_MIN_FILES)}
    paths = [x.strip() for x in (baseline or "").split(",") if x.strip()]
    if not paths:
        return {"ok": False,
                "reason": "有效文件数 %s ≥ %s 但未提供 --baseline → 各分身将无统一上下文基线（契约冲突/返工风险）"
                          % (files_effective, BASELINE_MIN_FILES)}
    bad = []
    for x in paths:
        full = os.path.expanduser(x)
        if not (os.path.isfile(full) and os.path.getsize(full) > 0):
            bad.append(x)
    if bad:
        return {"ok": False, "paths": paths,
                "reason": "基线文件不存在或为空：" + "；".join(bad)}
    return {"ok": True, "paths": paths}


def probe_gate_check(units, session_log=None):
    """闸3 探针实证：units 达到 PROBE_MIN_FANOUT 时，窗口内须有已完成往返的扇出类调用。"""
    if units is None or units < PROBE_MIN_FANOUT:
        return {"ok": True, "skipped": True,
                "reason": "扇出单元 %s < %s → 探针闸跳过" % (units, PROBE_MIN_FANOUT)}
    path, source = resolve_session_log(session_log)
    if path is None:
        return {"ok": None,
                "reason": "无法定位当前会话日志（旧版/Kimi 均未命中）→ 用 --session-log 显式指定后重扳"}
    lines = slog.read_session_lines(path)
    if lines is None:
        return {"ok": None, "reason": "会话日志读取失败：%s" % path}
    cutoff_ms = (time.time() - PROBE_FRESH_SECONDS) * 1000
    calls = {}
    settled = set()
    for ev in slog.iter_events(lines, slog.is_kimi_log(path)):
        if ev["kind"] == "fanout_call":
            calls[ev.get("call_id")] = ev.get("time_ms") or 0
        elif ev["kind"] == "tool_result" and ev.get("call_id"):
            settled.add(ev["call_id"])
    proofs = sum(1 for cid, t in calls.items() if cid in settled and t >= cutoff_ms)
    if proofs == 0:
        return {"ok": False, "log": path, "log_source": source, "proofs": 0,
                "reason": "扇出单元 %s ≥ %s，但 %s 分钟内无已完成往返的扇出类调用实证 → 通道未验证（retro-pm-124 盲扇出风险）"
                          % (units, PROBE_MIN_FANOUT, PROBE_FRESH_SECONDS // 60)}
    return {"ok": True, "log": path, "log_source": source, "proofs": proofs}


def flip(files, units, coupled, batch, desc, dep_reason, force_serial, session_log=None, baseline=None, dep_type=""):
    """扳动开关：probe 判定 → 映射为单刀双掷 verdict。"""
    # ---- 契约先行分片（2026-08-17 REFORM-GATE 判A落地，块文件
    #      ~/.agents/logs/reform_gate_block_contract_sharding_20260817.md）：
    #      coupled 先分契约耦合/产物耦合。契约耦合只需在分片时冻结 API/接口契约，
    #      冻约后各片即无依赖，按无耦合并行扇出；产物耦合才走原 coupled 串行/评估路径。
    contract_note = None
    if coupled and dep_type == "contract":
        contract_note = ("契约先行分片（--dep-type contract）：先冻结 API/接口契约，"
                         "冻约后各片视为无依赖 → 按无耦合并行扇出，构建/验证串行收口")
        coupled = False

    probe = probe_decide(files, units, coupled, batch, desc)
    if contract_note:
        probe["reasons"] = [contract_note] + probe["reasons"]

    # ---- 悬空态禁止：信号不足不许扳动 ----
    if probe.get("clarify"):
        return {
            "verdict": "CLARIFY",
            "throw": None,
            "clarify": probe["clarify"],
            "reasons": probe["reasons"],
        }, EXIT_CLARIFY

    n = units if units is not None else files
    gate = probe.get("gate_declaration")

    # ---- 掷点 A：执行并行（人工强制串行时跳过）----
    if probe["fanout"] >= 1 and not force_serial:
        # 机械前置（2026-08-16 裁定）：本 turn 必须已 todo_write 登记任务清单
        n_eff = n if n is not None else probe["fanout"]
        todo_gate = todo_gate_check(n_eff, session_log)
        if todo_gate["ok"] is None:
            return {
                "verdict": "CLARIFY",
                "throw": None,
                "clarify": todo_gate["reason"],
                "todo_gate": todo_gate,
                "reasons": probe["reasons"],
            }, EXIT_CLARIFY
        if todo_gate["ok"] is False:
            return {
                "verdict": "VIOLATION",
                "throw": None,
                "gate_declaration": gate,
                "todo_gate": todo_gate,
                "reasons": probe["reasons"] + [
                    f"掷点 A 闸1 清单登记未过：{todo_gate['reason']} → 违规，开关拒绝扳动"
                ],
                "directive": "先调用 todo_write 把全部子任务登记进任务清单（本 turn 内，条目数 ≥ 扇出单元数），再重扳本开关",
            }, EXIT_VIOLATION
        baseline_gate = baseline_gate_check(baseline, files if files is not None else n_eff)
        if baseline_gate["ok"] is False:
            return {
                "verdict": "VIOLATION",
                "throw": None,
                "gate_declaration": gate,
                "todo_gate": todo_gate,
                "baseline_gate": baseline_gate,
                "reasons": probe["reasons"] + [
                    f"掷点 A 闸2 基线存在未过：{baseline_gate['reason']} → 违规，开关拒绝扳动"
                ],
                "directive": "先产出统一上下文基线文件（pm_plan/task_slice_plan/.prd.md 等适用项），再以 --baseline <路径1,路径2> 重扳本开关",
            }, EXIT_VIOLATION
        probe_gate = probe_gate_check(n_eff, session_log)
        if probe_gate["ok"] is None:
            return {
                "verdict": "CLARIFY",
                "throw": None,
                "clarify": probe_gate["reason"],
                "todo_gate": todo_gate,
                "baseline_gate": baseline_gate,
                "probe_gate": probe_gate,
                "reasons": probe["reasons"],
            }, EXIT_CLARIFY
        if probe_gate["ok"] is False:
            return {
                "verdict": "VIOLATION",
                "throw": None,
                "gate_declaration": gate,
                "todo_gate": todo_gate,
                "baseline_gate": baseline_gate,
                "probe_gate": probe_gate,
                "reasons": probe["reasons"] + [
                    f"掷点 A 闸3 探针实证未过：{probe_gate['reason']} → 违规，开关拒绝扳动"
                ],
                "directive": "先以 run_in_background:false 派 1 个极小探针任务验证分身通道，回执到达后重扳本开关",
            }, EXIT_VIOLATION
        passed = [f"掷点 A 闸1 清单登记已通过：本 turn 任务清单已登记 {todo_gate['todos']} 条（todo/write 实证）"]
        if not baseline_gate.get("skipped"):
            passed.append(f"掷点 A 闸2 基线存在已通过：{len(baseline_gate['paths'])} 个基线文件真实非空")
        if not probe_gate.get("skipped"):
            passed.append(f"掷点 A 闸3 探针实证已通过：窗口内 {probe_gate['proofs']} 次扇出类调用完成往返")
        return {
            "verdict": "A",
            "throw": "A",
            "mechanism": probe["mechanism"],
            "fanout": probe["fanout"],
            "scale": probe["scale"],
            "topology": probe["topology"],
            "gate_declaration": gate,
            "todo_gate": todo_gate,
            "baseline_gate": baseline_gate,
            "probe_gate": probe_gate,
            "reasons": probe["reasons"] + passed,
            "directive": "照抄 gate_declaration 输出后，按 mechanism 立即扇出，禁止只评估不执行；每路 settle 后立即销号对应 todo",
        }, EXIT_A

    # ---- 掷点 B：不执行并行（串行）----
    natural = (n is None or n <= 1)  # 单体任务串行为自然态，无需理由
    if natural and not force_serial:
        return {
            "verdict": "B",
            "throw": "B",
            "mechanism": "sequential",
            "gate_declaration": None,
            "reasons": probe["reasons"] + ["单体任务（无并行对象）→ 自然串行，免依赖链理由"],
            "directive": "单线程执行即可，本开关仅留痕",
        }, EXIT_B

    # 多任务判串行（probe 判定串行 或 --force-serial 人工强制）：必须携带依赖链理由
    if not dep_reason or not dep_reason.strip():
        return {
            "verdict": "VIOLATION",
            "throw": None,
            "gate_declaration": gate,
            "reasons": probe["reasons"] + [
                "多任务（≥2 子任务）判串行但未提供 --dep-reason 依赖链理由 → 违规，开关拒绝扳动"
            ],
            "directive": "要么补 --dep-reason 重新扳动，要么改判 A 执行并行",
        }, EXIT_VIOLATION

    src = "人工强制串行(--force-serial)" if force_serial else "探针判定串行"
    gate_fixed = (f"[PARALLEL-GATE] 子任务数:{n} | 无依赖:0 | "
                  f"判定:sequential | 机制:串行({dep_reason.strip()})")
    return {
        "verdict": "B",
        "throw": "B",
        "mechanism": "sequential",
        "dep_reason": dep_reason.strip(),
        "gate_declaration": gate_fixed,
        "reasons": probe["reasons"] + [f"多任务串行（{src}）理由已备案：{dep_reason.strip()}"],
        "directive": "照抄 gate_declaration 输出后串行执行；理由已留痕，复盘纳入 B/A 比率审计",
    }, EXIT_B


def append_log(path, entry):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="调度单刀双掷开关（parallel-dispatch 唯一出口）")
    ap.add_argument("--files", type=int, default=None, help="涉及文件数量")
    ap.add_argument("--units", type=int, default=None, help="无依赖独立单元数（缺省=文件数）")
    ap.add_argument("--coupled", action="store_true", help="存在跨模块契约/状态耦合")
    ap.add_argument("--dep-type", type=str, default="", choices=["", "contract", "artifact"],
                    help="coupled 前置细分（契约先行分片）：contract=契约耦合（冻约后并行，推荐）；artifact=产物耦合（才允许串行评估路径）")
    ap.add_argument("--batch", action="store_true", help="批量同类操作（强制 workflow）")
    ap.add_argument("--dep-reason", type=str, default="", help="B 档必备：多任务串行的依赖链理由，空即违规")
    ap.add_argument("--force-serial", action="store_true",
                    help="人工强制扳向 B（多任务想串行的唯一合法通道，必须配 --dep-reason）")
    ap.add_argument("--desc", type=str, default="", help="任务描述（留痕用）")
    ap.add_argument("--session-log", type=str, default=None,
                    help="掷点 A 前置校验用：显式指定当前会话日志路径（旧版 session.jsonl.zstd 或 Kimi wire.jsonl；缺省自动定位活跃日志）")
    ap.add_argument("--baseline", type=str, default="",
                    help="闸2 用：统一上下文基线文件路径（逗号分隔）；有效文件数 ≥4 时强制")
    ap.add_argument("--log", type=str, default=DEFAULT_LOG, help="留痕 jsonl 路径")
    args = ap.parse_args()

    result, code = flip(args.files, args.units, args.coupled, args.batch,
                        args.desc, args.dep_reason, args.force_serial, args.session_log,
                        args.baseline or None, dep_type=args.dep_type)

    if args.dep_type:
        result["dep_type"] = args.dep_type

    append_log(args.log, {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "inputs": {"files": args.files, "units": args.units,
                   "coupled": args.coupled, "batch": args.batch,
                   "dep_type": args.dep_type or None,
                   "dep_reason": args.dep_reason or None, "desc": args.desc or None},
        "session": os.environ.get("AGENT_SESSION_ID"),
        "verdict": result["verdict"],
        "throw": result.get("throw"),
        "mechanism": result.get("mechanism"),
        "force_serial": args.force_serial or None,
        "gate_declaration": result.get("gate_declaration"),
        "todo_gate": result.get("todo_gate"),
        "baseline": (result.get("baseline_gate") or {}).get("paths"),
        "probe_gate": result.get("probe_gate"),
    })

    result["logged"] = args.log
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.exit(code)


if __name__ == "__main__":
    main()
