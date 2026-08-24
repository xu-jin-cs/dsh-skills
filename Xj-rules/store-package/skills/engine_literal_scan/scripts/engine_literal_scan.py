#!/usr/bin/env python3
"""engine_literal_scan.py — 引擎层业务字面量扫描（P2 防复发闸，2026-08-20 REFORM-GATE 判A）

契约（gate_switch.py script_exit 原语）：
  python3 engine_literal_scan.py
  exit 0 = 扫描零命中（或命中均在 legacy_allowlist 内）
  exit 2 = 发现词表字面量命中且不在白名单（stdout 逐条列出 文件:行号:内容）

数据源：~/.agents/skills/engine_literal_scan/data/engine_literal_wordlist.json
词表只增不删；legacy_allowlist 只减不增（迁移清账后移除）。
"""
import json
import os
import re
import sys

HOME = os.path.expanduser("~")
WORDLIST = os.path.join(HOME, ".agents/skills/engine_literal_scan/data/engine_literal_wordlist.json")


def main():
    cfg = json.load(open(WORDLIST, encoding="utf-8"))
    wb = [re.escape(w) for w in cfg["literals"]["word_boundary"]]
    exact = [re.escape(w) for w in cfg["literals"]["exact"]]
    pattern = re.compile(r"\b(" + "|".join(wb) + r")\b|" + "|".join(exact))
    allow = {os.path.normpath(os.path.join(HOME, f.replace("~/", ""))) if f.startswith("~/")
             else os.path.normpath(os.path.join(HOME, f)) for f in cfg["legacy_allowlist"]["files"]}
    excl = re.compile("|".join(re.escape(p) for p in cfg["exclude_patterns"]))

    hits, scanned = [], 0
    for d in cfg["scan_dirs"]:
        root = os.path.expanduser(d)
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                if not any(fn.endswith(g[1:]) for g in cfg["include_globs"]):
                    continue
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, HOME)
                if excl.search(rel):
                    continue
                if os.path.normpath(path) in allow:
                    continue
                scanned += 1
                try:
                    with open(path, encoding="utf-8", errors="ignore") as fh:
                        for ln, line in enumerate(fh, 1):
                            if pattern.search(line):
                                hits.append(f"{rel}:{ln}: {line.strip()[:100]}")
                except OSError:
                    continue

    if hits:
        print(f"ENGINE-LITERAL-SCAN: 判B——引擎层业务字面量 {len(hits)} 处命中（扫描 {scanned} 文件，词表 {WORDLIST}）：")
        for h in hits[:30]:
            print("  " + h)
        sys.exit(2)
    print(f"ENGINE-LITERAL-SCAN: PASS 扫描 {scanned} 文件零命中（白名单 {len(allow)} 个存量登记文件除外）")
    sys.exit(0)


if __name__ == "__main__":
    main()
