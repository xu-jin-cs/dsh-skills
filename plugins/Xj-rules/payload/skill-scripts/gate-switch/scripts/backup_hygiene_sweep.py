#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backup_hygiene_sweep.py — 备份残渣自动清扫开关（L2 执行体，2026-08-20 用户提案 REFORM-GATE 判A落地）

定位：backup_hygiene.json（纯核验闸）的执行体另一半——检查→执行闭环。
策略（用户 2026-08-20 终裁）：
  - 阈值 >0 零容忍：发现散落备份即自动处置
  - 只归档永不自动 rm：mv 到 <治理域根>/archive/backup_<date>/<相对路径>（非破坏可考古）；
    删除是破坏性动作，永久保留给 danger_cmd_gate 人工闸，本执行体不越权
  - 挂载点：会话开始闸族（与 retro_audit_freshness 同点位，"人不记系统记"）

扫描域与豁免（与 backup_hygiene.json 严格同口径）：
  域：~/.agents ~/.dsh ~/agent-harness ~/dsh-skills
  模式：*.bak / *.backup / *.old / *~ / *.bak.*
  豁免：*/archive/* 、 */migration_backup/*

用法：
  backup_hygiene_sweep.py            # 扫描+自动归档（会话开始挂载形态）
  backup_hygiene_sweep.py --dry-run  # 只扫描报告不动作

退出码：0 = 清扫完成或本无一物（报告见 stdout JSON）；2 = 有文件归档失败（violations 列出）
留痕：~/.agents/logs/backup_hygiene_sweep.jsonl
"""
import datetime
import json
import os
import shutil
import sys

HOME = os.path.expanduser("~")
ROOTS = [f"{HOME}/.agents", f"{HOME}/.dsh", f"{HOME}/agent-harness", f"{HOME}/dsh-skills"]
EXEMPT = ("/archive/", "/migration_backup/")
SUFFIXES = (".bak", ".backup", ".old", "~")
LOG = f"{HOME}/.agents/logs/backup_hygiene_sweep.jsonl"


def is_backup(name):
    if name.endswith(SUFFIXES):
        return True
    # .bak- 模式（如 SKILL.md.bak-3word-reregister-<ts>；2026-08-22 片2 实证修补：
    # 横杠命名不被点分隔口径覆盖，曾致 found:0 假阴性 CLEAN，13 残渣漏扫）
    if ".bak-" in name:
        return True
    # *.bak.* 模式（如 .bak.20260817）
    base = name.split(".")
    return "bak" in base[1:-1] if len(base) > 2 else False


def scan():
    hits = []
    for root in ROOTS:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                p = os.path.join(dirpath, fn)
                norm = p.replace(os.sep, "/")
                if any(x in norm for x in EXEMPT):
                    continue
                if is_backup(fn):
                    hits.append(p)
    return sorted(hits)


def root_of(path):
    """最长前缀匹配治理域根（/.agents 优先于更短前缀，天然有序）。"""
    best = ""
    for r in ROOTS:
        if path.startswith(r + os.sep) and len(r) > len(best):
            best = r
    return best or ROOTS[0]


def sweep(paths, today):
    moved, failed = [], []
    for p in paths:
        root = root_of(p)
        rel = os.path.relpath(p, root)
        dest = os.path.join(root, "archive", f"backup_{today}", rel)
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(p, dest)
            moved.append({"from": p, "to": dest})
        except Exception as e:
            failed.append({"path": p, "error": str(e)})
    return moved, failed


def main():
    dry = "--dry-run" in sys.argv
    today = datetime.date.today().strftime("%Y%m%d")
    found = scan()
    moved, failed = ([], [])
    if found and not dry:
        moved, failed = sweep(found, today)
    out = {
        "gate": "backup_hygiene_sweep",
        "mode": "dry-run" if dry else "sweep",
        "threshold": ">0 零容忍（用户 2026-08-20 终裁）",
        "found": len(found),
        "moved": len(moved),
        "failed": failed,
        "items": moved if moved else [{"found_only": p} for p in found],
        "verdict": "CLEAN" if not found else ("SWEPT" if not failed else "PARTIAL-FAIL"),
        "directive": (
            "治理域零残渣" if not found else
            "已自动归档（非破坏，永不自动 rm；物理删除走 danger_cmd_gate 人工闸）" if not failed else
            "部分归档失败，violations 即残留清单，人工处置"
        ),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "mode": out["mode"], "found": len(found),
                "moved": len(moved), "failed": len(failed),
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 留痕失败不阻断
    sys.exit(2 if failed else 0)


if __name__ == "__main__":
    main()
