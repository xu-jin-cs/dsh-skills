#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""todo_write_precheck.py — todo_write 前置附身闸（起始端变种，2026-08-25 用户裁定）。

对齐"todo_write 附身闸"：以前末尾追加完成步骤，本变种在【起始端】把 todo 清单可能要触发的规则扫一遍。
在调用 todo_write 前运行，机械提醒"调用前要做的事"。数据源=本次 todo 清单 + 会话已见台账。

提醒项：
  ① 清单含【新任务】 → 计划闸附身（attached_plan：新任务才触发、重发豁免）
  ② 出现【多任务/并行】→ 并行闸（PARALLEL-GATE：dispatch_switch + todo_write 先登记）
  ③ 新回合有【未完成 todo】→ 需重发 todo_write（面板 turn 级清零）
  ④ 若为【改造/机制/重构】→ 收益闸（REFORM-GATE）判 A 才动手

用法：
  python3 todo_write_precheck.py --tasks '["任务A","任务B"]' [--new-turn]

退出码：0=提醒与分流结论已输出（恒放行，不阻塞不打回）。

闸内扇出分流（2026-10-13 用户终裁：必定是闸·闸内判断·事前型·恒有下文不阻塞）：
  每次 TodoWrite 必经本闸——闸体内直接完成分流判定并输出执行拓扑结论：
  ① 分解判定（逐任务独立）：content 内嵌标注 [S]=不可分解 / [M]/[L]/[XL]=可分解；
     缺标注按不可分解处理并 notes 提示。混合合法，不要求全部可分解。
  ② 并行判定（仅 ≥2 任务触发）：读 content 内嵌 deps 标注（[M|deps:1,3] 引用清单序号），
     无依赖同 wave 并行、有依赖 wave 间串行；缺 deps 标注保守串行。
  输出=执行拓扑（wave 结构+分解标注），注入 additionalContext 随 TodoWrite 生效。
  终局许可（2026-10-13 用户终裁·关卡合并）：分流结论即放行，生成任务后一次判断完毕，
  符合并行直接并行、符合分解直接分解，禁止再增设关卡。
  销号规则（2026-10-13 用户终裁）：并行任务谁完成谁销号；decomposable 任务由母 agent
  等全部子 agent 事项合并后才销号；复合拓扑=多母并行（母间互不等待）×各母带子群聚合。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# 闸内分流判定件（task_fanout_plan.make_plan 函数级复用，判定逻辑唯一副本）；
# 导入失败按无分流段照章运行，不炸主流程
try:
    sys.path.insert(0, os.path.expanduser("~/.agents/skills/parallel-dispatch/scripts"))
    from task_fanout_plan import make_plan as _fanout_make_plan
except Exception:
    _fanout_make_plan = None

SEAL_DIR = os.environ.get(
    "TODO_SEAL_DIR",
    os.path.expanduser("~/.agents/logs/todo_seal"),
)
PRECHECK_LOG = os.environ.get(
    "TODO_PRECHECK_LOG",
    os.path.expanduser("~/.agents/logs/todo_write_precheck.jsonl"),
)

# content 内嵌标注：[S] / [M|deps:1,3] / [L|deps:]（deps 引用清单内 1 基序号；deps: 空=显式无依赖）
_ANNOTATION = re.compile(r"^\[(S|M|L|XL)(?:\|deps:([\d,\s]*))?\]")


def session_id() -> str:
    return os.environ.get("DSH_SESSION_ID", "").strip() or "default-session"


def load_seen(session: str) -> set:
    path = os.path.join(SEAL_DIR, f"{session}.jsonl")
    seen = set()
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    seen.add(json.loads(line)["task_key"])
                except Exception:
                    continue
    return seen


def normalize(t: str) -> str:
    return " ".join(t.strip().lower().split())


def parse_tasks(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            out = []
            for x in data:
                if isinstance(x, dict):
                    out.append(str(x.get("content") or x.get("title") or ""))
                else:
                    out.append(str(x))
            return [t for t in out if t]
    except Exception:
        pass
    # 纯文本：分号优先（hook 层以 "；" 连接 content，且 deps:1,2 内含逗号防误切）；
    # 无分号才按逗号切（逗号分隔场景请勿用 deps 内联列表）
    if "；" in raw or ";" in raw:
        parts = re.split(r"[；;]", raw)
    else:
        parts = re.split(r"[，,]", raw)
    return [t for t in parts if t.strip()]


def remind(text, task):
    print(f"  ☐ {text}")
    print(f"     ↳ {task}")


def parse_fanout_tasks(tasks: list) -> list:
    """content 内嵌标注解析：[S] / [M|deps:1,3] → [{id,size,deps}]（序号=清单内 1 基位置）。"""
    out = []
    for i, c in enumerate(tasks, 1):
        t = {"id": str(i)}
        m = _ANNOTATION.match(str(c).strip())
        if m:
            t["size"] = m.group(1)
            if m.group(2) is not None:  # deps: 空串 = 显式无依赖；缺失 = 未声明（保守串行）
                t["deps"] = [d.strip() for d in m.group(2).split(",") if d.strip()]
        out.append(t)
    return out


def emit_fanout_plan(tasks: list) -> None:
    """闸内分流判定：一行结论式输出（2026-10-13 P0 重构：去门槛去轰炸）。
    判定件缺失则跳过不炸；notes 仅异常级（成环/悬空/非法输入）。"""
    if _fanout_make_plan is None or not tasks:
        return
    plan = _fanout_make_plan(parse_fanout_tasks(tasks))
    waves = " → ".join(
        ("∥" if w["parallel"] else "") + str(w["tasks"]) for w in plan["waves"])
    decomp = [tid for tid, m in plan["breakdown"].items() if m == "decomposable"]
    line = f"  ⇒ 分流：{plan['mode']} width={plan['parallel_width']} | {waves}"
    if decomp:
        line += f" | 可分解:{decomp}（先拆再执行）"
    print(line)
    for n in plan["notes"]:
        print(f"     ⚠ {n}")


def main() -> int:
    ap = argparse.ArgumentParser(description="todo_write 前置提醒脚本")
    ap.add_argument("--tasks", required=True, help="本次 todo_write 任务清单（JSON 数组/逗号分隔）")
    ap.add_argument("--new-turn", action="store_true", help="标记为新回合（提示 todo 重发）")
    args = ap.parse_args()

    tasks = parse_tasks(args.tasks)
    session = session_id()
    seen = load_seen(session)
    keys = [normalize(t) for t in tasks]
    new_keys = [k for k in keys if k and k not in seen]

    print(f"todo_write 前置提醒（会话 {session}，共 {len(tasks)} 项任务）:")

    if new_keys:
        remind("清单含新任务 → 计划闸附身", "attached_plan 对新任务触发；重发（无新任务）豁免")
    else:
        print("  ✓ 无新任务（重发豁免，不重复附身计划闸）")

    # 并行/多任务启发：任务数>1 且含并行意图
    multi = any(k in " ".join(keys) for k in ("并行", "多任务", "扇出", "多个"))
    if len(keys) > 1 or multi:
        remind("多任务/并行 → 分流结论即放行", "按上方扇出拓扑直接执行；仅 width>5 或显式耦合才扳 dispatch_switch（重型场景）")

    if args.new_turn:
        remind("新回合有未完成 todo → 重发", "todo_write 面板 turn 级清零，重发同步面板")

    if any(k in " ".join(keys) for k in ("改造", "重构", "机制", "规则")):
        remind("改造/机制/重构 → 收益闸", "REFORM-GATE 判 A 才动手，禁以'用户指令'跳闸")

    # 闸内扇出分流判定（必定触发·恒有输出·不阻塞）
    emit_fanout_plan(tasks)

    print("提示：照抄并执行命中项后再调用 todo_write；判定禁止手写。")

    # 留痕（事后审计闸核验"todo_write 前已触发 precheck"用）
    try:
        os.makedirs(os.path.dirname(PRECHECK_LOG), exist_ok=True)
        import datetime
        with open(PRECHECK_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "session_id": session,
                "n_tasks": len(tasks),
                "n_new": len(new_keys),
                "new_turn": args.new_turn,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 留痕失败不阻断
    return 0


if __name__ == "__main__":
    sys.exit(main())
