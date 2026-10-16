#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZCode PreToolUse(Bash) hook：方向盘闸·测试命令族拦截（2026-10-15，通道2）。

LLM 自主跑测试（无用户消息进场，声明闸静默）时的机械兜底：
- 命令命中测试族（pytest / python3 .*test_*.py / acceptance_matrix / npm test …）且
  无有效质疑块戳记 → exit 2 阻断（deny），stderr 输出指引；
- 有效戳记（4h 内 + 块仍可判A复核）→ exit 0 放行；
- 非测试命令 → exit 0 不干预；
- 脚本故障 → exit 0 放行留痕（fail-open，仅对"缺戳记"这一确定态阻断）。

打戳（判A留痕）：python3 test_steering_hook.py --stamp <质疑块路径>
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

GATE = os.path.expanduser("~/.agents/skills/gate-switch/scripts/gate_switch.py")
SPEC = os.path.expanduser("~/.agents/skills/gate-switch/specs/spec_challenge_gate.json")
STAMP = os.path.expanduser("~/.agents/logs/spec_challenge_pass.json")
CREATED_LEDGER = os.path.expanduser("~/.agents/logs/spec_challenge_created.log")
LOG = os.path.expanduser("~/.agents/logs/zcode_hooks.log")
TEMPLATE = os.path.expanduser("~/.agents/skills/gate-switch/templates/SPEC_CHALLENGE_TEMPLATE.md")
STAMP_TTL = 4 * 3600  # 戳记有效期 4 小时

TEST_CMD_RE = re.compile(
    r"(pytest\b|python3?\s+\S*(test_|_test\.py)|acceptance_matrix\.py|npm\s+(run\s+)?test\b|"
    r"\.\/run_tests|bash\s+\S*test)")

# 高危变更族（2026-10-16 用户双闸裁定·方案B兜底：LLM 自主变更动作）
# 收窄判据：只拦高危变更命令族，不拦日常写操作（全写拦截=体系不可用，已否决）
CHANGE_CMD_RE = re.compile(
    r"(rm\s+-[rf]|rm\s+[^\n]*~?/\.|mv\s+\S+\s+\S+|git\s+push|git\s+reset\s+--hard|"
    r"curl\s+[^\n]*-X\s*(POST|PUT|DELETE|PATCH)|>\s*[^\n]*(\.agents|/etc/|/usr/|prod)|"
    r"pip3?\s+(install|uninstall)|brew\s+(install|uninstall)|docker\s+(rm|rmi|push)|"
    r"kill\s+-9|chmod\s+-R|chown\s+-R)")


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def block_passes(block_path):
    """复核质疑块仍判A（两个闸规格任一通过即可：测试族/通用变更族）。"""
    if not os.path.isfile(block_path):
        return False
    specs = [SPEC, os.path.expanduser("~/.agents/skills/gate-switch/specs/intent_risk_gate.json")]
    for spec in specs:
        r = subprocess.run(["python3", GATE, "--spec", spec, "--set", f"block={block_path}"],
                           capture_output=True, text=True, timeout=30)
        try:
            out = json.loads(r.stdout[r.stdout.find("{"):])
            if out.get("verdict") == "A":
                return True
        except Exception:
            continue
    return False


def ledger_created(path, kind):
    """机制产生文件建账（机制无权自删，误触发时打印给用户人工处置）。"""
    try:
        with open(CREATED_LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "kind": kind, "path": path}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def ledger_tail(n=5):
    try:
        lines = open(CREATED_LEDGER, encoding="utf-8").read().strip().splitlines()
        return lines[-n:] if lines else []
    except OSError:
        return []


def stamp_valid():
    try:
        s = json.load(open(STAMP, encoding="utf-8"))
        if time.time() - float(s.get("ts", 0)) > STAMP_TTL:
            return False
        return block_passes(s.get("block", ""))
    except Exception:
        return False


def do_stamp(block_path):
    if not os.path.isfile(block_path):
        print(f"BLOCK 质疑块不存在: {block_path}", file=sys.stderr)
        return 2
    if not block_passes(block_path):
        print("BLOCK 质疑块判 B，补齐字段后重扳", file=sys.stderr)
        return 2
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STAMP), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"block": os.path.abspath(block_path), "ts": time.time(),
                   "via": "test_steering_hook"}, f, ensure_ascii=False)
    os.replace(tmp, STAMP)
    ledger_created(os.path.abspath(block_path), "challenge_block")
    ledger_created(STAMP, "stamp")
    print(f"STAMP 打戳成功: {block_path}（4h 内测试命令族放行）")
    return 0


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--stamp":
        return do_stamp(sys.argv[2])
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command.strip():
        return 0
    is_test = bool(TEST_CMD_RE.search(command))
    is_change = bool(CHANGE_CMD_RE.search(command))
    if not (is_test or is_change):
        return 0
    family = "测试执行" if is_test else "高危变更"
    try:
        if stamp_valid():
            log("test_steering_hook: 放行（戳记有效）")
            return 0
    except Exception as e:
        log(f"test_steering_hook ERROR: {e!r}")
        return 0  # fail-open
    ledger = ledger_tail()
    ledger_note = ""
    if ledger:
        ledger_note = ("\n【误触发提醒】本机制无权自删文件；若本次属误触发（命令非测试任务），"
                       "以下由本机制产生的文件可由你人工处置：\n"
                       + "\n".join("  - " + l for l in ledger))
    sys.stderr.write(
        f"BLOCK 方向盘闸：检测到{family}，但未找到有效的规格质疑块戳记。\n"
        f"先填块（模板 {TEMPLATE}）→ 过闸：gate_switch.py --spec intent_risk_gate.json（测试场景用 spec_challenge_gate.json）"
        " --set block=<块文件> 判 A → 打戳：test_steering_hook.py --stamp <块文件> → 重试。\n"
        "若判定为误触发：忽略本阻断并直接告知用户即可，无需填块。" + ledger_note + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
