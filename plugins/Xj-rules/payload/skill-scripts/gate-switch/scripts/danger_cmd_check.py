#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""danger_cmd_check.py — 危险命令事前闸检查器（2026-08-17 存量清算落地）

与事后审计 safety_cmd_guard.py（S1 黑名单）互补：本脚本管"当次执行前"的 0/1
判定，事后审计管"漏扳"追责，双保险非重复设防。判危逻辑单一真源——直接从
safety_cmd_guard 导入 check_dangerous_commands，禁止双副本漂移。

用法（落盘文件传参，规避 shell 引用注入）：
    python3 danger_cmd_check.py --cmdfile <含待检命令的文本文件>
退出码：0=未命中黑名单（A 放行）/ 2=命中（B 阻断，violations 即明细）/ 3=输入不足。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from safety_cmd_guard import check_dangerous_commands  # 单一真源：S1 判危逻辑


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cmdfile", required=True)
    args = ap.parse_args()

    if not os.path.isfile(args.cmdfile):
        print(json.dumps({"ok": False, "reason": f"cmdfile 不存在: {args.cmdfile}"},
                         ensure_ascii=False))
        return 3
    with open(args.cmdfile, encoding="utf-8") as f:
        cmd = f.read().strip()
    if not cmd:
        print(json.dumps({"ok": False, "reason": "cmdfile 为空"}, ensure_ascii=False))
        return 3

    hits = check_dangerous_commands([cmd])
    out = {"ok": not hits, "cmd_preview": cmd[:120], "violations": hits}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if hits:
        print(f"DANGER_CMD_CHECK: BLOCKED count={len(hits)}")
        return 2
    print("DANGER_CMD_CHECK: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
