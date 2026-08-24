#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
archmap_diff_check.py — archmap 复盘前 diff 留痕新鲜度最小校验器（gate-switch 配套，2026-08-15）

校验 {project}/archmap/diff_history.jsonl：
  0. 前置分流（2026-08-15 用户裁定修复）：先机械检测工作期项目有无真实变更——
     无变更 → exit 0「无变更豁免」（0 留痕是正常状态而非机制空转；
     实证：某引擎项目 diff_history 为 0 系无功能变更/改完未跑 archmap，曾被误判为空转）；
     有变更 → 才查留痕（下列 1-3）
  1. 存在（file_exists 语义）
  2. 非空壳（size > 0，防 0 字节占位伪造）
  3. mtime 晚于 work_start（复盘工作期起点，防旧留痕冒充本工作期留痕）

work_start 三种可解析形态（按序尝试）：
  - 存在的文件路径 → 取其 mtime（对齐 touch /tmp/retro_marker_<复盘名> 标记文件用法）
  - epoch 秒（浮点/整数字符串）
  - ISO 8601 时间戳

退出码：0=全部通过 / 1=有违例（stdout 列出违例明细）。
由 gate_switch.py 以 script_exit 原语包装（expect 0）。
"""
import argparse
import datetime
import os
import subprocess
import sys

# 变更检测的排除目录（mtime 扫描回退通道用）
_SKIP_DIRS = {".git", "node_modules", "__pycache__", "dist", "build", "archmap", ".venv", "venv"}
# 只认这些代码/文档扩展名，防日志/缓存/产物文件误报为"变更"
_SRC_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".java", ".go", ".rs",
            ".md", ".json", ".yaml", ".yml", ".sql", ".sh", ".html", ".css"}


def detect_changes(project, ws):
    """工作期有无真实变更。返回 True=有变更 / False=无变更（豁免）。
    通道1（git 仓）：git log --since 有提交 → 有变更；否则对 git status --porcelain
    列出的脏文件逐个查 mtime > ws（porcelain 反映当前脏状态而非时间窗，必须用
    mtime 再过一道时间闸——work_start 之前改而未提交的文件不算本工作期变更）。
    通道2（非 git 或 git 失败）：源码文件 mtime > ws 扫描（限深排除噪声目录）。"""
    try:
        r = subprocess.run(
            ["git", "-C", project, "log", "--oneline", f"--since={int(ws)}"],
            capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            if r.stdout.strip():
                return True
            r2 = subprocess.run(
                ["git", "-C", project, "status", "--porcelain"],
                capture_output=True, text=True, timeout=15)
            if r2.returncode == 0:
                for line in r2.stdout.splitlines():
                    # porcelain 格式: "XY path" 或 "XY orig -> new"
                    p = line[3:].split(" -> ")[-1].strip().strip('"')
                    fp = os.path.join(project, p)
                    try:
                        if os.path.isfile(fp) and os.path.getmtime(fp) > ws:
                            return True
                    except OSError:
                        continue
                return False
    except (OSError, subprocess.TimeoutExpired):
        pass
    # 回退：mtime 扫描
    for root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        if root.count(os.sep) - project.count(os.sep) > 6:
            dirs[:] = []
            continue
        for fn in files:
            if os.path.splitext(fn)[1].lower() not in _SRC_EXT:
                continue
            fp = os.path.join(root, fn)
            try:
                if os.path.getmtime(fp) > ws:
                    return True
            except OSError:
                continue
    return False


def parse_work_start(raw):
    """解析工作期起点为 epoch 秒；无法解析返回 None。"""
    if os.path.exists(raw):
        return os.path.getmtime(raw)
    try:
        return float(raw)
    except ValueError:
        pass
    try:
        dt = datetime.datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.astimezone()  # 朴素时间戳按本地时区解释
        return dt.timestamp()
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser(description="archmap diff 留痕新鲜度校验（复盘前固定卡点）")
    ap.add_argument("--project", required=True, help="项目根路径（内含 archmap/ 目录）")
    ap.add_argument("--work-start", required=True,
                    help="复盘工作期起点：标记文件路径 / epoch 秒 / ISO 8601 时间戳")
    args = ap.parse_args()

    target = os.path.join(args.project, "archmap", "diff_history.jsonl")
    violations = []

    ws = parse_work_start(args.work_start)
    if ws is None:
        violations.append(
            f"work_start 无法解析: {args.work_start!r}（需标记文件路径/epoch秒/ISO8601）")
    elif not detect_changes(args.project, ws):
        # 无变更豁免：0 留痕是正常状态，不是机制空转（2026-08-15 用户裁定）
        print(f"OK: 无变更豁免——工作期 {args.project} 无代码变更，diff 留痕闸不适用")
        sys.exit(0)

    if not os.path.isfile(target):
        violations.append(f"diff 留痕文件不存在: {target}（工作期有变更但 archmap diff 留痕机制从未激活）")
    else:
        size = os.path.getsize(target)
        if size <= 0:
            violations.append(f"diff 留痕为空壳: {target} size=0B（0 字节占位=0 留痕，视同未激活）")

        mtime = os.path.getmtime(target)
        if mtime <= ws:
            violations.append(
                "diff 留痕不新于工作期起点: "
                f"mtime={datetime.datetime.fromtimestamp(mtime).isoformat(timespec='seconds')} "
                f"<= work_start={datetime.datetime.fromtimestamp(ws).isoformat(timespec='seconds')}"
                "（本工作期有变更但未执行 archmap +diff 留痕）")

    if violations:
        for v in violations:
            print(f"VIOLATION: {v}")
        # script_exit 原语只取 stdout 末行作 B 档理由 → 末行必须是全量违例汇总
        print(f"VIOLATIONS({len(violations)}): " + " ｜ ".join(violations))
        sys.exit(1)
    print(f"OK: {target} 存在、非空、新于工作期起点")
    sys.exit(0)


if __name__ == "__main__":
    main()
