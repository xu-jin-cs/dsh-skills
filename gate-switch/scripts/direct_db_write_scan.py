#!/usr/bin/env python3
"""direct_db_write_scan.py — direct_db_write_gate 扫描器（2026-08-31 问题闸判A落地）。

规则 38/40 机械防线：RetroETLEngine 是唯一写点，禁止绕开引擎直连
LanceDB/SQLite/BM25 写数据。本脚本扫描 agent-harness 工程代码，命中白名单外
直连写库原语即 exit 2（判 B）。挂点：复盘着陆闸族 + 交付期。

白名单：
  - engine 本体（~/.agents/retro-skills-registry/engine/ 不在本扫描范围）
  - knowledge_base/vector_store/（lancedb_manager 等管理器层）
  - legacy_allowlist.json 登记的存量违规（3 个直连 ingest 脚本，任务15拆解中，只减不增）
"""
import json
import io
import os
import re
import sys
import tokenize


def _strip_noncode(text: str) -> str:
    """把注释与字符串字面量（含 docstring）的内容置空（保列位，不改其他字符）——
    字符串里的"调用"不是调用；位置保持不变，避免误报也避免误伤。"""
    chars = list(text)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type not in (tokenize.COMMENT, tokenize.STRING):
                continue
            lines = text.splitlines(keepends=True)
            s = sum(len(l) for l in lines[:tok.start[0] - 1]) + tok.start[1]
            e = sum(len(l) for l in lines[:tok.end[0] - 1]) + tok.end[1]
            for i in range(s, min(e, len(chars))):
                if chars[i] != "\n":
                    chars[i] = " "
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return "".join(chars)

ROOT = os.path.expanduser(os.environ.get("AGENT_HARNESS_ROOT", "~/agent-harness"))
ALLOWLIST_PATH = os.path.expanduser(
    "~/.agents/skills/gate-switch/data/direct_db_write_allowlist.json")

# 直连写库原语（写方法级，只打"写"不打"读"——读路径（stats/search 端点）
# 经 VectorStore/lancedb.connect 只读不违规，规则 38 禁的是绕引擎写数据）
PRIMITIVES = [
    r"_table\.add\(|_table\.delete\(",
    r"write_overwrite\(|merge_insert\(|upsert_raw",
    r"\.create_table\(",
    r"upsert_chunks\(|insert_chunks\(",
]

# 豁免目录（管理器层/历史留痕/依赖/测试/数据归档）
EXEMPT_DIRS = (
    "/knowledge_base/vector_store/",
    "/tongue_diagnosis/vector_store/",
    "/_backups/", "/archive/", "/data/", "/etl_data/", "/deploy/",
    "/node_modules/", "/__pycache__/", "/.git/",
    "/tests/",
)


def load_allowlist() -> dict:
    if not os.path.isfile(ALLOWLIST_PATH):
        return {"legacy_allowlist": []}
    with open(ALLOWLIST_PATH, encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    allow = set(load_allowlist().get("legacy_allowlist", []))
    hits = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            rel = path.replace(ROOT, "")
            if any(x in rel for x in EXEMPT_DIRS):
                continue
            if rel in allow:
                continue
            try:
                text = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            code = _strip_noncode(text)
            for pat in PRIMITIVES:
                for m in re.finditer(pat, code):
                    line = code[:m.start()].count("\n") + 1
                    hits.append(f"{rel}:{line} [{pat}]")

    if hits:
        print(f"direct_db_write_scan: 白名单外直连写库命中 {len(hits)} 处 → 判 B")
        for h in hits[:20]:
            print("  ", h)
        return 2
    print("direct_db_write_scan: 白名单外零命中 → PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
