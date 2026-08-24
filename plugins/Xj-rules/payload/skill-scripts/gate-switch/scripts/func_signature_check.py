#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
func_signature_check.py — 规则29 函数签名实证器（2026-08-15 裁定，通用工具）

写测试调用前实证被测函数真实签名与存活：ast 解析定位函数定义，
输出真实签名；找不到（已删除/重命名）→ 判 B，禁止凭记忆写调用。
"""
import argparse
import ast
import glob
import json
import os
import sys


def sig_of(node):
    a = node.args
    parts = []
    defaults = [None] * (len(a.args) - len(a.defaults)) + list(a.defaults)
    for arg, dft in zip(a.args, defaults):
        s = arg.arg
        if arg.annotation:
            s += ": " + ast.unparse(arg.annotation)
        if dft is not None:
            s += "=" + ast.unparse(dft)
        parts.append(s)
    if a.vararg:
        parts.append("*" + a.vararg.arg)
    for arg, dft in zip(a.kwonlyargs, a.kw_defaults):
        s = arg.arg
        if dft is not None:
            s += "=" + ast.unparse(dft)
        parts.append(s)
    if a.kwarg:
        parts.append("**" + a.kwarg.arg)
    ret = " -> " + ast.unparse(node.returns) if node.returns else ""
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    return f"{prefix}{node.name}({', '.join(parts)}){ret}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--func", required=True)
    ap.add_argument("--src", required=True, help="源码文件或目录（递归 .py）")
    args = ap.parse_args()

    files = [args.src] if os.path.isfile(args.src) else sorted(
        glob.glob(os.path.join(args.src, "**", "*.py"), recursive=True))
    hits = []
    for p in files:
        try:
            tree = ast.parse(open(p, encoding="utf-8").read())
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == args.func:
                hits.append({"file": p, "line": node.lineno, "signature": sig_of(node)})

    if not hits:
        print(json.dumps({"pass": False,
                          "violations": [f"函数 {args.func} 在 {args.src} 不存在（已删除/重命名），禁止凭记忆写调用"]},
                         ensure_ascii=False, separators=(",", ":")))
        sys.exit(1)
    print(json.dumps({"pass": True, "func": args.func, "hits": hits},
                     ensure_ascii=False, separators=(",", ":")))
    sys.exit(0)


if __name__ == "__main__":
    main()
