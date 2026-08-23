#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plan_select.py — 扳手框架｜方案择优引擎 v2（三维度槽位原型池，2026-08-18 用户两次裁定定稿）

定义源（用户配置，冻结）：
  /Users/xujin/Downloads/扳手框架｜方案择优引擎.md（初版）
  + 2026-08-18 用户会话两次裁定：维度重构为三槽位原型池

核心设计（用户裁定原文语义固化）：
  1. 候选池固定 3 个维度槽位，每个维度生成一个方案，总共至多 3 个方案：
     - native_internal       执行载体维度 → 方案【原生内置最优】：全程模型原生内部实现
     - history_reuse         依赖组件维度 → 方案【历史复用最优】：历史有生成过、可复用已有成果
     - iteration_efficiency  变更范围维度 → 方案【迭代效率最优】：迭代生成步骤最少、修正次数最少
  2. 缺维过滤：某维度条件不满足（如历史没有可复用成果）→ 该方案生成不了 →
     直接过滤不给分、不参与排序——若判 0 分即成脏数据，会被"最低分最优"误选，
     可能输出"无方案"冒充最优，必须过滤而非计 0；
  3. 评分：有效方案分数 = S（真实执行步骤数，脚本直接计数），分数最低者为最优；
     同分按槽位编号小者优先（机械，无概率空间）；
  4. 判 A → 照抄 chosen 直接执行（不等用户确认）；
  5. 执行后双校验【运行态+产物】，失败 --rank N 顺位切换，上限=有效方案数，全败即终止；
  6. 禁止模型输出打分/自评词（机械拦截 → VIOLATION）；放弃探针；全部计算由本脚本执行。

退出码（四态，与 gate-switch 族一致）：
  0 = A          排序完成，照抄 chosen 方案直接执行
  2 = B          全部槽位被过滤（0 个有效方案）→ 禁止输出"无方案"，或 --rank 超界全败终止
  3 = CLARIFY    候选池无任何方案块（模型尚未按模板生成）
  4 = VIOLATION  未知维度词 / 槽位重复 / 方案块 >3 / 含模型自评打分词

用法：
  python3 plan_select.py --pool <候选池文件.md>
  python3 plan_select.py --pool <候选池文件.md> --rank 2   # 首位双校验失败后取下一顺位
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

DEFAULT_LOG = os.path.expanduser("~/.agents/logs/plan_select.jsonl")
ATTACHED_DISPATCH = os.path.expanduser("~/.dsh/xujin-scripts/skills/gate-switch/scripts/attached_dispatch.py")
ATTACHED_PLAN = os.path.expanduser("~/.dsh/xujin-scripts/skills/gate-switch/scripts/attached_plan.py")

EXIT_A, EXIT_B, EXIT_CLARIFY, EXIT_VIOLATION = 0, 2, 3, 4

# ---- 三维度槽位（用户裁定冻结，顺序即同分优先级）----
# key: (槽位编号, 维度名, 方案特质, 中文字面别名)
DIMENSIONS = {
    "native_internal":       (1, "执行载体维度", "原生内置最优：全程模型原生内部实现", "原生内置"),
    "history_reuse":         (2, "依赖组件维度", "历史复用最优：历史有生成过、可复用已有成果", "历史复用"),
    "iteration_efficiency":  (3, "变更范围维度", "迭代效率最优：迭代生成步骤最少、修正次数最少", "迭代效率"),
}
DIM_LITERALS = {}
for _k, (_i, _dn, _tr, _cn) in DIMENSIONS.items():
    DIM_LITERALS[_k] = _k
    DIM_LITERALS[_cn] = _k

# 模型自评/打分禁词（forbid_model_output_score）
SELF_SCORE_PATTERNS = [
    r"评分[:：]", r"打分[:：]", r"得分[:：]", r"可行性[:：]\s*(可行|不可行)",
    r"推荐方案", r"首选方案", r"我认为.*更[好快优]", r"综合来看.*应选",
]

STEP_RE = re.compile(r"^\s*\d+\s*[.、)]\s*\S")
PLAN_HEAD_RE = re.compile(r"^##\s*方案")
DIM_LINE_RE = re.compile(r"^dimension\s*[:：]", re.IGNORECASE)
# 2026-08-22 块I：NEXT-GATE 指令块 --files 机械提取用（文件路径字面量）
FILE_TOKEN_RE = re.compile(r"(?:~|/|[\w.-]+/)[\w./~()-]*\.(?:py|md|json|jsonl|sh|js|ts|yaml|yml)")


def parse_pool(text):
    """解析候选池 → (plans, violations)。plans: [{name, dim, steps, raw}]"""
    plans, violations = [], []
    current = None
    in_steps = False
    for line in text.splitlines():
        if PLAN_HEAD_RE.match(line):
            if current is not None:
                plans.append(current)
            current = {"name": line.lstrip("#").strip(), "dim": None, "steps": [], "verify": "", "raw": []}
            in_steps = False
            continue
        if current is None:
            continue
        current["raw"].append(line)
        stripped = line.strip()
        if DIM_LINE_RE.match(stripped):
            in_steps = False
            token = re.sub(r"^dimension\s*[:：]\s*", "", stripped, flags=re.IGNORECASE).strip()
            key = DIM_LITERALS.get(token)
            if key:
                current["dim"] = key
            else:
                violations.append(f"未知维度词「{token}」（{current['name']}）：维度严格字面匹配，仅允许 "
                                  f"{' / '.join(DIMENSIONS)}")
            continue
        if re.match(r"^steps\s*[:：]", stripped, re.IGNORECASE):
            in_steps = True
            continue
        if re.match(r"^verify\s*[:：]", stripped, re.IGNORECASE):
            in_steps = False
            current["verify"] = re.sub(r"^verify\s*[:：]\s*", "", stripped, flags=re.IGNORECASE).strip()
            continue
        if in_steps and STEP_RE.match(line):
            current["steps"].append(STEP_RE.match(line).group(0).strip())
    if current is not None:
        plans.append(current)
    for p in plans:
        if not p.get("verify"):
            violations.append(f"{p['name']} 缺 verify: 强制字段（客观失败判据）——判据必须池子生成时写死，禁止执行时临时发明")
    return plans, violations


def check_self_score(plans):
    hits = []
    for p in plans:
        body = "\n".join(p["raw"])
        for pat in SELF_SCORE_PATTERNS:
            if re.search(pat, body):
                hits.append(f"{p['name']} 含模型自评/打分禁词 /{pat}/")
    return hits


def log_event(record):
    os.makedirs(os.path.dirname(DEFAULT_LOG), exist_ok=True)
    record["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    with open(DEFAULT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def emit(verdict, exit_code, payload):
    out = {"verdict": verdict, "gate": "plan_select", "engine": "v2-dimension-slot", **payload}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    log_event({"verdict": verdict, **{k: v for k, v in payload.items() if k not in ("ranked", "filtered")}})
    sys.exit(exit_code)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True, help="候选方案池文件（模型按三维度槽位模板填充）")
    ap.add_argument("--rank", type=int, default=1, help="取排序第 N 顺位（首位双校验失败后递增）")
    ap.add_argument("--fail", type=int, default=0, help="宣告第 N 顺位双校验失败：留痕原因并直接输出下一顺位（纠错留痕唯一通道，2026-08-19 落地）")
    ap.add_argument("--reason", default="", help="--fail 必填：失败原因（照抄 verify 判据的实测结果）")
    args = ap.parse_args()

    if args.fail and not args.reason:
        emit("VIOLATION", EXIT_VIOLATION,
             {"violations": ["--fail 必须配 --reason：失败原因留痕是纠错机制存在的意义"],
              "directive": "重扳：--fail <rank> --reason \"<照抄 verify 判据的实测失败结果>\""})

    if not os.path.isfile(args.pool):
        emit("B", EXIT_B, {"violations": [f"候选池文件不存在: {args.pool}"],
                           "directive": "模型先按三维度槽位模板生成候选方案落盘，再重扳本开关"})

    text = open(args.pool, encoding="utf-8").read()
    plans, parse_violations = parse_pool(text)

    if not plans:
        emit("CLARIFY", EXIT_CLARIFY,
             {"violations": ["候选池无任何「## 方案」块：模型尚未按模板生成候选方案"],
              "directive": "按三维度槽位模板生成候选池（维度不满足的槽位直接不写该块）后重扳"})

    if len(plans) > 3:
        emit("VIOLATION", EXIT_VIOLATION,
             {"violations": [f"方案块数 {len(plans)} > 3：每维度至多 1 方案，总池固定 3 槽"],
              "directive": "裁剪至每槽 1 方案后重扳"})

    score_hits = check_self_score(plans)
    if score_hits:
        emit("VIOLATION", EXIT_VIOLATION,
             {"violations": score_hits,
              "directive": "模型仅填充客观实现路径，删除自评/打分词后重扳"})

    if parse_violations:
        emit("VIOLATION", EXIT_VIOLATION,
             {"violations": parse_violations,
              "directive": "修正 dimension: 行为三槽位字面词后重扳"})

    # 槽位重复检测
    seen = {}
    for p in plans:
        if p["dim"]:
            if p["dim"] in seen:
                emit("VIOLATION", EXIT_VIOLATION,
                     {"violations": [f"槽位「{p['dim']}」重复占用（{seen[p['dim']]} 与 {p['name']}）：每维度至多 1 方案"],
                      "directive": "每槽位保留 1 方案后重扳"})
            seen[p["dim"]] = p["name"]

    # 缺维过滤：0 步骤方案直接过滤不给分（防 0 分脏数据被"最低分最优"误选输出无方案）
    valid, filtered = [], []
    for p in plans:
        if p["dim"] is None:
            filtered.append({"name": p["name"], "reason": "缺 dimension 声明，无法归属槽位，过滤不给分"})
        elif len(p["steps"]) == 0:
            filtered.append({"name": p["name"], "dim": p["dim"],
                             "reason": "该维度条件不满足（0 个有效步骤），方案生成不了，直接过滤不给分"})
        else:
            slot, dim_name, trait, _ = DIMENSIONS[p["dim"]]
            valid.append({"name": p["name"], "dim": p["dim"], "dim_name": dim_name,
                          "trait": trait, "S": len(p["steps"]), "slot": slot})

    if not valid:
        emit("B", EXIT_B,
             {"violations": ["全部维度槽位被过滤（0 个有效方案）：禁止输出「无方案」冒充最优"],
              "filtered": filtered,
              "directive": "无可用执行路径：转 CLARIFY 向用户澄清需求或补充资源后重建候选池，禁止硬凑方案"})

    # 排序：S 升序（最低分最优），同分按槽位编号小者优先
    ranked = sorted(valid, key=lambda p: (p["S"], p["slot"]))
    for i, p in enumerate(ranked, 1):
        p["rank"] = i

    # --fail 纠错留痕通道：宣告第 N 顺位失败，留痕后取下一顺位
    if args.fail:
        failed = next((p for p in ranked if p["rank"] == args.fail), None)
        if failed is None:
            emit("VIOLATION", EXIT_VIOLATION,
                 {"violations": [f"--fail {args.fail} 无对应顺位（有效方案数 {len(ranked)}）"],
                  "directive": "核对 ranked 清单后重扳"})
        log_event({"event": "plan_fail", "pool": args.pool, "rank": failed["rank"],
                   "name": failed["name"], "dim": failed["dim"], "reason": args.reason})
        args.rank = args.fail + 1

    if args.rank > len(ranked):
        emit("B", EXIT_B,
             {"violations": [f"--rank {args.rank} 超出有效方案数 {len(ranked)}：全部候选已遍历"],
              "max_attempts": len(ranked),
              "directive": "已达最大尝试次数=有效方案总数，直接终止任务，禁止循环重试"})

    chosen = ranked[args.rank - 1]
    verify_map = {p["name"]: p.get("verify", "") for p in plans}
    chosen_verify = verify_map.get(chosen["name"], "")
    # ━━━ 附身量纲判定（2026-08-22 块N 混合模式方向1，REFORM-GATE 判A，升级块I 的
    # NEXT-GATE 文本提醒为脚本内机械附身）：chosen 输出后 subprocess 扳
    # attached_dispatch → dispatch_switch，--files 从 chosen 方案正文文件路径机械提取
    # （提取不了保守取步骤数），--units=步骤数 S；掷点结果原文并入输出，
    # VIOLATION 拒扳只作提醒不炸本判定；漏附身由 F10-PLAN-EXIT-NO-DISPATCH 后查。
    raw_map = {p["name"]: "\n".join(p["raw"]) for p in plans}
    chosen_body = raw_map.get(chosen["name"], "")
    n_files = len(set(FILE_TOKEN_RE.findall(chosen_body))) or chosen["S"]
    n_units = chosen["S"]
    try:
        ar = subprocess.run(
            [sys.executable, ATTACHED_DISPATCH, "--files", str(n_files),
             "--units", str(n_units), "--desc", chosen["name"], "--host", "plan_select"],
            capture_output=True, text=True, timeout=120)
        next_gate = json.loads(ar.stdout)
    except Exception as e:
        next_gate = {"attached": True, "host": "plan_select", "error": f"{type(e).__name__}: {e}",
                     "note": "附身调用失败不炸宿主判定，人工补扳 dispatch_switch"}
    attach_summary = (f"附身量纲判定已执行：files={n_files} units={n_units} → "
                      f"掷点 {next_gate.get('dispatch_throw') or next_gate.get('dispatch_verdict')}"
                      f"（{next_gate.get('note', '')}）")
    # ━━━ 强制连锁（2026-08-22 块Q v3 用户终裁）：有计划闸必跟收益闸——chosen 输出后
    # 附身 [ATTACHED-REFORM] 义务块（chosen 方案须过 reform_gate 判A才执行；
    # 用户直给方案单过收益闸路径不触发本链）；附身恒 exit 0 不炸本判定。
    try:
        rr = subprocess.run(
            [sys.executable, ATTACHED_PLAN, "--mode", "reform", "--host", "plan_select",
             "--desc", chosen["name"]],
            capture_output=True, text=True, timeout=60)
        attached_reform = json.loads(rr.stdout)
    except Exception as e:
        attached_reform = {"attached": True, "mode": "reform", "host": "plan_select",
                           "error": f"{type(e).__name__}: {e}",
                           "note": "附身调用失败不炸宿主判定，人工补过 reform_gate"}
    reform_summary = attached_reform.get(
        "declaration", "[ATTACHED-REFORM] chosen 方案须过 reform_gate 判A后才执行")
    emit("A", EXIT_A, {
        "ranked": [{k: p[k] for k in ("rank", "name", "dim", "dim_name", "trait", "S")}
                   for p in ranked],
        "filtered": filtered or None,
        "chosen": {"rank": chosen["rank"], "name": chosen["name"],
                   "dim": chosen["dim"], "trait": chosen["trait"], "S": chosen["S"],
                   "verify": chosen_verify},
        "next_gate": next_gate,
        "attached_reform": attached_reform,
        "max_attempts": len(ranked),
        "directive": (f"照抄直接执行第 {chosen['rank']} 顺位「{chosen['name']}」"
                      f"（{chosen['dim_name']}·{chosen['trait']}，S={chosen['S']} 最低分最优）；"
                      f"{reform_summary}；"
                      f"{attach_summary}；"
                      f"执行后双校验【运行态+产物】，失败判据照抄池内 verify：「{chosen_verify}」；"
                      f"失败必须 --fail {chosen['rank']} --reason \"<实测失败结果>\" 留痕并自动取下一顺位"
                      f"（禁止裸 --rank 跳顺不留痕），上限 {len(ranked)} 次全败即终止"),
    })


if __name__ == "__main__":
    main()
