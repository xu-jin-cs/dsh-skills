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

from . import escape as escape_mod
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="xj-engine paradigm", description="范式选型（唯一实现）")
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

    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
