"""范式选型 CLI（引擎侧唯一实现）。

用法（也可经 `xj-engine paradigm ...` 调用）：
  python3 -m engine.paradigm.cli match --text "帮我查一下昨天入库多少条" [--json]
  python3 -m engine.paradigm.cli match --text "..." --override plan_execute --reason "人工判断"
  python3 -m engine.paradigm.cli validate --spec <模板.json> [--expected <paradigm>] [--force]
  python3 -m engine.paradigm.cli escape --declared react --facts '{"maxIterations":3,"loopPurpose":"reflection"}'

退出码：
  match   0=自动采信｜2=需人工复核｜1=强制人工指定（禁止自动流转）
  validate 0=全通过｜1=P0 阻断｜2=仅 P1 告警（等人工确认）
  escape  0=未逃逸｜1=检测到逃逸
"""
from __future__ import annotations

import argparse
import json
import sys

from . import capability, escape as escape_mod, team as team_mod, wiring as wiring_mod
from . import event_log, gates, matcher, samples, spec


def _print(obj, as_json: bool, human_lines: list[str]):
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        for ln in human_lines:
            print(ln)


def cmd_match(a) -> int:
    if a.skip and not spec.skip_selector():
        return _cmd_match_run(a, skipped=False)
    if a.skip:
        event_log.emit("input", inputHash=matcher.input_hash(a.text), text=a.text,
                       skipped=True, skipSwitch=True)
        _print({"skipped": True, "reason": "skip_paradigm_selector=1：已按开关跳过整套选型"},
               a.json, ["已按 skip_paradigm_selector 开关跳过选型（留痕 paradigm_selection.jsonl）"])
        return 0
    return _cmd_match_run(a, skipped=False)


def _cmd_match_run(a, skipped: bool) -> int:
    decision = matcher.decide(a.text, override=a.override, mode=a.mode,
                              use_cache=not a.no_cache,
                              embed_model=a.embed_model, skip=a.skip)
    event_log.emit("match", inputHash=decision["inputHash"], text=a.text,
                   mode=decision["mode"], scores=decision.get("scores"),
                   top=decision.get("top"), second=decision.get("second"),
                   confidence=decision.get("confidence"), cacheHit=decision.get("cacheHit"))
    decision_row = event_log.emit("decide", inputHash=decision["inputHash"],
                                  paradigm=decision["paradigm"],
                                  decision=decision["decision"],
                                  confidence=decision["confidence"],
                                  tie=decision.get("tie"),
                                  override=decision.get("override"),
                                  warnings=decision.get("warnings"))

    if a.override:
        samples.override_sample(a.text, decision, reason=a.reason)
        event_log.emit("override", inputHash=decision["inputHash"],
                       chosen=a.override, suggested=decision.get("suggested"),
                       reason=a.reason)

    code = {"auto": 0, "review": 2, "blocked": 1}[decision["decision"]]
    lines = [
        f"范式：{decision['paradigm']}（{decision['decision']}）置信度 {decision['confidence']}",
        (f"最高分 {decision.get('top')} / 次高分 {decision.get('second')}"
         f"（阈值 auto={decision['thresholds']['auto']} review={decision['thresholds']['review']}）"
         if decision.get("top") is not None else
         f"人工覆盖优先（阈值 auto={decision['thresholds']['auto']} review={decision['thresholds']['review']}）"),
        f"模式：{decision['mode']}" + ("（缓存命中）" if decision.get("cacheHit") else ""),
    ]
    if decision["decision"] == "review":
        lines.append("→ 低置信：需人工复核，可 --override 指定范式（覆盖样本自动回流）")
    elif decision["decision"] == "blocked":
        lines.append("→ 置信不足：阻断自动选择，必须人工 --override 指定范式")
    for w in decision.get("warnings") or []:
        lines.append(f"⚠ {w}")
    _print({**decision, "logRowId": decision_row["id"]}, a.json, lines)
    return code


def cmd_validate(a) -> int:
    asset = json.loads(open(a.spec, encoding="utf-8").read())
    result = gates.run(asset, expected=a.expected)
    event_log.emit("gate", spec=a.spec, expected=a.expected, code=result["code"],
                   verdict=result["verdict"], errors=result["errors"],
                   warnings=result["warnings"])
    if result["code"] == 1:
        samples.gate_failure(a.spec, result, a.expected)
    if result["code"] == 2 and a.force:
        samples.waiver(a.spec, result, operator=a.operator)
        result["forceReleased"] = True
        result["code"] = 0
        result["verdict"] = "PASS_FORCED"
    lines = [f"[{result['verdict']}] code={result['code']} {a.spec}",
             f"范式版本 {result['paradigmVersion']}"]
    lines += [f"P0 {e}" for e in result["errors"]]
    lines += [f"P1 {w}" for w in result["warnings"]]
    if result.get("forceReleased"):
        lines.append("→ P1 已人工强放，永久标记（paradigm_waivers.jsonl），运行时纳入观测")
    _print(result, a.json, lines)
    return result["code"]


def cmd_escape(a) -> int:
    facts = json.loads(a.facts)
    res = escape_mod.detect(a.declared, facts)
    event_log.emit("escape", declared=a.declared, facts=facts, escaped=res["escaped"])
    if res["escaped"]:
        samples.escape_alert(facts.get("assetKey", ""), a.declared, res)
    lines = [f"逃逸检测：{'命中' if res['escaped'] else '未命中'}（声明 {a.declared}）"]
    lines += [f"  {x['code']} {x['message']}" for x in res["alerts"]]
    if res["escaped"]:
        lines.append("  actions=" + ",".join(res["actions"]) + "（暂停/推送指导大师/回流样本由平台执行）")
    _print(res, a.json, lines)
    return 1 if res["escaped"] else 0


def cmd_capability(a) -> int:
    row = capability.build(a.paradigm, a.role)
    event_log.emit("capability", paradigm=a.paradigm, role=a.role,
                   profile=row.get("capabilityProfile"), conflicts=row.get("conflicts"))
    lines = [f"能力 profile：{a.paradigm} × {a.role} → {'OK' if row['ok'] else 'FAIL'}"]
    p = row["capabilityProfile"]
    lines.append(f"  plan={p['plan']['mode']}({p['plan']['source']}) "
                 f"tool={p['tool']['mode']}({p['tool']['source']}) "
                 f"memory={p['memory']['enabledTiers']} persist={p['memory']['persist']} "
                 f"reflect={p['reflect']['mode']} loop≤{p['reflect']['loop']['maxIterations']}")
    lines += [f"  ✗ {c}" for c in row["conflicts"]]
    _print(row, a.json, lines)
    return 0 if row["ok"] else 1


def cmd_wiring(a) -> int:
    asset = json.loads(open(a.spec, encoding="utf-8").read())
    res = wiring_mod.check(asset, strict=a.strict)
    event_log.emit("wiring", spec=a.spec, code=res["code"], verdict=res["verdict"],
                   blocking=res["blocking"], degradable=res["degradable"])
    lines = [f"[{res['verdict']}] code={res['code']} strict={a.strict} {a.spec}",
             f"阻断类缺口 {res['blocking']}｜可降级缺口 {res['degradable']}"]
    lines += [f"  {g['field']}: {g['status']}（{g['consumer']}）" for g in res["gaps"]]
    _print(res, a.json, lines)
    return res["code"]


def cmd_team(a) -> int:
    asset = json.loads(open(a.spec, encoding="utf-8").read())
    res = team_mod.analyze(asset)
    event_log.emit("team", spec=a.spec, path=res["path"], code=res["code"],
                   verdict=res["verdict"], agents=res["agents"]["agentCount"],
                   hasParallel=res["parallel"]["hasParallel"],
                   precheck=res["precheck"]["decision"],
                   exceptions=[e["type"] for e in res["exceptions"]])
    lines = [f"[{res['verdict']}] code={res['code']} path={res['path']} {a.spec}",
             f"角色数 {res['agents']['agentCount']} {res['agents']['distinctAgentIds']}"
             f"｜并行 {res['parallel']['hasParallel']}"
             f"（agent 组 {len(res['parallel']['parallelGroups'])} / task 组 {len(res['parallel']['taskParallelGroups'])}）",
             f"并行闸预判 {res['precheck']['decision']}（{', '.join(res['precheck']['reasons'])}）"]
    lines += [f"  ✗ {e['type']}: {e['message']}" for e in res["exceptions"] if e["level"] == "block"]
    lines += [f"  ⚠ {e['type']}: {e['message']}" for e in res["exceptions"] if e["level"] != "block"]
    _print(res, a.json, lines)
    return res["code"]


class _ArgParser(argparse.ArgumentParser):
    """入参错误 → exit 3；2 专用于 match 的"需人工复核"，禁止 argparse 默认 exit 2 撞码。"""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"FATAL 入参错误：{message}", file=sys.stderr)
        raise SystemExit(3)


def main(argv=None) -> int:
    ap = _ArgParser(prog="xj-engine paradigm", description="范式选型（唯一实现）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("match", help="自然语言 → 范式 + 置信三档")
    m.add_argument("--text", required=True)
    m.add_argument("--override", default="", help="人工指定范式（优先于自动打分）")
    m.add_argument("--reason", default="", help="人工覆盖原因（永久留痕）")
    m.add_argument("--mode", choices=["lexical", "semantic"], default=None)
    m.add_argument("--embed-model", default=None, help="本地嵌入模型路径（semantic 模式）")
    m.add_argument("--no-cache", action="store_true")
    m.add_argument("--skip", action="store_true", help="显式跳过（受 skip_paradigm_selector 开关约束）")
    m.add_argument("--json", action="store_true")
    m.set_defaults(func=cmd_match)

    v = sub.add_parser("validate", help="模板三门校验（0/1/2）")
    v.add_argument("--spec", required=True)
    v.add_argument("--expected", default=None, help="选型结果范式（用于一致性门）")
    v.add_argument("--force", action="store_true", help="P1 告警人工强放（P0 不可强放）")
    v.add_argument("--operator", default="manual")
    v.add_argument("--json", action="store_true")
    v.set_defaults(func=cmd_validate)

    e = sub.add_parser("escape", help="事后逃逸检测")
    e.add_argument("--declared", required=True)
    e.add_argument("--facts", required=True, help='JSON：{"maxIterations":..,"loopPurpose":..,"distinctAgentId":..}')
    e.add_argument("--json", action="store_true")
    e.set_defaults(func=cmd_escape)

    c = sub.add_parser("capability", help="矩阵推导：范式 × 任务角色 → 四能力 profile")
    c.add_argument("--paradigm", required=True)
    c.add_argument("--role", required=True)
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_capability)

    w = sub.add_parser("wiring", help="运行时接线自检（报告式；--strict 才阻断）")
    w.add_argument("--spec", required=True)
    w.add_argument("--strict", action="store_true")
    w.add_argument("--json", action="store_true")
    w.set_defaults(func=cmd_wiring)

    t = sub.add_parser("team", help="单多决策：数角色/看并行/看契约/三件套/路径/异常")
    t.add_argument("--spec", required=True)
    t.add_argument("--json", action="store_true")
    t.set_defaults(func=cmd_team)

    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
