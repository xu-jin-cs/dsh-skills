#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""safety_cmd_guard.py — 安全铁律事后审计闸（2026-08-17 REFORM-GATE 判立即改落地；2026-08-20 补丁：rm 强制旗标 -f 漏判 + 多文件漏判 + mv 多命令误报修复，判危逻辑一致化真源）

短板B改造：00_root_safety.md 目录树铁律原为 L1 文本级无机械兜底；平台沙箱
workspace=整个家目录对 ~/.agents 内危险命令保护≈零，且无 git 回滚。
本闸克隆 reform_exit_guard.py 骨架，扫 DSH 会话 jsonl 的 tool/call 记录，一门三查：

  S1 危险命令黑名单（铁律7：rm 限单文件 / mv·cp -R 源限单文件）：
     - rm 带 -r/-R/-f 组合（含 rm -rf）→ 违例
     - rm 删除多于 1 个文件参数 → 违例（铁律7：rm 仅限单个文件）
     - cp 带 -r/-R（递归拷贝，源必为目录）→ 违例
     - find ... -delete → 违例
     - mv 源参数审计时为现存目录或以 / 结尾或含通配符 → 违例
  S2 固定目录区块完整性（铁律6）：哨兵文件内
     `====【不可修改固定目录区块】====` 标记符计数必须成对（0 或 2）。
  S3 打断即停手弱审计（2026-08-16 双事故条款）：user/message 插入后
     同轮仍出现 tool/call → WARNING 线索（只报不判 B，防"提问 vs 继续指令"语义误报）。

退出码：0=A 全过 / 2=B 违例清单（gate-switch script_exit 包装，expect=0）。
用法：python3 safety_cmd_guard.py [--session-log <path>]
"""
import argparse
import glob
import json
import os
import re
import shlex
import subprocess
import sys

DSH_SESSIONS_GLOB = os.path.expanduser("~/.dsh/sessions/*/*/session.jsonl.zstd")

# S2 哨兵文件清单（含固定目录区块标记的索引类文件，可扩充）
SENTINEL_FILES = [
    os.path.expanduser("~/.dsh/AGENTS.md"),
    os.path.expanduser("~/AGENTS.md"),
]
FIXED_BLOCK_MARK = "====【不可修改固定目录区块】===="

RE_RM = re.compile(r"\brm\b")
RE_RM_FLAGS = re.compile(r"-[a-zA-Z]*[rRf][a-zA-Z]*")  # 递归 -r/-R 或强制 -f（含组合如 -rf、-fr）
RE_CP_RECURSIVE = re.compile(r"\bcp\s+(?:-[a-zA-Z]*[rR][a-zA-Z]*)")
RE_FIND_DELETE = re.compile(r"\bfind\b[^\n|;&]*\s-delete\b")
RE_MV = re.compile(r"\bmv\s+")


def check_rm_danger(seg):
    """铁律7：rm 仅限删除单个文件。带 -r/-R/-f 任何旗标，或删除多于 1 个文件参数，均命危。"""
    try:
        tokens = shlex.split(seg)
    except Exception:
        return None
    if not tokens or tokens[0] != "rm":
        return None
    flags = [t for t in tokens[1:] if t.startswith("-") and not t.startswith("--")]
    files = [t for t in tokens[1:]
             if not (t.startswith("-") and not t.startswith("--")) and not t.startswith("--")]
    for f in flags:
        if RE_RM_FLAGS.search(f):
            return {"code": "S1-RM-RECURSIVE", "cmd": seg[:200],
                    "detail": f"rm 携带强制/递归旗标 {f}，违反铁律7（rm 仅限单个文件）"}
    if len(files) > 1:
        return {"code": "S1-RM-MULTI", "cmd": seg[:200],
                "detail": f"rm 删除 {len(files)} 个文件，违反铁律7（rm 仅限单个文件）"}
    return None


def check_dangerous_commands(cmds):
    """S1：危险命令黑名单，返回违例清单。"""
    hits = []
    for cmd in cmds:
        for line in re.split(r"&&|\|\||;", cmd):
            seg = line.strip()
            if not seg:
                continue
            if RE_RM.search(seg):
                r = check_rm_danger(seg)
                if r:
                    hits.append(r)
            elif RE_CP_RECURSIVE.search(seg):
                hits.append({"code": "S1-CP-RECURSIVE", "cmd": seg[:200],
                             "detail": "cp 递归拷贝源必为目录，违反铁律7（cp -R 源须单文件）"})
            elif RE_FIND_DELETE.search(seg):
                hits.append({"code": "S1-FIND-DELETE", "cmd": seg[:200],
                             "detail": "find -delete 批量删除，绕开单文件限制"})
            elif RE_MV.search(seg):
                # 多行/多命令块：mv 是其中某条，需定位 mv 自身的参数，
                # 不要把前面 cd 的目录或后续 shell 片段误当 mv 源（2026-08-20 修复误报）
                mv_block = seg
                if "\n" in seg or "&&" in seg or ";" in seg:
                    mv_block = None
                    for sub in re.split(r"\n|&&|\|\||;", seg):
                        if re.match(r"^\s*mv\s+", sub):
                            mv_block = sub.strip()
                            break
                    if mv_block is None:
                        continue
                try:
                    tokens = [t for t in shlex.split(mv_block) if not t.startswith("-")]
                except Exception:
                    continue
                sources = tokens[1:-1] if len(tokens) >= 3 else []
                for src in sources:
                    if src.endswith("/") or "*" in src or os.path.isdir(os.path.expanduser(src)):
                        hits.append({"code": "S1-MV-DIRECTORY", "cmd": seg[:200],
                                     "detail": f"mv 源疑似目录（{src}），违反铁律7"})
                        break
    return hits


def resolve_session_log(explicit=None):
    if explicit:
        return explicit, "arg"
    env = os.environ.get("DSH_SESSION_JSONL")
    if env and os.path.exists(env):
        return env, "env"
    cands = sorted(glob.glob(DSH_SESSIONS_GLOB), key=os.path.getmtime, reverse=True)
    return (cands[0], "glob") if cands else (None, None)


def read_events(path):
    """返回事件列表 [(type, data)]；解压失败返回 None。"""
    try:
        proc = subprocess.run(["zstd", "-dc", path], capture_output=True, timeout=120)
        raw = proc.stdout.decode("utf-8", "replace")
    except Exception:
        return None
    events = []
    for line in raw.splitlines():
        if '"type"' not in line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        events.append((obj.get("type"), obj.get("data", {})))
    return events


def extract_bash_commands(events):
    """从 tool/call 事件提取 bash 命令清单。"""
    cmds = []
    for t, data in events:
        if t != "tool/call":
            continue
        name = data.get("name", "")
        args_raw = data.get("arguments", "")
        if name != "bash":
            continue
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except Exception:
            continue
        cmd = args.get("command", "")
        if cmd:
            cmds.append(cmd)
    return cmds


def check_fixed_blocks():
    """S2：哨兵文件固定区块标记符成对性。"""
    hits = []
    for fp in SENTINEL_FILES:
        if not os.path.exists(fp):
            continue
        try:
            with open(fp, encoding="utf-8") as f:
                n = f.read().count(FIXED_BLOCK_MARK)
        except Exception:
            continue
        if n not in (0, 2):
            hits.append({"code": "S2-FIXED-BLOCK-BROKEN", "file": fp,
                         "detail": f"固定目录区块标记符计数={n}（应成对：0 或 2），疑似被破坏"})
    return hits


def check_interrupt_warnings(events):
    """S3：user/message 后同轮出现 tool/call → WARNING 线索（不判 B）。"""
    warns = []
    pending_user = False
    for t, data in events:
        if t == "user/message":
            pending_user = True
        elif t == "assistant/message":
            pending_user = False  # 新一轮助手回合开始，重置
        elif t == "tool/call" and pending_user:
            warns.append({"code": "S3-INTERRUPT-OVERRUN",
                          "tool": data.get("name", "?"),
                          "detail": "用户发言后同轮仍发起工具调用，疑似违反打断即停手（需人工复核：提问 vs 继续指令）"})
            pending_user = False  # 同轮只报一次
    return warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-log", default=None)
    args = ap.parse_args()

    path, source = resolve_session_log(args.session_log)
    if not path:
        print(json.dumps({"ok": False, "violations": [{"code": "S0-NO-SESSION",
              "detail": "无法定位会话日志（--session-log 显式指定后重跑）"}]}, ensure_ascii=False, indent=2))
        print("SAFETY_CMD_GUARD_RESULT: FAIL dims=['INFRA']")
        return 2

    events = read_events(path)
    if events is None:
        print(json.dumps({"ok": False, "violations": [{"code": "S0-DECOMPRESS",
              "detail": f"会话日志解压失败: {path}"}]}, ensure_ascii=False, indent=2))
        print("SAFETY_CMD_GUARD_RESULT: FAIL dims=['INFRA']")
        return 2

    cmds = extract_bash_commands(events)
    violations = check_dangerous_commands(cmds) + check_fixed_blocks()
    warnings = check_interrupt_warnings(events)

    out = {
        "ok": not violations,
        "session_log": path,
        "log_source": source,
        "bash_commands_scanned": len(cmds),
        "violations": violations,
        "warnings": warnings,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if violations:
        dims = sorted({v["code"].split("-")[0] for v in violations})
        print(f"SAFETY_CMD_GUARD_RESULT: FAIL dims={dims} count={len(violations)} warnings={len(warnings)}")
        return 2
    print(f"SAFETY_CMD_GUARD_RESULT: PASS warnings={len(warnings)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
