#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZCode UserPromptSubmit hook：闸触发铁律机械化（2026-08-29 v1；
2026-09-01 v2 对齐 dsh-trigger-auto 通道① v3 行为（REFORM zcode_gate_auto_align 判A）。

读 stdin 钩子输入（含 prompt），跑 trigger_signal_scan.py：
- HITS（L0 硬命中非空）→ 完整调试面板（层位计数行 + 逐命中 must_pull + soft 仅 id
  列表一行 + [TRIGGER-AUTO-CLEARED] 收尾声明），照抄 dsh v3 格式；
- 非 HITS（NO-HIT / 纯成分命中）→ 常显精简行（扫描在岗状态，对齐 dsh v3
  "调试板常显"设计：静默导致长期不可见）；
- 扫描失败 → 静默 exit 0 + 留痕 zcode_hooks.log（不拖垮主流程）。
同时写 turn 状态文件（query_weld_hook 的 turnStart 依据）。
"""
import datetime
import json
import os
import subprocess
import sys

SCAN = os.path.expanduser(
    "~/.agents/skills/gate-switch/scripts/trigger_signal_scan.py")
LOG = os.path.expanduser("~/.agents/logs/zcode_hooks.log")
STATE = os.path.expanduser("~/.agents/logs/zcode_hooks_state.json")


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def stamp_turn(payload):
    """写 turn 边界状态（query_weld 的 turnStart 依据）。"""
    try:
        state = {}
        if os.path.isfile(STATE):
            state = json.load(open(STATE, encoding="utf-8"))
        state["last_prompt_ts"] = datetime.datetime.now(
            datetime.timezone.utc).isoformat()
        sid = payload.get("session_id") or payload.get("sessionId") or ""
        if sid:
            state["session_id"] = sid
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def full_panel(hits, component_hits, soft):
    """完整调试面板（对齐 dsh triggerDeclarationBlock 格式）。"""
    lines = ["[TRIGGER-AUTO 调试面板·ZCode]"]
    lines.append("命中层位: 插件通道①(UserPromptSubmit→scan) ｜ L0硬命中:%d ｜ "
                 "L1成分:%d ｜ L2软:%d" % (len(hits), len(component_hits), len(soft)))
    for hit in hits:
        lines.append("├─ %s（%s）" % (hit.get("id"), hit.get("name")))
        matched = " ; ".join(hit.get("matched") or [])
        if matched:
            lines.append("│   命中词: %s" % matched)
        for pull in hit.get("must_pull") or []:
            lines.append("│   must_pull: %s" % pull)
    if soft:
        lines.append("├─ L2 软层提醒（keyword 不可判信号，留软层自查）: %s"
                     % " / ".join(s.get("id", "?") for s in soft))
    ids = " ".join(h.get("id", "?") for h in hits)
    lines.append("└─ 逐条扳完 must_pull 后回复首行声明: [TRIGGER-AUTO-CLEARED] " + ids)
    return "\n".join(lines)


def compact_line(hits, component_hits, soft):
    """常显精简行（对齐 dsh compactStatusLine：NO-HIT/纯成分也注入在岗状态）。"""
    text = ("[TRIGGER-AUTO] 扫描在岗 ｜ L0硬:%d ｜ L1成分:%d ｜ L2软:%d ｜ 未命中"
            % (len(hits), len(component_hits), len(soft)))
    if component_hits:
        detail = " ".join(str(c) for c in component_hits[:3])
        text += " ｜ 成分命中: %s" % detail
    return text


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    prompt = ""
    for key in ("prompt", "user_prompt", "text", "input"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            prompt = v
            break
    if not prompt:
        return 0
    stamp_turn(payload)
    try:
        proc = subprocess.run(
            ["python3", SCAN, "--text", prompt],
            capture_output=True, timeout=20, text=True)
        data = json.loads(proc.stdout)
    except Exception as e:
        log("prompt_scan_hook ERROR: %r" % e)
        return 0
    hits = data.get("hits") or []
    component_hits = data.get("component_hits") or []
    soft = data.get("soft_reminders") or []
    if data.get("verdict") == "HITS" and hits:
        text = full_panel(hits, component_hits, soft)
    else:
        text = compact_line(hits, component_hits, soft)
    print(json.dumps({"additionalContext": text}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
