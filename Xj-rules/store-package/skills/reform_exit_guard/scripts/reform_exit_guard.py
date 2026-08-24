#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reform_exit_guard.py — 请示出口闸（2026-08-17 用户裁定落地，REFORM-GATE 判 A）

裁定原文：改造方案判立即改/价值A 直接执行不问用户；「一直让我决定这个毛病一直没有改好」；
「这是扳手性质，不能用软提示词约束」。

双检查（证据源=旧版 会话 jsonl.zstd + gate_switch.jsonl，复用 dispatch_switch 证据源手法）：
  E1 请示句式黑名单：assistant 出口文本（content type=text，剥离「」/“”引用段后）命中
     请示句式（是否需要我/要不要我/是否执行/需要我继续/等你确认 等 + ？结尾）→ 违例。
     剥离引用段是为放行"引用违例样本做复盘分析"的合法讨论，只拦真实出口请示。
  E2 方案裸奔出口：assistant 文本含改造方案特征（改造方案/新增机制/建议改造/REFORM-GATE/
     立即改 等）时，gate_switch.jsonl 必须存在本会话时间窗内 spec=reform_gate 的掷点记录，
     缺失 → 方案未过收益框架即出口违例。

退出码：0=A 全过 / 2=B 违例清单（gate-switch script_exit 包装，expect=0）。
用法：python3 reform_exit_guard.py [--session-log <path>] [--gate-log <path>]
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime

SESSIONS_GLOB = os.path.expanduser("~/.kimi-code/sessions/*/*/session.jsonl.zstd")
DEFAULT_GATE_LOG = os.path.expanduser("~/.agents/logs/gate_switch.jsonl")

# E1 请示句式黑名单（用户口语症状短语，与 retro 条目 seq000 triggers 对齐）
PLEA_PHRASES = [
    "是否需要我", "要不要我", "要不要执行", "是否执行", "需要我继续",
    "需要我接着", "等你确认", "请您定夺", "你来决定", "是否继续",
    "需要确认吗", "可以吗？", "行吗？",
]
# E2 改造方案特征（出现即要求 reform_gate 掷点记录）
PROPOSAL_MARKERS = [
    "改造方案", "改造建议", "新增机制", "建议改造", "建议新增",
    "重构建议", "REFORM-GATE", "立即改", "扳手改造",
]
QUOTE_STRIP = re.compile(r"「[^」]*」|“[^”]*”|\"[^\"]*\"")


def resolve_session_log(explicit=None):
    if explicit:
        return explicit, "arg"
    env = os.environ.get("AGENT_SESSION_JSONL")
    if env and os.path.exists(env):
        return env, "env"
    cands = sorted(glob.glob(SESSIONS_GLOB), key=os.path.getmtime, reverse=True)
    return (cands[0], "glob") if cands else (None, None)


def read_session(path):
    """返回 (assistant_texts, session_start_iso)。解压失败返回 (None, None)。"""
    try:
        proc = subprocess.run(["zstd", "-dc", path], capture_output=True, timeout=120)
        raw = proc.stdout.decode("utf-8", "replace")
    except Exception:
        return None, None
    texts, start_iso = [], None
    for line in raw.splitlines():
        if '"type"' not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        t = obj.get("type")
        if t == "session" and start_iso is None:
            ca = obj.get("createdAt")
            if isinstance(ca, (int, float)):
                start_iso = datetime.fromtimestamp(ca / 1000).isoformat(timespec="seconds")
        elif t == "assistant/message":
            msg = obj.get("data", {}).get("message", {})
            for item in msg.get("content", []):
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
    if start_iso is None:  # 兜底：文件 mtime
        start_iso = datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds")
    return texts, start_iso


def check_plea(texts):
    """E1：剥离引用段后 grep 请示句式，返回违例清单。"""
    hits = []
    for idx, txt in enumerate(texts):
        stripped = QUOTE_STRIP.sub("", txt)
        for phrase in PLEA_PHRASES:
            for m in re.finditer(re.escape(phrase), stripped):
                tail = stripped[m.end():m.end() + 30]
                hits.append({
                    "code": "E1-PLEA",
                    "phrase": phrase,
                    "excerpt": stripped[max(0, m.start() - 20):m.end() + 20].replace("\n", " "),
                    "tail": tail.replace("\n", " "),
                })
    return hits


def check_bare_proposal(texts, start_iso, gate_log):
    """E2：有方案特征但会话窗口内无 reform_gate 掷点 → 违例。"""
    joined = "\n".join(QUOTE_STRIP.sub("", t) for t in texts)
    marker = next((m for m in PROPOSAL_MARKERS if m in joined), None)
    if not marker:
        return []
    if os.path.exists(gate_log):
        with open(gate_log, encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if "reform_gate" in str(rec.get("spec", "")) and str(rec.get("ts", "")) >= start_iso:
                    return []  # 窗口内已扳过收益闸
    return [{
        "code": "E2-BARE-PROPOSAL",
        "marker": marker,
        "detail": f"会话含改造方案特征「{marker}」但 {start_iso} 之后 gate_switch.jsonl 无 reform_gate 掷点记录 → 方案未过收益框架即出口",
    }]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-log", default=None)
    ap.add_argument("--gate-log", default=DEFAULT_GATE_LOG)
    args = ap.parse_args()

    path, source = resolve_session_log(args.session_log)
    if not path:
        print(json.dumps({"ok": False, "violations": [{"code": "E0-NO-SESSION",
              "detail": "无法定位会话日志（--session-log 显式指定后重跑）"}]}, ensure_ascii=False, indent=2))
        print("REFORM_EXIT_GUARD_RESULT: FAIL dims=['INFRA']")
        return 2

    texts, start_iso = read_session(path)
    if texts is None:
        print(json.dumps({"ok": False, "violations": [{"code": "E0-DECOMPRESS",
              "detail": f"会话日志解压失败: {path}"}]}, ensure_ascii=False, indent=2))
        print("REFORM_EXIT_GUARD_RESULT: FAIL dims=['INFRA']")
        return 2

    violations = check_plea(texts) + check_bare_proposal(texts, start_iso, args.gate_log)
    out = {
        "ok": not violations,
        "session_log": path,
        "log_source": source,
        "session_start": start_iso,
        "assistant_texts_scanned": len(texts),
        "violations": violations,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if violations:
        dims = sorted({v["code"].split("-")[0] for v in violations})
        print(f"REFORM_EXIT_GUARD_RESULT: FAIL dims={dims} count={len(violations)}")
        return 2
    print("REFORM_EXIT_GUARD_RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
