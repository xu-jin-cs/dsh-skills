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


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def block_passes(block_path):
    """复核质疑块仍判A（防止戳记对应的块被改坏）。"""
    if not os.path.isfile(block_path):
        return False
    r = subprocess.run(["python3", GATE, "--spec", SPEC, "--set", f"block={block_path}"],
                       capture_output=True, text=True, timeout=30)
    try:
        out = json.loads(r.stdout[r.stdout.find("{"):])
        return out.get("verdict") == "A"
    except Exception:
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
    if not command.strip() or not TEST_CMD_RE.search(command):
        return 0
    try:
        if stamp_valid():
            log("test_steering_hook: 放行（戳记有效）")
            return 0
    except Exception as e:
        log(f"test_steering_hook ERROR: {e!r}")
        return 0  # fail-open
    sys.stderr.write(
        "BLOCK 方向盘闸：检测到测试执行，但未找到有效的规格质疑块戳记。\n"
        f"先填块（模板 {TEMPLATE}）→ 过闸：gate_switch.py --spec spec_challenge_gate.json "
        "--set block=<块文件> 判 A → 打戳：test_steering_hook.py --stamp <块文件> → 重试。\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
