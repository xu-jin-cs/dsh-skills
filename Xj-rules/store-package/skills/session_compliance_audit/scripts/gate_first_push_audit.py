#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_first_push_audit.py — L2 开关"第一推动"事后审计闸（2026-08-17 REFORM-GATE 判立即改落地）

短板A改造：无钩子环境下"何时该扳开关"纯靠模型自觉，不扳不留痕、违规隐身。
本闸克隆 reform_exit_guard.py 骨架，扫 旧版 会话 jsonl + 各开关留痕 jsonl，
检测"模式信号在、对应开关留痕缺"的不对称（事后必被查 → 倒逼事前自觉扳）：

  F1 多任务扇出未扳 dispatch_switch：会话 ≥2 次 subagent/subagent_fork/workflow
     tool/call，但窗口内 dispatch_switch.jsonl 无掷点记录 → 违例
  F2 改造方案未过 REFORM-GATE 裸奔出口：assistant 文本含方案特征词，但窗口内
     gate_switch.jsonl 无 spec=reform_gate 掷点 → 违例（= reform_exit_guard E2 同源）
  F3 复盘触发词命中未走 GENERATE 准入：user 文本命中触发词表（源自
     dispatcher_generate_config.json fixed_phrases），但窗口内无
     spec=retro_generate_token 掷点 → 违例
  F4 掷点 A 后未真扇出：窗口内 dispatch_switch 有 throw=A 留痕，但会话无任何
     subagent 族 tool/call → 违例（只评估不执行=故意串行化的机械代理信号）
  F6 retro-match 该跑没跑：用户消息命中复盘/流程触发词，但窗口内
     _active_match.md mtime 未更新 → 违例（该文件每次运行无条件重写，
     mtime 判据覆盖"跑了但无命中"；retro 消费链第一环机械兜底）
  F7 起手式缺失（2026-08-17 REFORM-GATE 判 A，规则制定者自我盲区实证：
     4 条问卷提交未开清单/未掷点/串行无理由，对 F1-F6 全隐身）：
     F7a 单回合工具链 ≥4 且无 todo/write → 长链任务未开清单起手式；
     F7b 同形命令跨 ≥3 回合重复，重复窗口内无 todo/write 且会话窗口内
     无 dispatch_switch 掷点 → 批量任务零起手式
  F8 查询闸漏扳后查（2026-08-20 任务书 D2，REFORM-GATE 判 A）：用户消息命中
     dual-gates 声明闸 2 字词根白名单（import 复用同一真源 match_whitelist），
     但窗口内 dual_gates_audit.jsonl 无 declaration_gate_* 留痕 → 评估/取证
     未过查询闸
  F10 方案判A出口漏扳子分身闸（2026-08-22 块I 用户指令焊死，REFORM-GATE 判A）：
     reform_gate/plan_select 判A留痕出现后，同会话后续窗口（至会话末或下一判A前）
     dispatch_switch.jsonl 无扳动留痕 → 违例 F10-PLAN-EXIT-NO-DISPATCH
  F11 漏判捕获/漏例回收机（2026-08-22 块L 方向1，REFORM-GATE 判A，渐近 99% 唯一
     可持续路径）：逐次扳闸留痕（gate_switch.jsonl + dispatch_switch.jsonl）对比
     其前最近一次 trigger_signal_scan 命中集（hit_ids ∪ component_hit_ids），
     扳了闸但对应信号未命中 → 漏例落盘 miss_cases.jsonl（输入摘要+应中信号+实扳闸），
     复盘着陆时逐条回收为新成分；豁免：用户输入显式点名 spec 文件名（直接指令扳闸）

纯语义情形（"这段输入算不算多任务"）不进违例清单，只认机械代理信号。
退出码：0=A 全过 / 2=B 违例清单（gate-switch script_exit 包装，expect=0）。
用法：python3 gate_first_push_audit.py [--session-log <path>]
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
DISPATCH_LOG = os.path.expanduser("~/.agents/logs/dispatch_switch.jsonl")
GATE_LOG = os.path.expanduser("~/.agents/logs/gate_switch.jsonl")
RETRO_CONFIG = os.path.expanduser("~/.agents/retro-registry/dispatcher_generate_config.json")
RETRO_MATCH_OUTPUT = os.path.expanduser("~/.agents/retro-registry/runtime/_active_match.md")
TRIGGER_SCAN_LOG = os.path.expanduser("~/.agents/logs/trigger_signal_scan.jsonl")
PLAN_SELECT_LOG = os.path.expanduser("~/.agents/logs/plan_select.jsonl")
POST_GATE_LOG = os.path.expanduser("~/.agents/logs/post_gate_audit.jsonl")
RULE_CONFLICT_LOG = os.path.expanduser("~/.agents/logs/rule_conflict_adjudication.jsonl")
MISS_CASES_LOG = os.path.expanduser("~/.agents/logs/miss_cases.jsonl")

# F11 漏判捕获映射表（2026-08-22 块L 硬编码）：闸 spec 关键词 ↔ 应中信号 id
SPEC_SIGNAL_MAP = {
    "reform_gate": "S-REFORM",
    "problem_gate": "S-PROBLEM-GATE",
    "stat_citation": "S-STAT-CITE",
    "danger_cmd_gate": "S-DANGER-CMD",
    "retro_generate_token": "S-RETRO-WORDS",
    "perf_no_sleep": "S-PERF",
}
DISPATCH_SIGNAL = "SOFT-MULTITASK"  # dispatch_switch.jsonl 扳动 ↔ 成分信号

SUBAGENT_TOOLS = {"subagent", "subagent_fork", "workflow"}
PROPOSAL_MARKERS = [
    "改造方案", "改造建议", "新增机制", "建议改造", "建议新增",
    "重构建议", "REFORM-GATE", "立即改", "扳手改造",
]
QUOTE_STRIP = re.compile(r"「[^」]*」|“[^”]*”|\"[^\"]*\"")


def load_retro_triggers():
    try:
        with open(RETRO_CONFIG, encoding="utf-8") as f:
            return json.load(f)["trigger_config"]["fixed_phrases"]
    except Exception:
        return ["复盘", "验收通过", "项目完成", "收尾", "结项", "完工", "交付", "关闭"]


def resolve_session_log(explicit=None):
    if explicit:
        return explicit, "arg"
    env = os.environ.get("AGENT_SESSION_JSONL")
    if env and os.path.exists(env):
        return env, "env"
    cands = sorted(glob.glob(SESSIONS_GLOB), key=os.path.getmtime, reverse=True)
    return (cands[0], "glob") if cands else (None, None)


def read_session(path):
    """返回 (events, assistant_texts, user_texts, bash_cmds, subagent_calls, start_iso, end_iso,
    user_msgs_timed[(iso,text)]——F11 漏判捕获的输入原文摘要与豁免判定用）。"""
    try:
        proc = subprocess.run(["zstd", "-dc", path], capture_output=True, timeout=120)
        raw = proc.stdout.decode("utf-8", "replace")
    except Exception:
        return None
    events, a_texts, u_texts, bash_cmds, sub_calls = [], [], [], [], 0
    u_msgs_timed = []
    start_iso = None
    max_ms = None
    for line in raw.splitlines():
        if '"type"' not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        t, data = obj.get("type"), obj.get("data", {})
        events.append((t, data))
        ms = obj.get("time")
        if isinstance(ms, (int, float)) and (max_ms is None or ms > max_ms):
            max_ms = ms
        if t == "session" and start_iso is None:
            ca = obj.get("createdAt")
            if isinstance(ca, (int, float)):
                start_iso = datetime.fromtimestamp(ca / 1000).isoformat(timespec="seconds")
        elif t == "assistant/message":
            for item in data.get("message", {}).get("content", []):
                if isinstance(item, dict) and item.get("type") == "text":
                    a_texts.append(item.get("text", ""))
        elif t == "user/message":
            # 2026-08-20 修复提取断链：用户消息实为 data.content（list），原读
            # data.message.content 恒为空 → F3/F6 用户侧触发从未真实检出（关键词桩化）。
            # source.kind 过滤注入文本（agent-instructions/plugin/skill-catalog），
            # 只认真实用户输入，防 AGENTS.md 注入文本里的触发词全会话误报。
            src = data.get("source", {})
            if isinstance(src, dict) and src.get("kind") not in (None, "user"):
                continue
            content = data.get("content", data.get("message", {}).get("content", ""))
            msg_iso = (datetime.fromtimestamp(ms / 1000).isoformat(timespec="seconds")
                       if isinstance(ms, (int, float)) else None)
            if isinstance(content, str):
                u_texts.append(content)
                u_msgs_timed.append((msg_iso, content))
            elif isinstance(content, list):
                for i in content:
                    if isinstance(i, dict) and i.get("type") == "text":
                        u_texts.append(i.get("text", ""))
                        u_msgs_timed.append((msg_iso, i.get("text", "")))
        elif t == "tool/call":
            name = data.get("name", "")
            if name in SUBAGENT_TOOLS:
                sub_calls += 1
            if name == "bash":
                try:
                    args = json.loads(data.get("arguments", "{}"))
                    bash_cmds.append(args.get("command", ""))
                except Exception:
                    pass
    if start_iso is None:
        start_iso = datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds")
    end_iso = (datetime.fromtimestamp(max_ms / 1000).isoformat(timespec="seconds")
               if max_ms is not None else
               datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds"))
    return events, a_texts, u_texts, bash_cmds, sub_calls, start_iso, end_iso, u_msgs_timed


def log_has_record(path, start_iso, predicate):
    """窗口内留痕 jsonl 是否存在满足 predicate 的记录。"""
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if str(rec.get("ts", "")) >= start_iso and predicate(rec):
                return True
    return False


def session_id_of_log(path):
    """从会话日志路径提取会话 id：.../session-<id>/session.jsonl.zstd → session-<id>。"""
    return os.path.basename(os.path.dirname(path))


def same_session(rec, sid):
    """留痕归属判定（2026-08-19 F4 跨会话污染修复，REFORM-GATE 判 A）：
    有 session 字段的记录必须等于当前会话 id；无 session 字段的历史记录
    按时间窗原样计入（向后兼容）。"""
    return not rec.get("session") or rec.get("session") == sid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-log", default=None)
    args = ap.parse_args()

    path, source = resolve_session_log(args.session_log)
    if not path:
        print(json.dumps({"ok": False, "violations": [{"code": "F0-NO-SESSION",
              "detail": "无法定位会话日志（--session-log 显式指定后重跑）"}]}, ensure_ascii=False, indent=2))
        print("FIRST_PUSH_AUDIT_RESULT: FAIL dims=['INFRA']")
        return 2

    parsed = read_session(path)
    if parsed is None:
        print(json.dumps({"ok": False, "violations": [{"code": "F0-DECOMPRESS",
              "detail": f"会话日志解压失败: {path}"}]}, ensure_ascii=False, indent=2))
        print("FIRST_PUSH_AUDIT_RESULT: FAIL dims=['INFRA']")
        return 2

    events, a_texts, u_texts, bash_cmds, sub_calls, start_iso, end_iso, u_msgs_timed = parsed
    violations, warnings = [], []
    sid = session_id_of_log(path)

    # F1 扇出未扳开关（2026-08-19 起按 session 过滤，防并发会话留痕掩盖/污染）
    if sub_calls >= 2 and not log_has_record(DISPATCH_LOG, start_iso, lambda r: same_session(r, sid)):
        violations.append({"code": "F1-FANOUT-NO-SWITCH",
            "detail": f"会话 {sub_calls} 次 subagent 族扇出，但窗口内 dispatch_switch.jsonl 无掷点记录 → 多任务未扳开关"})

    # F2 方案裸奔（剥离引用段后判定，与 reform_exit_guard E2 同源）
    joined = "\n".join(QUOTE_STRIP.sub("", t) for t in a_texts)
    marker = next((m for m in PROPOSAL_MARKERS if m in joined), None)
    if marker and not log_has_record(GATE_LOG, start_iso, lambda r: "reform_gate" in str(r.get("spec", ""))):
        violations.append({"code": "F2-BARE-PROPOSAL",
            "detail": f"assistant 文本含方案特征「{marker}」但窗口内无 reform_gate 掷点 → 方案未过收益框架"})

    # F3 复盘触发未走 GENERATE 准入
    triggers = load_retro_triggers()
    u_joined = "\n".join(u_texts)
    hit = next((w for w in triggers if w in u_joined), None)
    if hit and not log_has_record(GATE_LOG, start_iso, lambda r: "retro_generate_token" in str(r.get("spec", ""))):
        violations.append({"code": "F3-RETRO-NO-TOKEN",
            "detail": f"用户消息命中复盘触发词「{hit}」但窗口内无 retro_generate_token 掷点 → 复盘未走 GENERATE 准入"})

    # F4 掷点 A 未真扇出（2026-08-19 起按 session 过滤，防并发会话掷点 A 污染本窗口）
    if log_has_record(DISPATCH_LOG, start_iso, lambda r: r.get("throw") == "A" and same_session(r, sid)) and sub_calls == 0:
        violations.append({"code": "F4-THROW-A-NO-FANOUT",
            "detail": "窗口内有 dispatch_switch 掷点 A 留痕但会话零 subagent 族调用 → 只评估不执行（故意串行化代理信号）"})

    # F6 retro-match 该跑没跑：触发词命中但窗口内 retro-match 未运行
    # （_active_match.md 每次运行无条件重写——retro-match.sh line 440，含无命中空跑——
    #   故 mtime≥会话开始 = 本会话跑过；与 F3 共用触发词命中 hit，义务同源）
    if hit and not (
        os.path.exists(RETRO_MATCH_OUTPUT)
        and datetime.fromtimestamp(os.path.getmtime(RETRO_MATCH_OUTPUT)).isoformat(timespec="seconds") >= start_iso
    ):
        violations.append({"code": "F6-RETRO-MATCH-NOT-RUN",
            "detail": f"用户消息命中 retro 触发词「{hit}」但窗口内 _active_match.md 未更新 → retro-match.sh 该跑没跑（消费链第一环断）"})

    # F7 起手式缺失（2026-08-17 REFORM-GATE 判 A，规则制定者自我盲区实证：
    # 4 条问卷提交未开清单/未掷点/串行无理由，对 F1-F6 全隐身）
    # F7a 单回合工具链 ≥4 且无 todo/write；F7b 同形命令跨 ≥3 回合重复，
    #     重复窗口内无 todo/write 且会话窗口内无 dispatch_switch 掷点
    turns_calls, turns_bash_sig, turns_todo = {}, {}, set()
    cur = None
    for t, data in events:
        if t == "turn/start":
            cur = data.get("turn")
        elif t == "tool/call" and cur is not None:
            name = data.get("name", "")
            turns_calls.setdefault(cur, []).append(name)
            if name == "bash":
                try:
                    cmd = json.loads(data.get("arguments", "{}")).get("command", "")
                    m = re.findall(r"[\w./~-]+\.py", cmd)
                    sig = m[-1] if m else " ".join(cmd.split()[:2])
                    turns_bash_sig.setdefault(cur, []).append(sig)
                except Exception:
                    pass
        elif t == "todo/write" and cur is not None:
            turns_todo.add(cur)
    f7a = [tn for tn, calls in turns_calls.items() if len(calls) >= 4 and tn not in turns_todo]
    if f7a:
        violations.append({"code": "F7a-LONGCHAIN-NO-TODO",
            "detail": f"回合 {f7a[:5]} 工具调用≥4 但无 todo/write → 长链任务未开清单起手式"})
    sig_turns = {}
    for tn, sigs in turns_bash_sig.items():
        for s in set(sigs):
            sig_turns.setdefault(s, []).append(tn)
    has_dispatch = log_has_record(DISPATCH_LOG, start_iso, lambda r: True)
    for sig, tns in sig_turns.items():
        tns = sorted(set(tns))
        if len(tns) < 3:
            continue
        if any(tn in turns_todo for tn in range(tns[0], tns[-1] + 1)):
            continue
        if not has_dispatch:
            violations.append({"code": "F7b-SERIAL-BATCH-NO-SWITCH",
                "detail": f"命令模式 {os.path.basename(sig)} 跨 {len(tns)} 个回合重复（turn {tns}），窗口内无 todo/write 且会话无 dispatch_switch 掷点 → 批量任务零起手式"})

    # F8 查询闸漏扳后查（2026-08-20 REFORM-GATE 判 A，任务书 D2 落地）：
    # 用户消息命中声明闸 2 字词根白名单，但窗口内 dual_gates_audit.jsonl 无
    # declaration_gate_* 事件 → 评估/取证类任务未过查询闸（08-19 评估会话
    # 血泪教训第 1 条"评估/取证必过查询闸"的机械兜底）。
    # 词根与匹配函数复用 dual_gates.py 同一真源（import 复用，禁双副本漂移）；
    # 留痕判定仿 F6：declare 每次运行无条件写审计事件，timestamp≥会话开始=跑过。
    q_hit = None
    try:
        import importlib.util
        _dg_path = os.path.expanduser("~/.agents/skills/dual-gates/scripts/dual_gates.py")
        _dg_spec = importlib.util.spec_from_file_location("dual_gates", _dg_path)
        _dg = importlib.util.module_from_spec(_dg_spec)
        _dg_spec.loader.exec_module(_dg)
        for _t in u_texts:
            _hits = _dg.match_whitelist(_t)
            if _hits:
                q_hit = _hits[0]
                break
    except Exception:
        q_hit = None
    if q_hit:
        # 注意：不能复用 log_has_record——其预筛硬编码 rec["ts"]，而
        # dual_gates_audit.jsonl 时间字段为 timestamp，预筛恒 False 会冤判。
        # 窗口取 [start_iso, end_iso] 闭区间：会话结束后补跑的 declare 不为旧会话开脱。
        dg_log = os.path.expanduser("~/.agents/logs/dual_gates_audit.jsonl")
        declared = False
        if os.path.exists(dg_log):
            with open(dg_log, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if not str(rec.get("event", "")).startswith("declaration_gate"):
                        continue
                    ts19 = str(rec.get("timestamp", ""))[:19]
                    if start_iso[:19] <= ts19 <= end_iso[:19]:
                        declared = True
                        break
        if not declared:
            violations.append({"code": "F8-QUERY-GATE-NOT-RUN",
                "detail": f"用户消息命中声明闸词根「{q_hit}」但窗口内 dual_gates_audit.jsonl 无 declare 留痕 → 评估/取证未过查询闸"})

    # ━━━ F9-F12 留痕消费链接链检查（2026-08-20 强生成弱消费审计 AGT-001/005/006/007 落地）━━━
    stats = {}

    # F9 唯一肌肉记忆漏扫（AGT-001）：trigger_signal_scan 要求「任何用户输入到达即跑」，
    # 会话有真实用户输入但窗口内零扫描留痕 → 肌肉记忆断链
    scan_count = 0
    if os.path.exists(TRIGGER_SCAN_LOG):
        with open(TRIGGER_SCAN_LOG, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                ts19 = str(rec.get("ts", ""))[:19]
                if start_iso[:19] <= ts19 <= end_iso[:19]:
                    scan_count += 1
    stats["trigger_signal_scan_in_window"] = scan_count
    stats["user_messages"] = len(u_texts)
    if u_texts and scan_count == 0:
        violations.append({"code": "F9-SIGNAL-SCAN-NOT-RUN",
            "detail": f"会话有 {len(u_texts)} 条真实用户输入但窗口内 trigger_signal_scan.jsonl 零留痕 → 「唯一肌肉记忆」未扳（漏扫率消费方本检查）"})

    # F10 plan_select 质量信号消费（AGT-005）：plan_fail/B/VIOLATION 占比是方案择优引擎
    # 唯一质量反馈，在此统计并超阈值告警（原声称「纳入复盘审计」无机制承接，本检查补链）
    ps_total = ps_fail = 0
    if os.path.exists(PLAN_SELECT_LOG):
        with open(PLAN_SELECT_LOG, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                v = str(rec.get("verdict", ""))
                if not v:
                    continue
                ps_total += 1
                if v in ("B", "VIOLATION") or "plan_fail" in str(rec.get("event", "")):
                    ps_fail += 1
    stats["plan_select"] = {"total": ps_total, "fail": ps_fail}
    if ps_total >= 4 and ps_fail / ps_total > 0.5:
        warnings.append({"code": "F10-PLAN-SELECT-HIGH-FAIL",
            "detail": f"plan_select 失败/切换率 {ps_fail}/{ps_total}={ps_fail/ps_total:.0%} >50% → 方案择优引擎质量信号异常，进复盘议题"})

    # F11 post_gate_audit 字段消费（AGT-006）：anchor_invalid_rate 契约字段在此统计
    pga = []
    if os.path.exists(POST_GATE_LOG):
        with open(POST_GATE_LOG, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec.get("anchor_invalid_rate"), (int, float)):
                    pga.append(rec["anchor_invalid_rate"])
    if pga:
        recent = pga[-20:]
        avg = sum(recent) / len(recent)
        stats["post_gate_audit"] = {"samples": len(recent), "avg_anchor_invalid_rate": round(avg, 3)}
        if avg > 0.2:
            warnings.append({"code": "F11-POST-GATE-ANCHOR-HIGH",
                "detail": f"post_gate_audit 近 {len(recent)} 次 anchor_invalid_rate 均值 {avg:.2f} >0.2 → 锚点抽检质量异常，进复盘议题"})

    # F12 规则冲突裁决消费（AGT-007）：窗口内有新增裁决记录 → 必须进复盘议题
    if os.path.exists(RULE_CONFLICT_LOG):
        rc_new, rc_nots = 0, 0
        with open(RULE_CONFLICT_LOG, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                ts19 = str(rec.get("ts", rec.get("timestamp", "")))[:19]
                if not ts19:
                    rc_nots += 1
                elif start_iso[:19] <= ts19 <= end_iso[:19]:
                    rc_new += 1
        stats["rule_conflict"] = {"new_in_window": rc_new, "no_timestamp": rc_nots}
        if rc_new or rc_nots:
            warnings.append({"code": "F12-RULE-CONFLICT-PENDING",
                "detail": f"rule_conflict_adjudication.jsonl 窗口内新增 {rc_new} 条（无时间戳 {rc_nots} 条）→ 必须进复盘议题"})

    # F10 方案判A出口未扳子分身闸（2026-08-22 块I 用户指令焊死，REFORM-GATE 判A，
    # 块文件 logs/reform_blocks/dispatch_gate_weld_20260822.md；与 F10 质量信号
    # warning 并存，违例码独立）：
    # gate_switch.jsonl 有 reform_gate 判A / plan_select.jsonl 有判A 留痕出现后，
    # 同会话后续窗口（至会话末或下一判A前）无 dispatch_switch.py 扳动留痕 → 违例进复盘。
    exit_marks = []
    if os.path.exists(GATE_LOG):
        with open(GATE_LOG, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if "reform_gate" in str(rec.get("spec", "")) and rec.get("verdict") == "A":
                    exit_marks.append(("reform_gate", str(rec.get("ts", ""))))
    if os.path.exists(PLAN_SELECT_LOG):
        with open(PLAN_SELECT_LOG, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("verdict") == "A" and not rec.get("event"):
                    exit_marks.append(("plan_select", str(rec.get("ts", ""))))
    exit_marks = sorted((m for m in exit_marks if m[1] and m[1] >= start_iso),
                        key=lambda m: m[1])
    stats["plan_exit_marks_in_window"] = len(exit_marks)
    f10_misses = []
    for i, (src, mts) in enumerate(exit_marks):
        win_end = exit_marks[i + 1][1] if i + 1 < len(exit_marks) else None

        def _dispatched(r, _lo=mts, _hi=win_end):
            rts = str(r.get("ts", ""))
            return same_session(r, sid) and rts >= _lo and (_hi is None or rts < _hi)

        if not log_has_record(DISPATCH_LOG, start_iso, _dispatched):
            f10_misses.append(f"{src}@{mts}")
    if f10_misses:
        violations.append({"code": "F10-PLAN-EXIT-NO-DISPATCH",
            "detail": f"窗口内 {len(exit_marks)} 次方案判A出口，其中 {len(f10_misses)} 次后续窗口 "
                      f"无 dispatch_switch 扳动留痕（{f10_misses[:3]}）→ 子分身闸漏扳"
                      f"（2026-08-22 焊死条款：判A后执行前必扳，单任务亦扳由开关自判）"})

    # ━━━ F11 漏判捕获/漏例回收机（2026-08-22 块L 方向1，REFORM-GATE 判A）━━━
    # 逐次扳闸留痕对比其前最近一次扫描命中集：扳了闸但该 turn 注入/命中中无对应
    # 信号 → 漏例（判定层漏判实证），落盘 miss_cases.jsonl 供复盘着陆回收为新成分。
    # 豁免：扫描~扳闸之间用户输入显式点名 spec 文件名（直接指令扳闸不算漏判）。
    # turn 近似口径：扫描/扳闸留痕无 turn 字段，取"扳闸前最近一次扫描"为该 turn 注入集。
    scans = []
    if os.path.exists(TRIGGER_SCAN_LOG):
        with open(TRIGGER_SCAN_LOG, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                sts = str(rec.get("ts", ""))
                if sts:
                    scans.append((sts, set(rec.get("hit_ids", []))
                                  | set(rec.get("component_hit_ids", []))))
        scans.sort(key=lambda s: s[0])
    flips = []  # (ts, gate_key, expected_signal)
    if os.path.exists(GATE_LOG):
        with open(GATE_LOG, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                fts = str(rec.get("ts", ""))
                if not (start_iso <= fts <= end_iso):
                    continue
                base = os.path.basename(str(rec.get("spec", "")))
                for key, sig in SPEC_SIGNAL_MAP.items():
                    if key in base:
                        flips.append((fts, key, sig))
                        break
    if os.path.exists(DISPATCH_LOG):
        with open(DISPATCH_LOG, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                fts = str(rec.get("ts", ""))
                if start_iso <= fts <= end_iso and same_session(rec, sid):
                    flips.append((fts, "dispatch_switch", DISPATCH_SIGNAL))
    # 既有漏例去重键（幂等：审计可重复跑不重复落盘）
    seen_miss = set()
    if os.path.exists(MISS_CASES_LOG):
        with open(MISS_CASES_LOG, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                seen_miss.add((str(rec.get("ts", "")), str(rec.get("gate", ""))))
    new_misses, exempted, no_scan = [], 0, 0
    for fts, key, sig in sorted(flips):
        prev = [s for s in scans if s[0] <= fts]
        if not prev:
            no_scan += 1
            continue  # 扫描缺失由 F9 覆盖，不在此重复判
        sc_ts, sc_hits = prev[-1]
        if sig in sc_hits:
            continue  # 信号命中→扳闸，判定链正常
        # 豁免：扫描~扳闸窗口内用户输入点名 spec 文件名
        window_msgs = [t for mts, t in u_msgs_timed
                       if mts and sc_ts <= mts <= fts]
        if any(key in t or f"{key}.json" in t for t in window_msgs):
            exempted += 1
            continue
        snippet = ""
        prior = [t for mts, t in u_msgs_timed if mts and mts <= fts]
        if prior:
            snippet = re.sub(r"\s+", " ", prior[-1])[:120]
        miss = {"ts": fts, "gate": key, "expected_signal": sig,
                "scan_ts": sc_ts, "scan_hits": sorted(sc_hits),
                "input_snippet": snippet, "session": sid,
                "disposition": "pending（复盘着陆回收：差异措辞→候选成分→误触≤5%标定入表）"}
        new_misses.append(miss)
    if new_misses:
        os.makedirs(os.path.dirname(MISS_CASES_LOG), exist_ok=True)
        with open(MISS_CASES_LOG, "a", encoding="utf-8") as fh:
            for m in new_misses:
                if (m["ts"], m["gate"]) not in seen_miss:
                    fh.write(json.dumps(m, ensure_ascii=False) + "\n")
                    seen_miss.add((m["ts"], m["gate"]))
        violations.append({"code": "F11-MISS-CAPTURE",
            "detail": f"窗口内 {len(flips)} 次扳闸中 {len(new_misses)} 次对应信号未命中"
                      f"（豁免点名 {exempted} / 无扫描 {no_scan}）→ 漏例已落 miss_cases.jsonl "
                      f"待复盘回收：{[m['gate'] + '@' + m['ts'][11:19] for m in new_misses[:5]]}"})
    stats["f11_miss_capture"] = {"flips": len(flips), "misses": len(new_misses),
                                 "exempted": exempted, "no_scan": no_scan}

    out = {"ok": not violations, "session_log": path, "log_source": source,
           "session_start": start_iso, "subagent_calls": sub_calls,
           "violations": violations, "warnings": warnings, "stats": stats}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if violations:
        dims = sorted({v["code"].split("-")[0] for v in violations})
        print(f"FIRST_PUSH_AUDIT_RESULT: FAIL dims={dims} count={len(violations)} warnings={len(warnings)}")
        return 2
    print(f"FIRST_PUSH_AUDIT_RESULT: PASS warnings={len(warnings)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
