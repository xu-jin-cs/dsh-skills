"""observe 声明加载器（P1 · 只读 L1）—— 不依赖引擎内核，可独立运行。

职责：扫描资产定义里的 `observe:` 块，产出统一节点注册表，供平台 `assets/sync` 入库。
约束：
  - 不 import engine.kernel / engine.flow（保持与引擎解耦，可单测）
  - 每个 assetKey 只允许一处 observe（双载体 → DUAL_CARRIER 错误，fail-fast）
  - 非法声明（枚举/seq/字段）→ fail-fast 并给 file:line:field
  - 冻结白名单内资产照常入库，但打 frozen 标记（P1 只读展示）

用法：
  python3 -m engine.observe.contract_loader --check          # 只校验，非 0 退出=有问题
  python3 -m engine.observe.contract_loader --json out.json  # 产出注册表
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("FATAL 需要 PyYAML", file=sys.stderr)
    raise SystemExit(2)

SKILL_ROOT = Path.home() / ".agents" / "skills"
CONTRACT_VERSION = "1.0"
NODE_STATUSES = {"pending", "running", "waiting_input", "completed", "failed", "skipped", "stale", "voided"}
DELIVERABLE_TYPES = {"text", "structured", "binary", "none"}
EVENTS = {"node_start", "node_end", "node_failed", "input_ready", "task_end"}

# P1 冻结白名单（见 v3/05 §三）：入库但只读展示，不作执行演示
# 2026-11-05 移出 ppt：原冻结理由是"图谱对应已退役 12 节点流程"，现 SKILL.md 已自带
# 4 节点 observe 契约并接一行式 observe_step.py（退役图不再作为载体），冻结理由失效。
FROZEN_IDS = {
    "pptx": "纯母版不出片",
    "ppt-direct": "只覆盖直出分支，复刻分支未入图",
    "resume": "SKILL.md 称 12 节点，图为 11",
}


def _frozen_reason(asset_key: str) -> str:
    return FROZEN_IDS.get(asset_key.split(":", 1)[-1], "")


class ContractError(Exception):
    def __init__(self, asset_key: str, field: str, message: str, line: int = 0):
        self.asset_key, self.field, self.message, self.line = asset_key, field, message, line
        where = f"{field}:{line}" if line else field
        super().__init__(f"[{asset_key}] {where} {message}")


# ── 读取 ────────────────────────────────────────────────────────
SOURCE_LINE = re.compile(r"^(\s*sourceHash:\s*).*$", re.M)


def compute_source_hash(path: Path, carrier: str) -> str:
    """sourceHash 唯一口径：`sha256:` + sha256(载体内容, 自身 sourceHash 置空)[:16]。

    - 置空自身取值，避免"哈希含哈希"的自指
    - workflow_json：对 JSON 做规范化（sort_keys + 紧凑分隔符）后哈希整份文件
    - skill_md：对全文哈希（覆盖正文，不只节点标题）
    """
    import hashlib
    if carrier == "workflow_json":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(d.get("observe"), dict):
            d["observe"] = {**d["observe"], "sourceHash": ""}
        raw = json.dumps(d, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    else:
        text = Path(path).read_text(encoding="utf-8")
        raw = SOURCE_LINE.sub(lambda m: m.group(1).rstrip() + " ''", text, count=1)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _read_frontmatter(text: str):
    if not text.startswith("---\n"):
        return None
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return m.group(1) if m else None


def _carriers(asset_dir: Path):
    """返回 [(carrier, path, observe_dict|None)]"""
    out = []
    wj = asset_dir / "transformed" / "workflow.json"
    if wj.exists():
        d = json.loads(wj.read_text(encoding="utf-8"))
        out.append(("workflow_json", wj, d.get("observe")))
    sk = asset_dir / "SKILL.md"
    if sk.exists():
        fm = _read_frontmatter(sk.read_text(encoding="utf-8"))
        if fm:
            try:
                d = yaml.safe_load(fm) or {}
            except Exception:  # noqa: BLE001
                d = {}
            out.append(("skill_md", sk, d.get("observe")))
    return out


# ── 校验 ────────────────────────────────────────────────────────
def validate_observe(asset_key: str, ob: dict) -> None:
    if not isinstance(ob, dict):
        raise ContractError(asset_key, "observe", "不是对象")
    if str(ob.get("contractVersion")) != CONTRACT_VERSION:
        raise ContractError(asset_key, "observe.contractVersion",
                            f"不支持 {ob.get('contractVersion')!r}（支持 {CONTRACT_VERSION}）")
    if ob.get("assetKey") != asset_key:
        raise ContractError(asset_key, "observe.assetKey",
                            f"与路径不符，声明为 {ob.get('assetKey')!r}")
    if ob.get("runtime") not in ("engine", "host"):
        raise ContractError(asset_key, "observe.runtime", f"非法值 {ob.get('runtime')!r}")
    nodes = ob.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ContractError(asset_key, "observe.nodes", "缺失或为空")
    seen, last = set(), 0
    for i, n in enumerate(nodes):
        nid = n.get("nodeId")
        if not nid:
            raise ContractError(asset_key, "observe.nodes[].nodeId", f"第 {i+1} 项缺失")
        if nid in seen:
            raise ContractError(asset_key, "observe.nodes[].nodeId", f"重复 {nid}")
        seen.add(nid)
        seq = n.get("seq")
        if not isinstance(seq, int) or seq != last + 1:
            raise ContractError(asset_key, "observe.nodes[].seq", f"{nid} 处为 {seq}，应连续递增")
        last = seq
        if n.get("deliverableType") not in DELIVERABLE_TYPES:
            raise ContractError(asset_key, "observe.nodes[].deliverableType",
                                f"{nid} 非法值 {n.get('deliverableType')!r}")
        caps = n.get("capabilities") or {}
        for k in ("canReplace", "supportPause", "supportRerun"):
            if not isinstance(caps.get(k), bool):
                raise ContractError(asset_key, f"observe.nodes[].{k}", f"{nid} 缺布尔值")
    rep = ob.get("report")
    if not isinstance(rep, dict):
        raise ContractError(asset_key, "observe.report", "缺失")
    ev = set(rep.get("onEvents") or [])
    if not ev or not ev <= EVENTS:
        raise ContractError(asset_key, "observe.report.onEvents", f"非法事件 {sorted(ev - EVENTS)}")


# ── 扫描 ────────────────────────────────────────────────────────
def scan(root: Path = SKILL_ROOT) -> dict:
    registry, warnings, errors = {}, [], []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or any(x in str(d) for x in ("archive", "__pycache__", ".bak", ".tmp")):
            continue
        carriers = _carriers(d)
        present = [(c, p, ob) for c, p, ob in carriers if ob]
        if not present:
            continue
        if len(present) > 1:
            errors.append(ContractError(f"skill:{d.name}", "observe",
                                        f"双载体声明：{[c for c, _, _ in present]}"))
            continue
        carrier, path, ob = present[0]
        key = ob.get("assetKey") or f"skill:{d.name}"
        try:
            validate_observe(key, ob)
        except ContractError as e:
            errors.append(e)
            continue
        actual = compute_source_hash(path, carrier)
        declared = ob.get("sourceHash", "")
        registry[key] = {
            "assetKey": key,
            "assetType": key.split(":", 1)[0],
            "carrier": carrier,
            "runtime": ob["runtime"],
            "graphVersion": declared,
            "graphVersionActual": actual,
            "hashDrift": bool(declared) and declared != actual,
            "nodeTotal": len(ob["nodes"]),
            "pausableTotal": sum(1 for n in ob["nodes"] if n["capabilities"]["supportPause"]),
            "frozen": bool(_frozen_reason(key)),
            "frozenReason": _frozen_reason(key),
            "nodes": ob["nodes"],
            "report": ob.get("report"),
        }
        if declared and declared != actual:
            warnings.append({"assetKey": key, "code": "STALE_HASH",
                             "message": f"sourceHash 漂移：声明 {declared}，实际 {actual}"
                                        f"（运行 observe_hash.py --write 回写）"})
        if _frozen_reason(key):
            warnings.append({"assetKey": key, "code": "FROZEN", "message": _frozen_reason(key)})

        # agent 资产（同目录 agents/*.md）
        ad = d / "agents"
        if ad.is_dir():
            for ap in sorted(ad.glob("*.md")):
                fm = _read_frontmatter(ap.read_text(encoding="utf-8"))
                if not fm:
                    continue
                try:
                    aob = (yaml.safe_load(fm) or {}).get("observe")
                except Exception:  # noqa: BLE001
                    aob = None
                if not aob:
                    continue
                akey = aob.get("assetKey") or f"agent:{ap.stem}"
                try:
                    validate_observe(akey, aob)
                except ContractError as e:
                    errors.append(e)
                    continue
                a_actual = compute_source_hash(ap, "skill_md")
                a_declared = aob.get("sourceHash", "")
                registry[akey] = {
                    "assetKey": akey, "assetType": "agent", "carrier": "skill_md",
                    "runtime": aob["runtime"], "graphVersion": a_declared,
                    "graphVersionActual": a_actual,
                    "hashDrift": bool(a_declared) and a_declared != a_actual,
                    "nodeTotal": len(aob["nodes"]),
                    "pausableTotal": sum(1 for n in aob["nodes"] if n["capabilities"]["supportPause"]),
                    "frozen": False, "frozenReason": "", "nodes": aob["nodes"],
                    "report": aob.get("report"),
                }
                if a_declared and a_declared != a_actual:
                    warnings.append({"assetKey": akey, "code": "STALE_HASH",
                                     "message": f"sourceHash 漂移：声明 {a_declared}，实际 {a_actual}"})
    return {"registry": registry, "warnings": warnings, "errors": [str(e) for e in errors]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="", help="输出注册表 JSON 路径")
    ap.add_argument("--check", action="store_true", help="只校验")
    args = ap.parse_args()

    res = scan()
    reg = res["registry"]
    stats = {
        "assets": len(reg),
        "nodes": sum(v["nodeTotal"] for v in reg.values()),
        "engine": sum(1 for v in reg.values() if v["runtime"] == "engine"),
        "host": sum(1 for v in reg.values() if v["runtime"] == "host"),
        "frozen": sum(1 for v in reg.values() if v["frozen"]),
        "pausable": sum(v["pausableTotal"] for v in reg.values()),
        "warnings": len(res["warnings"]),
        "errors": len(res["errors"]),
    }
    print(json.dumps(stats, ensure_ascii=False))
    for e in res["errors"]:
        print("ERR", e, file=sys.stderr)
    if args.json:
        Path(args.json).write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"→ {args.json}")
    return 0 if not res["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
