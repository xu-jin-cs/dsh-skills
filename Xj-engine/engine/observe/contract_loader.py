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
# 控制通道枚举（唯一口径）：pause 由谁执行 / rerun 由谁拉起
CONTROL_PAUSE = {"boundary-block", "sigstop", "none"}
CONTROL_RERUN = {"session-resume", "flow-run", "none"}

# 范式层（2026-11-09）：五范式/编排策略/任务角色/风险类别的唯一真源在
# ~/.agents/agent-paradigms/paradigms.json；本文件只读取，不在此再定义一份枚举。
# 该文件缺失时：不带 paradigm 块的资产照常校验（向后兼容）；一旦声明了 paradigm，
# 则显式报错（功能禁用 + 可诊断），不做静默降级。
PARADIGM_FILE = Path.home() / ".agents" / "agent-paradigms" / "paradigms.json"
_PARADIGM_CACHE: dict | None = None


def paradigm_lexicon() -> dict:
    """返回 {paradigmIds, nodeModes, taskRoles, riskGuards}；缺失即 fail-fast。"""
    global _PARADIGM_CACHE
    if _PARADIGM_CACHE is None:
        if not PARADIGM_FILE.is_file():
            raise ContractError("(global)", "observe.paradigm",
                                f"范式层未安装：找不到 {PARADIGM_FILE}（五范式枚举唯一真源）")
        d = json.loads(PARADIGM_FILE.read_text(encoding="utf-8"))
        ctx = d.get("contextPolicyStandard") or {}
        _ctx_mem = ctx.get("memory") or {}
        _ctx_v = _ctx_mem.get("vector") or {}
        _ctx_ov = ctx.get("overflow") or {}
        _ctx_ho = ctx.get("handoff") or {}
        _PARADIGM_CACHE = {
            "paradigmIds": {p["id"] for p in d.get("paradigms") or []},
            "nodeModes": set((d.get("orchestrationStrategies") or {}).keys()),
            "taskRoles": set((d.get("taskRoles") or {}).keys()),
            "riskGuards": set((d.get("riskGuards") or {}).keys()),
            # 上下文策略枚举（第 13 段）同样只在此读取，不在代码里另写一份
            "compressionStrategies": set((ctx.get("compression") or {}).get("strategies") or {}),
            "dropPolicies": set((ctx.get("compression") or {}).get("dropPolicies") or []),
            "memoryTiers": set(_ctx_mem.get("tiers") or {}),
            "recallStrategies": set((_ctx_mem.get("recall") or {}).get("allowed") or []),
            "vectorMetrics": set(_ctx_v.get("metrics") or []),
            "overflowActions": set((_ctx_ov.get("actions") or {}).keys()),
            "escalateTargets": set(_ctx_ov.get("escalateTargets") or []),
            "alarmChannels": set((_ctx_ov.get("alarm") or {}).get("channels") or []),
            "alarmCodes": set((_ctx_ov.get("alarm") or {}).get("codes") or []),
            "handoffCarriers": set((_ctx_ho.get("carriers") or {}).keys()),
            "missingPolicies": set(_ctx_ho.get("missingPolicies") or []),
        }
    return _PARADIGM_CACHE

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


def _node_channel(asset_dir: Path) -> bool:
    """该资产是否真有**节点级**上报通道（SKILL.md 正文调用 observe_step.py）。

    声明 `report.onEvents` 里有 node_* 只证明"声明方说要报"，不证明"有东西真的在报"。
    """
    sk = asset_dir / "SKILL.md"
    try:
        return "observe_step.py" in sk.read_text(encoding="utf-8")
    except OSError:
        return False


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
    # 控制通道声明（2026-11-08 用户裁定 A：节点控制落点写进 workflow.json）
    # 只声明"每种动作由谁执行"，不重复声明 runtime（runtime 唯一真源仍在上面的 observe.runtime）
    ctl = ob.get("control")
    if ctl is not None:
        if not isinstance(ctl, dict):
            raise ContractError(asset_key, "observe.control", "不是对象")
        for k, allowed in (("pause", CONTROL_PAUSE), ("rerun", CONTROL_RERUN)):
            v = ctl.get(k)
            if v is not None and v not in allowed:
                raise ContractError(asset_key, f"observe.control.{k}",
                                    f"非法值 {v!r}（支持 {sorted(allowed)}）")
    _validate_paradigm(asset_key, ob, nodes)
    cp = ob.get("contextPolicy")
    if cp is not None:
        _validate_context_policy(asset_key, cp, paradigm_lexicon(), nodes)
    pc = ob.get("promptContract")
    if pc is not None:
        _validate_prompt_contract(asset_key, pc)


def _validate_paradigm(asset_key: str, ob: dict, nodes: list[dict]) -> None:
    """范式块与节点编排属性（2026-11-09）。**全部可选**，缺省不报错（向后兼容）。

    声明的枚举唯一真源是 ~/.agents/agent-paradigms/paradigms.json；本函数只做引用完整性校验。
    """
    ids = [n.get("nodeId") for n in nodes]
    idset = set(ids)
    seq_of = {n.get("nodeId"): n.get("seq") for n in nodes}

    has_orch = any(n.get("mode") is not None for n in nodes)
    par = ob.get("paradigm")
    if par is not None and not isinstance(par, dict):
        raise ContractError(asset_key, "observe.paradigm", "不是对象")
    if par is not None or has_orch:
        lex = paradigm_lexicon()          # 只在真的用到范式能力时才要求范式层存在
    else:
        lex = None

    # 1) 节点编排属性
    groups: dict[str, list[str]] = {}
    for n in nodes:
        nid = n.get("nodeId")
        mode = n.get("mode")
        if mode is not None:
            if mode not in lex["nodeModes"]:
                raise ContractError(asset_key, "observe.nodes[].mode",
                                    f"{nid} 非法值 {mode!r}（支持 {sorted(lex['nodeModes'])}）")
            if mode == "optional_parallel":
                g = n.get("parallelGroup")
                if not g:
                    raise ContractError(asset_key, "observe.nodes[].parallelGroup",
                                        f"{nid} mode=optional_parallel 必须声明 parallelGroup")
                groups.setdefault(g, []).append(nid)
            if mode == "fallback_hook":
                fo = n.get("fallbackOf")
                if not fo:
                    raise ContractError(asset_key, "observe.nodes[].fallbackOf",
                                        f"{nid} mode=fallback_hook 必须声明 fallbackOf")
                if fo not in idset:
                    raise ContractError(asset_key, "observe.nodes[].fallbackOf",
                                        f"{nid} 指向不存在的节点 {fo!r}")
                if seq_of.get(fo, 0) > seq_of.get(nid, 0):
                    raise ContractError(asset_key, "observe.nodes[].fallbackOf",
                                        f"{nid} 兜底的节点 {fo} 在其之后（应在之前）")
        for k in ("stateIn", "stateOut"):
            v = n.get(k)
            if v is not None and (not isinstance(v, list)
                                  or not all(isinstance(x, str) and x for x in v)):
                raise ContractError(asset_key, f"observe.nodes[].{k}",
                                    f"{nid} 必须是字符串数组")
        if "acceptance" in n and not isinstance(n.get("acceptance"), str):
            raise ContractError(asset_key, "observe.nodes[].acceptance", f"{nid} 必须是字符串")
    for g, members in groups.items():
        if len(members) < 2:
            raise ContractError(asset_key, "observe.nodes[].parallelGroup",
                                f"并行组 {g!r} 只有 {len(members)} 个节点（至少 2 个）")

    # 2) 范式块
    if par is None:
        return
    pid = par.get("id")
    if pid not in lex["paradigmIds"]:
        raise ContractError(asset_key, "observe.paradigm.id",
                            f"非法值 {pid!r}（支持 {sorted(lex['paradigmIds'])}）")
    role = par.get("taskRole")
    if role is not None and role not in lex["taskRoles"]:
        raise ContractError(asset_key, "observe.paradigm.taskRole",
                            f"非法值 {role!r}（支持 {sorted(lex['taskRoles'])}）")
    anchor = par.get("deliverableAnchor")
    if anchor is not None and anchor not in idset:
        raise ContractError(asset_key, "observe.paradigm.deliverableAnchor",
                            f"指向不存在的节点 {anchor!r}")
    guards = par.get("riskGuards")
    if guards is not None:
        if not isinstance(guards, list):
            raise ContractError(asset_key, "observe.paradigm.riskGuards", "必须是数组")
        bad = set(guards) - lex["riskGuards"]
        if bad:
            raise ContractError(asset_key, "observe.paradigm.riskGuards",
                                f"非法类别 {sorted(bad)}（支持 {sorted(lex['riskGuards'])}）")
    metrics = par.get("metrics")
    if metrics is not None and not isinstance(metrics, dict):
        raise ContractError(asset_key, "observe.paradigm.metrics", "必须是对象")


def _validate_context_policy(asset_key: str, cp: dict, lex: dict,
                             nodes: list[dict] | None = None) -> None:
    """第 13 段 contextPolicy（2026-11-09）。**可选**；声明了即严格校验。

    只校验结构/枚举/区间与跨字段一致性；不校验数值是否"合理"（那属标定，留人工）。
    """
    if not isinstance(cp, dict):
        raise ContractError(asset_key, "observe.contextPolicy", "不是对象")
    for blk in ("budget", "compression", "memory", "overflow", "handoff"):
        if not isinstance(cp.get(blk), dict):
            raise ContractError(asset_key, f"observe.contextPolicy.{blk}", "缺失或不是对象")

    b = cp["budget"]
    for k in ("outputReserveTokens", "systemPromptTokens"):
        v = b.get(k)
        if not isinstance(v, int) or v < 0:
            raise ContractError(asset_key, f"observe.contextPolicy.budget.{k}",
                                f"必须是非负整数，实际 {v!r}")
    win = b.get("contextWindowTokens")
    if win is not None and (not isinstance(win, int) or win < 1024):
        raise ContractError(asset_key, "observe.contextPolicy.budget.contextWindowTokens",
                            f"必须是 null 或 >=1024 的整数，实际 {win!r}")
    for k in ("safetyMarginRatio", "degradeAtRatio"):
        v = b.get(k)
        if not isinstance(v, (int, float)) or not (0 < v <= 1):
            raise ContractError(asset_key, f"observe.contextPolicy.budget.{k}",
                                f"必须是 (0,1] 的数，实际 {v!r}")
    if not isinstance(b.get("calibrated"), bool):
        raise ContractError(asset_key, "observe.contextPolicy.budget.calibrated", "必须是布尔值")
    if b.get("calibrated") is True and not str(b.get("calibrationEvidence") or "").strip():
        raise ContractError(asset_key, "observe.contextPolicy.budget.calibrationEvidence",
                            "calibrated=true 时必须写标定依据（禁止把默认值冒充已标定）")
    if win is not None:
        eff = int(win * (1 - b["safetyMarginRatio"])) - b["outputReserveTokens"] - b["systemPromptTokens"]
        if eff <= 0:
            raise ContractError(asset_key, "observe.contextPolicy.budget",
                                f"有效预算 {eff} <= 0（窗口 {win} − 输出预留 − 系统占用 − 安全余量）")

    c = cp["compression"]
    strat = c.get("strategy")
    if strat not in lex["compressionStrategies"]:
        raise ContractError(asset_key, "observe.contextPolicy.compression.strategy",
                            f"非法值 {strat!r}（支持 {sorted(lex['compressionStrategies'])}）")
    fb = c.get("fallbackStrategy")
    if fb is not None and fb not in lex["compressionStrategies"]:
        raise ContractError(asset_key, "observe.contextPolicy.compression.fallbackStrategy",
                            f"非法值 {fb!r}")
    trig = c.get("triggerAtRatio")
    if strat != "none":
        if not isinstance(trig, (int, float)):
            raise ContractError(asset_key, "observe.contextPolicy.compression.triggerAtRatio",
                                f"strategy={strat} 时必填")
        if trig > b["degradeAtRatio"]:
            raise ContractError(asset_key, "observe.contextPolicy.compression.triggerAtRatio",
                                f"{trig} 大于 degradeAtRatio {b['degradeAtRatio']}（永远触发不到）")
    if strat == "summary" and not isinstance(c.get("summaryMaxTokens"), int):
        raise ContractError(asset_key, "observe.contextPolicy.compression.summaryMaxTokens",
                            "strategy=summary 时必填整数")
    dp = c.get("dropPolicy")
    if dp is not None and dp not in lex["dropPolicies"]:
        raise ContractError(asset_key, "observe.contextPolicy.compression.dropPolicy",
                            f"非法值 {dp!r}（支持 {sorted(lex['dropPolicies'])}）")

    m = cp["memory"]
    tiers = m.get("enabledTiers")
    if not isinstance(tiers, list) or not tiers:
        raise ContractError(asset_key, "observe.contextPolicy.memory.enabledTiers", "必须是非空数组")
    if "working" not in tiers:
        raise ContractError(asset_key, "observe.contextPolicy.memory.enabledTiers",
                            "working 层恒开，不能省略")
    bad = set(tiers) - lex["memoryTiers"]
    if bad:
        raise ContractError(asset_key, "observe.contextPolicy.memory.enabledTiers",
                            f"非法层 {sorted(bad)}（支持 {sorted(lex['memoryTiers'])}）")
    r = m.get("recall") or {}
    if r.get("strategy") not in lex["recallStrategies"]:
        raise ContractError(asset_key, "observe.contextPolicy.memory.recall.strategy",
                            f"非法值 {r.get('strategy')!r}")
    vec = m.get("vector")
    if vec is not None:
        if not isinstance(vec, dict) or not isinstance(vec.get("enabled"), bool):
            raise ContractError(asset_key, "observe.contextPolicy.memory.vector",
                                "必须是对象且 enabled 为布尔值")
        if vec.get("metric") not in lex["vectorMetrics"]:
            raise ContractError(asset_key, "observe.contextPolicy.memory.vector.metric",
                                f"非法值 {vec.get('metric')!r}")
        if vec["enabled"]:
            # 启用即必须有落地参数；只声明不落地=假功能
            for k in ("collection", "embeddingModel", "dim"):
                if vec.get(k) in (None, ""):
                    raise ContractError(asset_key, f"observe.contextPolicy.memory.vector.{k}",
                                        "enabled=true 时必填")

    # ── 溢出降级与告警（禁止静默截断） ─────────────────────────
    ov = cp["overflow"]
    acts = []
    for k in ("onBudgetExceeded", "onCompressionExhausted"):
        v = ov.get(k)
        if v not in lex["overflowActions"]:
            raise ContractError(asset_key, f"observe.contextPolicy.overflow.{k}",
                                f"非法值 {v!r}（支持 {sorted(lex['overflowActions'])}）")
        acts.append(v)
    et = ov.get("escalateTo")
    if et not in lex["escalateTargets"]:
        raise ContractError(asset_key, "observe.contextPolicy.overflow.escalateTo",
                            f"非法值 {et!r}（支持 {sorted(lex['escalateTargets'])}）")
    if "escalate" in acts and et == "none":
        raise ContractError(asset_key, "observe.contextPolicy.overflow.escalateTo",
                            "动作含 escalate 时必须指定升级对象（human/orchestrator）")
    for k in ("hardStop", "recordEvidence"):
        if not isinstance(ov.get(k), bool):
            raise ContractError(asset_key, f"observe.contextPolicy.overflow.{k}", "必须是布尔值")
    al = ov.get("alarm")
    if not isinstance(al, dict) or not isinstance(al.get("enabled"), bool):
        raise ContractError(asset_key, "observe.contextPolicy.overflow.alarm",
                            "必须是对象且 enabled 为布尔值")
    if "truncate" in acts and al["enabled"] is not True:
        raise ContractError(asset_key, "observe.contextPolicy.overflow.alarm.enabled",
                            "动作含 truncate 时必须开启告警（禁止静默截断）")
    ch = al.get("channels")
    if not isinstance(ch, list) or not ch or set(ch) - lex["alarmChannels"]:
        raise ContractError(asset_key, "observe.contextPolicy.overflow.alarm.channels",
                            f"必须是非空数组，取值 {sorted(lex['alarmChannels'])}")
    codes = al.get("codes")
    if not isinstance(codes, list) or not codes or set(codes) - lex["alarmCodes"]:
        raise ContractError(asset_key, "observe.contextPolicy.overflow.alarm.codes",
                            f"必须是非空数组，取值 {sorted(lex['alarmCodes'])}")
    thr = al.get("throttleSec")
    if not isinstance(thr, int) or thr < 0:
        raise ContractError(asset_key, "observe.contextPolicy.overflow.alarm.throttleSec",
                            "必须是非负整数")

    # ── 跨节点交接载体 ────────────────────────────────────────
    ho = cp["handoff"]
    carrier = ho.get("carrier")
    if carrier not in lex["handoffCarriers"]:
        raise ContractError(asset_key, "observe.contextPolicy.handoff.carrier",
                            f"非法值 {carrier!r}（支持 {sorted(lex['handoffCarriers'])}）")
    if carrier == "file":
        pat = ho.get("pathPattern")
        if not isinstance(pat, str) or "{" not in pat:
            raise ContractError(asset_key, "observe.contextPolicy.handoff.pathPattern",
                                "carrier=file 时必须给可参数化路径（含 {from}/{to}）")
    hf = ho.get("fields")
    if not isinstance(hf, list) or not all(isinstance(x, str) and x for x in hf):
        raise ContractError(asset_key, "observe.contextPolicy.handoff.fields", "必须是字符串数组")
    if carrier != "none":
        if not hf:
            raise ContractError(asset_key, "observe.contextPolicy.handoff.fields",
                                f"carrier={carrier} 时 fields 不能为空")
        if nodes is not None:
            avail = {f for n in nodes for f in (n.get("stateOut") or [])}
            unknown = sorted(set(hf) - avail)
            if unknown:
                raise ContractError(asset_key, "observe.contextPolicy.handoff.fields",
                                    f"交接字段不在任何节点 stateOut：{unknown}")
    mb = ho.get("maxBytes")
    if not isinstance(mb, int) or mb <= 0:
        raise ContractError(asset_key, "observe.contextPolicy.handoff.maxBytes", "必须是正整数")
    if not isinstance(ho.get("checksum"), bool):
        raise ContractError(asset_key, "observe.contextPolicy.handoff.checksum", "必须是布尔值")
    if ho.get("onMissing") not in lex["missingPolicies"]:
        raise ContractError(asset_key, "observe.contextPolicy.handoff.onMissing",
                            f"非法值 {ho.get('onMissing')!r}（支持 {sorted(lex['missingPolicies'])}）")
    env = ho.get("envelope")
    req = (env or {}).get("requiredFields") if isinstance(env, dict) else None
    if not isinstance(req, list) or not {"from", "to", "ts"} <= set(req):
        raise ContractError(asset_key, "observe.contextPolicy.handoff.envelope.requiredFields",
                            "必须包含 from/to/ts（交接必须可追溯）")


def check_context_policy(asset_key: str, cp: dict,
                         nodes: list[dict] | None = None) -> None:
    """公开入口：范式层 CLI（paradigm_match.py）复用同一校验实现，禁止客户端再写一份。"""
    _validate_context_policy(asset_key, cp, paradigm_lexicon(), nodes)


def check_prompt_contract(asset_key: str, pc: dict) -> None:
    """公开入口：范式层 CLI 复用同一校验实现。"""
    _validate_prompt_contract(asset_key, pc)


def _validate_prompt_contract(asset_key: str, pc: dict) -> None:
    """第 14 段 promptContract（2026-11-09，系统提示词宪法）。**可选**；声明了即严格校验。

    只校验"写没写全、写没写死"（空=允许、缺项=失败），语义质量留软层。
    """
    if not isinstance(pc, dict):
        raise ContractError(asset_key, "observe.promptContract", "不是对象")
    role = pc.get("agent_role")
    if not isinstance(role, str) or not role.strip():
        raise ContractError(asset_key, "observe.promptContract.agent_role", "必须是非空字符串")
    cg = pc.get("core_goal")
    if not isinstance(cg, dict):
        raise ContractError(asset_key, "observe.promptContract.core_goal", "必须是对象")
    for k in ("statement", "done_when"):
        if not isinstance(cg.get(k), str) or not cg[k].strip():
            raise ContractError(asset_key, f"observe.promptContract.core_goal.{k}",
                                "必须非空（done_when 要可机械复判）")
    acts = pc.get("allow_actions")
    if not isinstance(acts, list) or not acts or not all(isinstance(a, str) and a for a in acts):
        raise ContractError(asset_key, "observe.promptContract.allow_actions",
                            "必须是非空字符串数组（空数组=允许一切）")
    if len(set(acts)) != len(acts):
        raise ContractError(asset_key, "observe.promptContract.allow_actions", "存在重复项")
    tools = pc.get("tool_spec")
    if not isinstance(tools, list) or not tools:
        raise ContractError(asset_key, "observe.promptContract.tool_spec", "必须是非空数组")
    names = []
    for i, t in enumerate(tools):
        if not isinstance(t, dict):
            raise ContractError(asset_key, "observe.promptContract.tool_spec", f"第 {i+1} 项不是对象")
        n = t.get("name")
        if not isinstance(n, str) or not n:
            raise ContractError(asset_key, "observe.promptContract.tool_spec[].name", f"第 {i+1} 项缺 name")
        if n not in acts:
            raise ContractError(asset_key, "observe.promptContract.tool_spec[].name",
                                f"工具 {n!r} 不在 allow_actions 中（声明了却不准用）")
        for k in ("when", "how"):
            if not isinstance(t.get(k), str) or not t[k].strip():
                raise ContractError(asset_key, f"observe.promptContract.tool_spec.{k}",
                                    f"{n} 缺 {k}（何时用/怎么用）")
        if not isinstance(t.get("args"), dict):
            raise ContractError(asset_key, "observe.promptContract.tool_spec.args",
                                f"{n} 的 args 必须是对象（参数约束）")
        names.append(n)
    if len(set(names)) != len(names):
        raise ContractError(asset_key, "observe.promptContract.tool_spec[].name", "工具名重复")
    eh = pc.get("error_handling")
    if not isinstance(eh, dict):
        raise ContractError(asset_key, "observe.promptContract.error_handling", "必须是对象")
    for k in ("failure", "timeout", "exception"):
        if not isinstance(eh.get(k), str) or not eh[k].strip():
            raise ContractError(asset_key, f"observe.promptContract.error_handling.{k}",
                                "失败/超时/异常三情形都必须写（缺一即编造兜底）")
    shots = pc.get("few_shot_examples")
    if not isinstance(shots, list) or not (2 <= len(shots) <= 5):
        raise ContractError(asset_key, "observe.promptContract.few_shot_examples",
                            f"必须是 2~5 条，实际 {len(shots) if isinstance(shots, list) else 'N/A'}")
    kinds = set()
    for s in shots:
        if not isinstance(s, dict) or s.get("kind") not in ("format", "refusal", "boundary"):
            raise ContractError(asset_key, "observe.promptContract.few_shot_examples[].kind",
                                f"非法 kind：{s.get('kind') if isinstance(s, dict) else s!r}")
        for k in ("input", "output"):
            if not isinstance(s.get(k), str) or not s[k].strip():
                raise ContractError(asset_key, f"observe.promptContract.few_shot_examples.{k}", "必须非空")
        kinds.add(s["kind"])
    missing = {"format", "refusal", "boundary"} - kinds
    if missing:
        raise ContractError(asset_key, "observe.promptContract.few_shot_examples",
                            f"样例必须覆盖格式/拒答/边界，缺 {sorted(missing)}")
    iso = pc.get("isolate_prompt_rule")
    if not isinstance(iso, bool):
        raise ContractError(asset_key, "observe.promptContract.isolate_prompt_rule", "必须是布尔值")
    stable = pc.get("stable_sections")
    dyn = pc.get("dynamic_sections")
    for name, v in (("stable_sections", stable), ("dynamic_sections", dyn)):
        if not isinstance(v, list) or not v or not all(isinstance(x, str) and x for x in v):
            raise ContractError(asset_key, f"observe.promptContract.{name}", "必须是非空字符串数组")
    if iso:
        dup = set(stable) & set(dyn)
        if dup:
            raise ContractError(asset_key, "observe.promptContract",
                                f"分离铁律开启时同一段不能既稳定又动态：{sorted(dup)}")


def prompt_contract_warnings(asset_key: str, ob: dict) -> list[dict]:
    pc = ob.get("promptContract")
    if not isinstance(pc, dict):
        return []
    out = []
    if pc.get("isolate_prompt_rule") is False:
        out.append({"assetKey": asset_key, "code": "PROMPT_SEPARATION_OFF",
                    "message": "isolate_prompt_rule=false：稳定规则与动态上下文混在一起，"
                               "缓存命中率与注入防护双重失效"})
    return out


def context_policy_warnings(asset_key: str, ob: dict) -> list[dict]:
    """第 13 段的运行期体检告警（不阻断入库，但必须在 sync 响应里当场看见）。"""
    cp = ob.get("contextPolicy")
    if not isinstance(cp, dict):
        return []
    out = []
    b = cp.get("budget") or {}
    if b.get("calibrated") is not True or b.get("contextWindowTokens") is None:
        out.append({"assetKey": asset_key, "code": "BUDGET_UNCALIBRATED",
                    "message": f"上下文窗口未标定（window={b.get('contextWindowTokens')!r}，"
                               f"calibrated={b.get('calibrated')!r}）：默认值不是实测值，"
                               f"接入前需按模型实测替换并写 calibrationEvidence"})
    vec = (cp.get("memory") or {}).get("vector") or {}
    if vec.get("enabled") is True:
        out.append({"assetKey": asset_key, "code": "VECTOR_RESERVED",
                    "message": "memory.vector.enabled=true，但向量检索属 RAG 工程且尚未对接："
                               "该能力当前不生效（声明先行，禁止当成可检索）"})
    rec = (cp.get("memory") or {}).get("recall") or {}
    if rec.get("strategy") in ("embedding", "hybrid") and vec.get("enabled") is not True:
        out.append({"assetKey": asset_key, "code": "RECALL_WITHOUT_VECTOR",
                    "message": f"recall.strategy={rec.get('strategy')} 依赖向量层，"
                               f"但 memory.vector.enabled=false：召回将退化或为空"})
    return out


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
            "control": ob.get("control") or {},
            "paradigm": ob.get("paradigm") or {},
            "contextPolicy": ob.get("contextPolicy") or {},
            "promptContract": ob.get("promptContract") or {},
        }
        if declared and declared != actual:
            warnings.append({"assetKey": key, "code": "STALE_HASH",
                             "message": f"sourceHash 漂移：声明 {declared}，实际 {actual}"
                                        f"（运行 observe_hash.py --write 回写）"})
        if _frozen_reason(key):
            warnings.append({"assetKey": key, "code": "FROZEN", "message": _frozen_reason(key)})
        # 声明-事实一致性：声明了节点级事件，却没有任何节点级上报通道（SKILL.md 未调
        # observe_step.py）。这类资产在平台上会"任务有行、节点全 pending"，属声明层说谎。
        # 控制声明与节点能力一致性（机制层唯一判定，此处只做声明体检）
        _ctl = ob.get("control") or {}
        if _ctl.get("pause") and not any(
                (n.get("capabilities") or {}).get("supportPause") for n in ob["nodes"]):
            warnings.append({"assetKey": key, "code": "CONTROL_INCONSISTENT",
                             "message": "声明了 control.pause，但没有任何节点 supportPause=true"})
        if _ctl.get("rerun") and not any(
                (n.get("capabilities") or {}).get("supportRerun") for n in ob["nodes"]):
            warnings.append({"assetKey": key, "code": "CONTROL_INCONSISTENT",
                             "message": "声明了 control.rerun，但没有任何节点 supportRerun=true"})
        if set((ob.get("report") or {}).get("onEvents") or []) & EVENTS and not _node_channel(d):
            warnings.append({"assetKey": key, "code": "CONTRACT_MISMATCH",
                             "message": "声明了节点级事件但 SKILL.md 未调用 observe_step.py"
                                        "（节点级上报无通道，面板会显示节点全 pending）"})
        # 范式/编排一致性体检（只警告，不改变既有资产能否入库）
        _par = ob.get("paradigm") or {}
        _modes = [n.get("mode") for n in ob["nodes"] if n.get("mode")]
        if _par.get("id") in ("plan_execute", "multi_agent") and not _modes:
            warnings.append({"assetKey": key, "code": "PARADIGM_INCOMPLETE",
                             "message": f"声明了 paradigm={_par['id']} 但没有任何 nodes[].mode"
                                        f"（控制台只能按默认串行渲染）"})
        _has_state = any(n.get("stateIn") or n.get("stateOut") for n in ob["nodes"])
        if _modes and not _has_state:
            warnings.append({"assetKey": key, "code": "ORCHESTRATION_NO_STATE",
                             "message": "声明了编排属性但无 stateIn/stateOut（显式状态契约缺失）"})
        _avail: set[str] = set()
        for n in sorted(ob["nodes"], key=lambda x: x.get("seq") or 0):
            for fld in (n.get("stateIn") or []):
                if fld not in _avail:
                    warnings.append({"assetKey": key, "code": "STATE_FIELD_UNREACHABLE",
                                     "message": f"{n.get('nodeId')} 读字段 {fld} 但无上游 stateOut 提供"})
            _avail |= set(n.get("stateOut") or [])
        warnings.extend(context_policy_warnings(key, ob))
        warnings.extend(prompt_contract_warnings(key, ob))

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
                    "paradigm": aob.get("paradigm") or {},
                    "contextPolicy": aob.get("contextPolicy") or {},
                    "promptContract": aob.get("promptContract") or {},
                }
                if a_declared and a_declared != a_actual:
                    warnings.append({"assetKey": akey, "code": "STALE_HASH",
                                     "message": f"sourceHash 漂移：声明 {a_declared}，实际 {a_actual}"})
                warnings.extend(context_policy_warnings(akey, aob))
                warnings.extend(prompt_contract_warnings(akey, aob))
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
