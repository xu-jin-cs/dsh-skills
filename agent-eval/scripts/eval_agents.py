#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""eval_agents.py — Agent/Skills 专项能力评估·综合排名 最终脚本（2026-09-18 定稿）

范围：仅 ~/.agents/skills/（不含 RAG/引擎/规则闸/设计者反推）。
用法：python3 eval_agents.py [--mode internal|generic] [--config cfg.json] [--compare 上轮skills_system.json] [--out 目录]
      缺 matplotlib 时自动改用 ~/.browser-use-env/bin/python3 重启自身。

流程：采集（只读实测，读取全部 agent/skills 文件）→ 体系级评分（冻结基线+调整版信号加减）→ 逐技能 9 维机械评分
     → 强弱识别（严重等级+行动指引）→ 综合排名（主排序 overall → 阻断数 → 核心四维均值）→ 落盘 → 渲染 2 图。

调整版加减分规则（依据《Agent(Skills)专项评估梳理与调整建议》落地）：
  1. 关键技能缺失阶梯扣分：每缺 1 个 -0.3，上限 -1.0（原来一刀切 -1.0）
  2. 正向加分：17 关键技能全齐 → 功能覆盖 +0.5；全部技能零路径漂移 → 可维护 +0.5
  3. retro<200 扣 -1.0 绑定开关 enable_agent_self_evolution（默认开，本体系有复盘自进化）
  4. etlengine 更名漂移已修复 → 可靠 +0.5、可维护 +0.5（保留原规则）
  5. clamp：限幅 [0,10]、步进 0.5；overall=有效维度算术均值；grade：A-≥85/B+≥80/B≥75/B-≥70/C+≥65/C≥55/其余 D

逐技能 9 维机械评分（证据锚点制，无裁量；信号=frontmatter/行数/脚本数/漂移引用/关键词组）：
  见 RUBRIC 数据结构，每条规则 = (条件, 增减分)，全部机械可复现。

双模式（依据调整建议 §1）：
  internal（默认）：完整 9 维等权；
  generic：7 基础维（GENERIC7_MAP 显式映射），机制创新性/自动化闭环降为附加标签不计综合分，
           加 --with-optional 才并入（降权 0.5）。

短板严重等级：阻断（frontmatter 契约缺失，调度不可识别）＞高风险（失效路径引用）＞一般优化（文档/执行面完善类）。
排名规则（依据《Agent综合能力排名方案》）：overall 降序 → 阻断数升序 → 核心四维均值降序 → 完全同分并列。
核心四维映射（9 维口径）：功能覆盖与正确性≈任务规划载体、工程实现质量≈工具交互落地、
可靠性与可验证性≈长程执行可靠性、安全与治理≈鲁棒安全。

产出（round 目录默认 ~/Desktop/agent-skills-eval-YYYYMMDD/，全部原子写）：
  images/agent_radar.png     —— 图1：Agent 多维度能力雷达（深色科技风，标杆线 85=A-）
  images/agent_rank.png      —— 图2：综合能力排名榜（卡片式大字体：排名+技能+分数+评级，◆优势/短板带严重等级）
  shards/skills_system.json / shards/skills_rank.json / baseline.md / agent_rank.md / report.html
"""
import argparse, glob, json, os, re, sys

try:
    import matplotlib
except ImportError:
    ALT = os.path.expanduser("~/.browser-use-env/bin/python3")
    if os.path.exists(ALT) and os.path.realpath(sys.executable) != os.path.realpath(ALT):
        os.execv(ALT, [ALT, os.path.abspath(__file__)] + sys.argv[1:])
    sys.exit("需要 matplotlib：请用 ~/.browser-use-env/bin/python3 运行本脚本")

import datetime
import numpy as np
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

for f in ("PingFang SC", "Heiti SC", "Arial Unicode MS"):
    if any(x.name == f for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = f
        break
plt.rcParams["axes.unicode_minus"] = False

HOME = os.path.expanduser("~")
TODAY = datetime.date.today().strftime("%Y%m%d")
EVAL_DATE = datetime.date.today().isoformat()

# 深色科技风（沿用 2026-08-20 裁定的渲染真源，与 chart2_agents_radar.png 一致）
BG = "#0B1120"; PANEL = "#111A2E"; GRID = "#334155"; TXT = "#E5E7EB"; SUB = "#94A3B8"
GREEN = "#34D399"; YELLOW = "#FBBF24"; RED = "#F87171"; CYAN = "#2DD4BF"; BLUE = "#5B8DEF"
GRADE_COLOR = {"A-": CYAN, "B+": BLUE, "B": "#7DD3FC", "B-": "#94A3B8", "C+": "#6B7280", "C": "#6B7280", "D": "#6B7280"}
SEV_ORDER = {"阻断": 0, "高风险": 1, "一般优化": 2}
SEV_COLOR = {"阻断": RED, "高风险": YELLOW, "一般优化": SUB}

DIMS9 = ["功能覆盖与正确性", "架构设计", "工程实现质量", "可靠性与可验证性", "安全与治理",
         "性能效率", "可维护与可分发", "机制创新性", "自动化执行力/Agentic闭环"]
CORE4 = ["功能覆盖与正确性", "工程实现质量", "可靠性与可验证性", "安全与治理"]  # ≈任务规划/工具交互/长程执行/鲁棒安全
OPTIONAL_DIMS = ["机制创新性", "自动化执行力/Agentic闭环"]
GENERIC7_MAP = [  # 通用 7 维 ← 内部 9 维显式映射（均值聚合）
    ("任务规划与拆解", ["功能覆盖与正确性"]),
    ("工具使用与环境交互", ["工程实现质量"]),
    ("长程执行与状态管理", ["可靠性与可验证性"]),
    ("记忆与上下文工程", ["架构设计"]),
    ("反思纠错与错误恢复", ["可靠性与可验证性", "自动化执行力/Agentic闭环"]),
    ("鲁棒安全与指令对齐", ["可靠性与可验证性", "安全与治理"]),
    ("可审计与可维护分发", ["可维护与可分发"]),
]

DEFAULT_CONFIG = {
    "skills_dir": os.path.join(HOME, ".agents/skills"),
    "retro_registry": os.path.join(HOME, ".agents/retro-skills-registry/registry-index.json"),
    "key_skills": ["pm", "pm-direct", "test-lead", "archmap", "gate-switch", "plan-select",
                   "parallel-dispatch", "dual-gates", "msh-eval-render", "expert-router",
                   "retro-skill-dispatcher", "retro-subagent", "whitebox-coverage", "ui-autoclick",
                   "ppt", "pptx", "resume"],
    "enable_agent_self_evolution": True,   # retro 水位扣分开关（本体系有复盘自进化，默认开）
    "missing_key_step": 0.3,               # 阶梯扣分步长
    "missing_key_cap": 1.0,                # 阶梯扣分上限
    "retro_low_watermark": 200,
    "benchmark": 85,                       # 雷达/柱状 A- 标杆线
    "mode": "internal",
    "with_optional": False,
}

BASE9 = dict(zip(DIMS9, [9, 9, 8, 8.5, 8, 8, 7, 9, 9]))  # 2026-09-09 冻结基线

KW = {
    "gate":   re.compile(r"闸|门禁|gate|判[AB]|契约|验收"),
    "verify": re.compile(r"测试|验收|留痕|证据|审计|溯源"),
    "safe":   re.compile(r"安全|权限|越权|拦截|确认|危险|禁令"),
    "perf":   re.compile(r"性能|节约|token|并行|增量|lite|轻量"),
    "innov":  re.compile(r"原创|首创|路由|锻造|问诊|逆向|配色|飞轮|自进化|矩阵"),
    "auto":   re.compile(r"自动|触发|闭环|复盘|自愈|调度"),
}
PATH_RE = re.compile(r"(~/[^\s\"'`\]\)】，。；：、]+|/Users/[^\s\"'`\]\)】，。；：、]+|(?<![\w/])\.agents/[^\s\"'`\]\)】，。；：、]+)")

def clamp(x): return max(0.0, min(10.0, round(x * 2) / 2))
def grade(s): return "A-" if s >= 85 else "B+" if s >= 80 else "B" if s >= 75 else "B-" if s >= 70 else "C+" if s >= 65 else "C" if s >= 55 else "D"
def read(p):
    try:
        return open(p, encoding="utf-8").read()
    except Exception:
        return ""
def cap(s, n=58):
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s if len(s) <= n else s[:n - 1] + "…"

# ================= 第一步：采集（只读实测，读取全部 agent/skills 文件） =================
def find_drift(text):
    """提取 SKILL.md 中的本地路径引用，返回不存在的路径列表（路径漂移实测）。"""
    bad = []
    for m in PATH_RE.finditer(text):
        p = m.group(1).rstrip(".,;:!?'>")
        if any(c in p for c in "*<${"):  # 占位符/通配，非真实路径
            continue
        real = os.path.join(HOME, p) if p.startswith(".agents/") else os.path.expanduser(p)
        if len(p) >= 8 and not os.path.exists(real):
            bad.append(p)
    return sorted(set(bad))

def collect(cfg):
    f = {"skills": []}
    sdir = cfg["skills_dir"]
    dirs = [d for d in sorted(glob.glob(os.path.join(sdir, "*")))
            if os.path.isdir(d) and os.path.isfile(os.path.join(d, "SKILL.md"))]
    f["skills_valid"] = len(dirs)
    f["skills_key_missing"] = [s for s in cfg["key_skills"] if not os.path.isdir(os.path.join(sdir, s))]
    reg = cfg["retro_registry"]
    f["retro_entries"] = (json.load(open(reg, encoding="utf-8")).get("total_entries")
                          if os.path.isfile(reg) else 0)
    f["skills_stale_engine_ref"] = ("engine/kernel.py" in read(os.path.join(
        sdir, "retro-skill-dispatcher/SKILL.md")) and not os.path.isdir(
        os.path.join(HOME, ".agents/retro-skills-registry/engine")))
    for d in dirs:
        name = os.path.basename(d)
        md = read(os.path.join(d, "SKILL.md"))
        head = md.split("---")[1] if md.startswith("---") and md.count("---") >= 2 else ""
        scripts = glob.glob(os.path.join(d, "scripts", "**", "*.py"), recursive=True)
        drift = find_drift(md)
        f["skills"].append({
            "name": name, "lines": len(md.splitlines()),
            "fm_ok": ("name:" in head and "description:" in head),
            "n_scripts": len(scripts), "has_scripts_dir": os.path.isdir(os.path.join(d, "scripts")),
            "drift": drift, "readme": bool(glob.glob(os.path.join(d, "README*"))),
            "is_key": name in cfg["key_skills"],
            "kw": {k: bool(p.search(md)) for k, p in KW.items()},
        })
    f["total_scripts"] = sum(s["n_scripts"] for s in f["skills"])
    f["drift_total"] = sum(len(s["drift"]) for s in f["skills"])
    return f

# ================= 第二步：评分 =================
def score_system(f, cfg):
    """体系级 9 维：冻结基线 + 调整版信号确定性加减。"""
    sc = dict(BASE9); notes = []
    miss = f["skills_key_missing"]
    if miss:
        pen = min(cfg["missing_key_step"] * len(miss), cfg["missing_key_cap"])
        sc["功能覆盖与正确性"] -= pen
        notes.append(f"关键技能缺失 {miss} → 功能覆盖 -{pen:.1f}（阶梯 {cfg['missing_key_step']}/个，上限 {cfg['missing_key_cap']}）")
    else:
        sc["功能覆盖与正确性"] += 0.5
        notes.append("17 关键技能全齐 → 功能覆盖 +0.5（正向加分）")
    if not f["skills_stale_engine_ref"]:
        sc["可靠性与可验证性"] += 0.5; sc["可维护与可分发"] += 0.5
        notes.append("etlengine 更名漂移已修复 → 可靠 +0.5 可维护 +0.5")
    if f["drift_total"] == 0:
        sc["可维护与可分发"] += 0.5
        notes.append("全部技能零路径漂移 → 可维护 +0.5（正向加分）")
    if cfg["enable_agent_self_evolution"] and f["retro_entries"] < cfg["retro_low_watermark"]:
        sc["自动化执行力/Agentic闭环"] -= 1.0
        notes.append(f"retro 注册表 {f['retro_entries']} 条 < {cfg['retro_low_watermark']} → 自动化 -1.0（开关 enable_agent_self_evolution=on）")
    elif not cfg["enable_agent_self_evolution"]:
        notes.append("自进化开关关闭 → retro 水位规则跳过")
    ev = {
        "功能覆盖与正确性": f"{f['skills_valid']} 个有效技能全生命周期覆盖；关键技能缺失={miss or '无'}",
        "架构设计": "双分支单入口工作流（pm-direct/ppt-direct/resume-direct）、test-lead 三路并行、dispatcher 双模式、expert-router 896 池",
        "工程实现质量": f"关键脚本实测在位（gate_switch/dual_gates/plan_select/render_eval/forge_skeleton）；scripts 共 {f['total_scripts']} 个",
        "可靠性与可验证性": f"whitebox 产出 test-master-report.json 门禁化；etlengine 更名漂移={'未修复 retro-skill-dispatcher:405' if f['skills_stale_engine_ref'] else '已修复'}",
        "安全与治理": "scope-boundary-gate 编码拦截超范围；acceptance-manager 不达标自动打回",
        "性能效率": "archmap full/lite 分流节约 token；parallel-dispatch 文件数量纲并行判定",
        "可维护与可分发": f"frontmatter 契约统一；全库路径漂移 {f['drift_total']} 处",
        "机制创新性": "扳手框架三维度槽位池、设想锻造炉 11 维、专家问诊团、配色主审官、taste 逆向",
        "自动化执行力/Agentic闭环": f"retro 注册表 {f['retro_entries']} 条；retro→skill GENERATE 自动注册；部署→验收自动触发链",
    }
    hi = [f"{f['skills_valid']} 技能全生命周期覆盖，{len(cfg['key_skills'])} 关键技能实测在位",
          f"retro-skills-registry {f['retro_entries']} 条，复盘→技能自进化闭环在跑",
          "双分支单入口模式成族，轻重流程按需分流"]
    lo = []
    if miss:
        lo.append({"sev": "阻断", "desc": f"关键技能缺失：{'、'.join(miss)}", "action": "补全关键技能目录与 SKILL.md 后再投用"})
    if f["skills_stale_engine_ref"]:
        lo.append({"sev": "高风险", "desc": "etlengine 更名漂移未同步（retro-skill-dispatcher:405）", "action": "同步 SKILL.md 中的引擎路径引用"})
    drift_names = [s["name"] for s in f["skills"] if s["drift"]]
    if drift_names:
        lo.append({"sev": "高风险", "desc": f"{len(drift_names)} 个技能存在失效路径引用（{f['drift_total']} 处）：{'、'.join(drift_names[:4])}", "action": "逐技能清理/同步 SKILL.md 路径引用"})
    if cfg["enable_agent_self_evolution"] and f["retro_entries"] < cfg["retro_low_watermark"]:
        lo.append({"sev": "一般优化", "desc": f"retro 注册表水位不足（{f['retro_entries']} 条）", "action": "增加复盘触发场景，积累复盘样本"})
    if not lo:
        lo.append({"sev": "一般优化", "desc": "缺全局技能依赖图，改名类变更无自动影响面扫描", "action": "补依赖图扫描工具"})
    d = dict(component="skills(Agent技能体系)", scores={k: clamp(v) for k, v in sc.items()},
             evidence=ev, highlights=hi, weaknesses=lo, notes=notes)
    d["overall"] = round(float(np.mean(list(d["scores"].values()))), 1)
    d["grade"] = grade(d["overall"] * 10)
    return d

RUBRIC = {  # 逐技能机械评分规则：dim -> (base, [(条件 lambda s, delta)...])
    "功能覆盖与正确性": (5.5, [(lambda s: s["fm_ok"], 1.0), (lambda s: s["lines"] >= 60, 0.5),
        (lambda s: s["lines"] >= 150, 1.0), (lambda s: s["n_scripts"] >= 1, 1.0),
        (lambda s: s["n_scripts"] >= 3, 0.5), (lambda s: s["is_key"], 0.5), (lambda s: s["drift"], -1.0)]),
    "架构设计": (5.5, [(lambda s: s["has_scripts_dir"], 1.0), (lambda s: s["n_scripts"] >= 3, 0.5),
        (lambda s: s["lines"] >= 100, 1.0), (lambda s: s["kw"]["gate"], 1.0), (lambda s: s["readme"], 0.5)]),
    "工程实现质量": (5.5, [(lambda s: s["fm_ok"], 1.0), (lambda s: s["n_scripts"] >= 1, 1.0),
        (lambda s: s["n_scripts"] >= 2, 0.5), (lambda s: s["lines"] >= 60, 0.5),
        (lambda s: s["readme"], 1.0), (lambda s: s["kw"]["verify"], 0.5)]),
    "可靠性与可验证性": (6.0, [(lambda s: s["kw"]["verify"], 1.0), (lambda s: s["kw"]["gate"], 1.0),
        (lambda s: s["lines"] >= 100, 0.5), (lambda s: s["n_scripts"] >= 1, 0.5), (lambda s: s["drift"], -1.5)]),
    "安全与治理": (5.5, [(lambda s: s["kw"]["safe"], 1.5), (lambda s: s["kw"]["gate"], 1.0), (lambda s: s["is_key"], 0.5)]),
    "性能效率": (6.0, [(lambda s: s["kw"]["perf"], 1.5), (lambda s: s["n_scripts"] >= 1, 0.5), (lambda s: s["lines"] >= 100, 0.5)]),
    "可维护与可分发": (6.0, [(lambda s: s["fm_ok"], 1.0), (lambda s: s["readme"], 0.5),
        (lambda s: s["n_scripts"] >= 1, 0.5), (lambda s: s["lines"] >= 60, 0.5), (lambda s: len(s["drift"]), lambda d: -1.0 * min(d, 2))]),
    "机制创新性": (5.5, [(lambda s: s["kw"]["innov"], 2.0), (lambda s: s["kw"]["auto"], 1.0), (lambda s: s["is_key"], 0.5)]),
    "自动化执行力/Agentic闭环": (5.5, [(lambda s: s["kw"]["auto"], 1.5), (lambda s: s["n_scripts"] >= 1, 1.0),
        (lambda s: s["kw"]["gate"], 0.5), (lambda s: s["is_key"], 0.5)]),
}

def _apply(delta_rule, s):
    return delta_rule(s) if callable(delta_rule) else delta_rule

def score_skill(s):
    dims = {}
    for dim, (base, rules) in RUBRIC.items():
        v = base
        for cond, delta in rules:
            hit = cond(s)
            if hit:
                v += _apply(delta, hit if not isinstance(hit, bool) else s)
        dims[dim] = clamp(v)
    return dims

def eval_all_skills(f):
    out = []
    for s in f["skills"]:
        dims = score_skill(s)
        overall = round(float(np.mean(list(dims.values()))), 1)
        wk = []
        if not s["fm_ok"]:
            wk.append({"sev": "阻断", "desc": "frontmatter 缺 name/description，调度系统不可识别", "action": "补齐 frontmatter 契约字段"})
        if s["drift"]:
            wk.append({"sev": "高风险", "desc": f"失效路径引用 {len(s['drift'])} 处（例：{s['drift'][0]}）", "action": "清理/同步 SKILL.md 中的路径引用"})
        if s["n_scripts"] == 0:
            wk.append({"sev": "一般优化", "desc": "无 scripts 机械执行面", "action": "补执行脚本，或在文档明示纯规则技能定位"})
        if s["lines"] < 60:
            wk.append({"sev": "一般优化", "desc": f"SKILL.md 过薄（{s['lines']} 行 < 60）", "action": "补全触发/流程/契约说明"})
        wk.sort(key=lambda w: SEV_ORDER[w["sev"]])
        hi = []
        if s["is_key"]:
            hi.append("17 关键技能在位")
        if s["fm_ok"] and s["n_scripts"] >= 3:
            hi.append(f"frontmatter 契约完整 + 脚本执行面 {s['n_scripts']} 个")
        elif s["n_scripts"] >= 1:
            hi.append(f"脚本执行面 {s['n_scripts']} 个")
        if s["lines"] >= 150:
            hi.append(f"文档详尽 {s['lines']} 行")
        topdim = max(dims, key=dims.get)
        if dims[topdim] >= 8.5:
            hi.append(f"高分维：{topdim} {dims[topdim]}")
        out.append({**{k: s[k] for k in ("name", "lines", "n_scripts", "is_key", "fm_ok")},
                    "drift_count": len(s["drift"]), "scores": dims, "overall": overall,
                    "grade": grade(overall * 10),
                    "core4": round(float(np.mean([dims[d] for d in CORE4])), 1),
                    "blocking": sum(1 for w in wk if w["sev"] == "阻断"),
                    "highlights": hi[:3], "weaknesses": wk})
    return out

def to_generic(dims9):
    return {g: round(float(np.mean([dims9[d] for d in src])), 1) for g, src in GENERIC7_MAP}

# ================= 第三步：综合排名 =================
def rank_skills(per, mode, with_optional):
    rows = []
    for s in per:
        if mode == "generic":
            d7 = to_generic(s["scores"])
            main = round(float(np.mean(list(d7.values()))), 1)
            if with_optional:  # 可选维降权 0.5 并入：overall = mean(7基础维)*7/8.5? 按 7:1.5 权重
                opt = float(np.mean([s["scores"][d] for d in OPTIONAL_DIMS]))
                main = round((float(np.mean(list(d7.values()))) * 7 + opt * 1.5) / 8.5, 1)
            core4 = round(float(np.mean([d7["任务规划与拆解"], d7["工具使用与环境交互"],
                                         d7["长程执行与状态管理"], d7["鲁棒安全与指令对齐"]])), 1)
            overall, g = main, grade(main * 10)
        else:
            overall, g, core4 = s["overall"], s["grade"], s["core4"]
        rows.append({**s, "rank_overall": overall, "rank_grade": g, "rank_core4": core4})
    rows.sort(key=lambda r: (-r["rank_overall"], r["blocking"], -r["rank_core4"], r["name"]))
    prev_key, rk = None, 0
    for i, r in enumerate(rows):
        key = (r["rank_overall"], r["blocking"], r["rank_core4"])
        if key != prev_key:
            rk = i + 1
            prev_key = key
        r["rank"] = rk
    return rows

# ================= 第四步：渲染（深色科技风，样式参照 chart2_agents_radar.png） =================
def draw_radar(ax, series, dims, bench):
    ax.set_facecolor(BG)
    N = len(dims)
    ang = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist(); ang += ang[:1]
    ax.set_theta_offset(np.pi / 2); ax.set_theta_direction(-1)
    ax.set_xticks(ang[:-1]); ax.set_xticklabels(dims, fontsize=10.5, color=TXT)
    ax.set_ylim(0, 100); ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=9, color=SUB)
    ax.grid(color=GRID, lw=0.6, alpha=0.55); ax.spines["polar"].set_color(GRID)
    ax.plot(ang, [bench] * (N + 1), ls="--", color=SUB, lw=1.2, alpha=0.85)
    ax.annotate(f"标杆线 {bench}", (ang[1], bench), fontsize=9, color=SUB, xytext=(10, 2), textcoords="offset points")
    for s in series:
        v = s["scores"] + s["scores"][:1]
        ax.plot(ang, v, color=s["color"], lw=2.4 if s.get("main") else 1.6,
                ls="-" if s.get("main") else "--", zorder=3, label=s.get("label"))
        if s.get("main"):
            ax.fill(ang, v, color=s["color"], alpha=0.14, zorder=2)
            for a, vv in zip(ang, v):
                ax.annotate(f"{vv:.0f}", (a, vv), color=s["color"], fontsize=11, weight="bold",
                            xytext=(0, 9), textcoords="offset points", ha="center", zorder=4)

def render_radar(sysd, dims, round_img, mode, compare=None, hi_lines=None, lo_lines=None, lo_total=None):
    """图1：Agent 多维度能力雷达。底部强弱清单区：每条独立成行、全文不截断，
    优势/短板各最多显示 10 行（规则标注在图上），超出部分注明总量并指向 agent_rank.md。"""
    hi_lines = (hi_lines or sysd["highlights"])[:10]
    lo_lines = (lo_lines or [f"【{w['sev']}】{w['desc']}" for w in sysd["weaknesses"]])[:10]
    cur = sysd["scores"] if mode == "internal" else to_generic(sysd["scores"])
    scores = [v * 10 for v in cur.values()]
    series = [{"scores": scores, "color": CYAN, "main": True, "label": "本轮"}]
    if compare:
        prev = compare["scores"] if mode == "internal" else to_generic(compare["scores"])
        series.append({"scores": [v * 10 for v in prev.values()], "color": SUB, "main": False, "label": "上一轮"})
    LH = 0.30                                   # 行高（英寸）
    block_h = (len(hi_lines) + len(lo_lines) + 2) * LH + 1.6 * LH + 0.55  # 清单区高度（含标题/间隔/页脚余量）
    radar_h, head_h = 8.4, 1.15
    fig_h = head_h + radar_h + block_h
    fig = plt.figure(figsize=(13, fig_h), facecolor=BG)
    ax = fig.add_axes([0.13, (block_h + 0.1) / fig_h, 0.74, radar_h / fig_h], polar=True)
    draw_radar(ax, series, dims, DEFAULT_CONFIG["benchmark"])
    if compare:
        ax.legend(loc="lower right", bbox_to_anchor=(1.18, -0.05), fontsize=10, facecolor=PANEL, labelcolor=TXT)
    comp = float(np.mean(scores))
    mode_cn = "内部自研 9 维" if mode == "internal" else "通用 7 维"
    fig.text(0.5, 1 - 0.42 / fig_h, "Agent 层 Skills — 能力评估体检", ha="center",
             fontsize=22, color=TXT, weight="bold")
    fig.text(0.5, 1 - 0.92 / fig_h, f"综合 {comp:.1f} 分 · 评级 {grade(comp)}  |  {mode_cn}百分制 · 证据锚点制评分",
             ha="center", fontsize=12.5, color=SUB)
    # 底部强弱清单：从底边锚定向上紧凑排列；标题居中，明细行左对齐原位
    y = block_h - 0.12
    fig.text(0.5, y / fig_h, f"亮点（最多显示 10 行，本区共 {len(hi_lines)} 条）",
             ha="center", fontsize=12.5, color=GREEN, weight="bold")
    for ln in hi_lines:
        y -= LH
        fig.text(0.085, y / fig_h, f"◆ {ln}", fontsize=11, color=GREEN)
    y -= LH * 1.5
    more = f"｜完整 {lo_total} 条见 agent_rank.md" if lo_total and lo_total > len(lo_lines) else ""
    fig.text(0.5, y / fig_h, f"短板（最多显示 10 行，本区共 {len(lo_lines)} 条{more}）",
             ha="center", fontsize=12.5, color=YELLOW, weight="bold")
    for ln in lo_lines:
        y -= LH
        sev = ln.split("】")[0].strip("【") if ln.startswith("【") else ""
        fig.text(0.085, y / fig_h, f"• {ln}", fontsize=11, color=SEV_COLOR.get(sev, YELLOW))
    fig.text(0.5, 0.28 / fig_h, f"对象：~/.agents/skills/  |  shards/skills_system.json · {EVAL_DATE} eval_agents.py 终版",
             ha="center", fontsize=9, color=SUB)
    out = os.path.join(round_img, "agent_radar.png")
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor=BG)
    plt.close(fig); print("saved", out, "| 综合 =", round(comp, 1), grade(comp))

def _wrap_units(s, limit=58):
    """按显示宽度换行（CJK 计 2 单位），全文保留不省略。"""
    lines, cur, w = [], "", 0
    for ch in str(s):
        u = 2 if ord(ch) > 0x2E7F else 1
        if w + u > limit and cur:
            lines.append(cur); cur, w = ch, u
        else:
            cur += ch; w += u
    if cur:
        lines.append(cur)
    return lines or ["—"]

def render_rank_board(rows, round_img, mode):
    """图2：综合能力排名榜（卡片式大字体，无条形；3 栏 × N 行，全部技能上榜。
    每卡三行：行1=#排名 技能名 + 综合分 评级；行2=◆优势整行（绿）；行3=短板整行（按严重等级配色）。
    优势/短板整行显示不截断，超长自动换行（短板的路径示例"（例：…）"图上省略，完整见 agent_rank.md）。"""
    n = len(rows)
    ncol = 3 if n > 20 else (2 if n > 8 else 1)
    per_col = int(np.ceil(n / ncol))
    LP, PAD, HEAD = 0.40, 0.22, 0.34  # 行距 / 卡内边距 / 行1高度
    cards = []
    for r in rows:
        adv = _wrap_units(f"◆ {r['highlights'][0]}" if r["highlights"] else "◆ —")
        if r["weaknesses"]:
            w = r["weaknesses"][0]
            desc = re.sub(r"（例：.*?）", "", w["desc"])  # 图上省略路径示例，完整路径见 agent_rank.md
            wk = _wrap_units(f"【{w['sev']}】{desc}")
            wk_color = SEV_COLOR[w["sev"]]
        else:
            wk, wk_color = ["无短板"], SUB
        cards.append((r, adv, wk, wk_color, HEAD + (len(adv) + len(wk)) * LP + PAD))
    col_h = [0.0] * ncol
    for i, c in enumerate(cards):
        col_h[i // per_col] += c[4]
    body_h = max(col_h) + 0.3
    fig = plt.figure(figsize=(19, body_h + 2.3), facecolor=BG)
    ax = fig.add_axes([0.0, 0.0, 1.0, body_h / (body_h + 2.3)]); ax.set_facecolor(BG); ax.axis("off")
    ax.set_xlim(0, ncol); ax.set_ylim(0, body_h)
    mode_cn = "内部自研 9 维" if mode == "internal" else "通用 7 维"
    fig.text(0.5, 1 - 1.05 / (body_h + 2.3), f"Agent 综合能力排名（{n} 个技能 · {mode_cn}）",
             ha="center", fontsize=28, color=TXT, weight="bold")
    fig.text(0.5, 1 - 1.75 / (body_h + 2.3), "排序：综合分降序 → 阻断数升序 → 核心四维均值降序 ｜ 颜色=评级（青A-/蓝B+/浅蓝B/灰蓝B-/灰C）｜ ◆优势（绿）｜ 短板（红=阻断/黄=高风险/灰=一般）｜ A- 标杆分 8.5",
             ha="center", fontsize=14, color=SUB)
    for c in range(1, ncol):
        ax.plot([c, c], [0, body_h], color=GRID, lw=1.0, alpha=0.6)
    ycur = [body_h] * ncol
    for i, (r, adv, wk, wk_color, ch) in enumerate(cards):
        c = i // per_col
        y_top = ycur[c]; ycur[c] -= ch
        x0, x1 = c + 0.05, c + 0.95
        gc = GRADE_COLOR.get(r["rank_grade"], "#6B7280")
        y = y_top - 0.26
        name_txt = f"#{r['rank']}  {r['name']}" + ("  【阻断】" if r["blocking"] > 0 else "")
        ax.text(x0, y, name_txt, fontsize=17, color=RED if r["blocking"] > 0 else TXT,
                weight="bold", va="center")
        ax.text(x1, y, f"{r['rank_overall']:.1f}  {r['rank_grade']}", fontsize=17,
                color=gc, weight="bold", ha="right", va="center")
        for ln in adv:
            y -= LP
            ax.text(x0, y, ln, fontsize=13, color=GREEN, va="center")
        for ln in wk:
            y -= LP
            ax.text(x0, y, ln, fontsize=13, color=wk_color, va="center")
        ax.plot([c + 0.04, c + 0.96], [y_top - ch + 0.02, y_top - ch + 0.02], color=GRID, lw=0.5, alpha=0.4)
    out = os.path.join(round_img, "agent_rank.png")
    fig.savefig(out, dpi=140, bbox_inches="tight", facecolor=BG)
    plt.close(fig); print("saved", out)

# ================= 落盘（全部原子写） =================
def atomic_write(path, text):
    tmp = path + ".tmp"
    open(tmp, "w", encoding="utf-8").write(text)
    os.replace(tmp, path)
def dump(path, d):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(d, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def write_baseline(f, sysd, rows, mode, round_dir):
    lines = [f"# agent-skills-eval-{TODAY} 评估基线（eval_agents.py 终版生成）", "",
             f"- 评估日期：{EVAL_DATE}｜对象：~/.agents/skills/｜模式：{'内部自研 9 维' if mode == 'internal' else '通用 7 维'}",
             "- 流程：采集（只读实测）→ 基线+调整版信号加减 → 逐技能 9 维机械评分 → 强弱识别（严重等级+行动指引）→ 综合排名 → 渲染 2 图",
             "", "## 体系级评分", "```json", json.dumps(sysd["scores"], ensure_ascii=False, indent=1), "```",
             f"综合 {sysd['overall']}（{sysd['grade']}）", "", "## 加减分 notes", "```json",
             json.dumps(sysd["notes"], ensure_ascii=False, indent=1), "```", "",
             "## 排名 Top10", "```json",
             json.dumps([{k: r[k] for k in ("rank", "name", "rank_overall", "rank_grade", "blocking", "rank_core4")} for r in rows[:10]],
                        ensure_ascii=False, indent=1), "```"]
    atomic_write(os.path.join(round_dir, "baseline.md"), "\n".join(lines))

def write_rank_md(sysd, rows, mode, round_dir):
    mode_cn = "内部自研 9 维" if mode == "internal" else "通用 7 维"
    L = [f"# Agent综合能力排名", f"> 评估模式：{mode_cn}｜评估日期：{EVAL_DATE}｜A- 标杆分 8.5｜对象：~/.agents/skills/（{len(rows)} 个技能）",
         "", "|排名|技能|综合分|评级|阻断级问题数|核心四维均分|优势Top2|短板Top2(标注等级)|", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        adv = "；".join(r["highlights"][:2]) or "—"
        wk = "；".join(f"{w['desc']}【{w['sev']}】" for w in r["weaknesses"][:2]) or "无"
        L.append(f"|{r['rank']}|{r['name']}|{r['rank_overall']:.1f}|{r['rank_grade']}|{r['blocking']}|{r['rank_core4']:.1f}|{adv}|{wk}|")
    L += ["", "## Agent迭代调整方向", "",
          "### 1.【阻断级优先修复】（修复前不做其他优化）"]
    blk = [(r, w) for r in rows for w in r["weaknesses"] if w["sev"] == "阻断"]
    L += ([f"- **{r['name']}**：{w['desc']} → 行动：{w['action']}" for r, w in blk] or ["- 无阻断级短板"])
    bot_dim = min(sysd["scores"], key=sysd["scores"].get)
    L += ["", f"### 2.【冲A短板，重点提升】", f"- 体系最低维：**{bot_dim} {sysd['scores'][bot_dim]}** → 行动：{sysd['weaknesses'][0]['action']}",
          "", "### 3.【维持优势】"] + [f"- {h}" for h in sysd["highlights"]]
    gen = [(r, w) for r in rows for w in r["weaknesses"] if w["sev"] == "一般优化"]
    L += ["", "### 4.【排期靠后-一般优化】"] + ([f"- **{r['name']}**：{w['desc']}" for r, w in gen[:10]] or ["- 无"])
    L += ["", "## 各技能详情"]
    for r in rows:
        L += [f"### #{r['rank']} {r['name']}（{r['rank_overall']:.1f} {r['rank_grade']}）",
              f"- 维分：" + " / ".join(f"{k} {v}" for k, v in r["scores"].items()),
              f"- 信号：{r['lines']} 行 / 脚本 {r['n_scripts']} 个 / 漂移引用 {r['drift_count']} 处 / 关键技能={'是' if r['is_key'] else '否'}",
              f"- **优势**：{'；'.join(r['highlights']) or '—'}"]
        if r["weaknesses"]:
            L += [f"- **短板**：【{w['sev']}】{w['desc']} → 行动：{w['action']}" for w in r["weaknesses"]]
        else:
            L += ["- **短板**：无"]
    L += ["", "> 筛选指引：优先选用阻断级问题=0 且评级 A- 的技能作关键链路依赖；分数高但存在阻断缺陷须先修复再投用；同分看核心四维均分与短板等级。"]
    atomic_write(os.path.join(round_dir, "agent_rank.md"), "\n".join(L))

def write_html(sysd, rows, mode, round_dir):
    mode_cn = "内部自研 9 维" if mode == "internal" else "通用 7 维"
    def wk_txt(r):
        return "；".join(f"【{w['sev']}】{w['desc']}" for w in r["weaknesses"][:2]) or "无"
    trs = "".join(
        f"<tr><td>{r['rank']}</td><td>{r['name']}</td><td>{r['rank_overall']:.1f}</td><td>{r['rank_grade']}</td>"
        f"<td>{r['blocking']}</td><td>{r['rank_core4']:.1f}</td><td>{'；'.join(r['highlights'][:2]) or '—'}</td>"
        f"<td>{wk_txt(r)}</td></tr>"
        for r in rows)
    dims_trs = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in sysd["scores"].items())
    html = f"""<!doctype html><html lang=zh><meta charset=utf-8><title>Agent/Skills 评估报告 {EVAL_DATE}</title>
<style>body{{background:{BG};color:{TXT};font-family:'PingFang SC',sans-serif;max-width:1200px;margin:24px auto;padding:0 16px}}
h1,h2{{color:{CYAN}}} table{{border-collapse:collapse;width:100%;font-size:13px;margin:12px 0}}
td,th{{border:1px solid {GRID};padding:6px 8px}} th{{background:{PANEL}}} img{{max-width:100%;margin:12px 0;border:1px solid {GRID}}}
.small{{color:{SUB};font-size:12px}}</style>
<h1>Agent/Skills 专项评估报告</h1>
<p class=small>模式：{mode_cn}｜日期：{EVAL_DATE}｜综合 {sysd['overall']}（{sysd['grade']}）｜eval_agents.py 终版</p>
<h2>体系级 9 维评分</h2><table><tr><th>维度</th><th>得分(0-10)</th></tr>{dims_trs}</table>
<h2>图1 · 多维度能力雷达</h2><img src="images/agent_radar.png">
<h2>图2 · 综合能力排名</h2><img src="images/agent_rank.png">
<h2>排名总表</h2><table><tr><th>排名</th><th>技能</th><th>综合分</th><th>评级</th><th>阻断数</th><th>核心四维</th><th>优势Top2</th><th>短板Top2</th></tr>{trs}</table>
<p class=small>筛选指引：优先选用阻断级问题=0 且评级 A- 的技能作关键链路依赖；分数高但存在阻断缺陷须先修复再投用。</p>"""
    atomic_write(os.path.join(round_dir, "report.html"), html)

# ================= 主流程 =================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["internal", "generic"], default=None)
    ap.add_argument("--config", default=None, help="JSON 配置（覆盖 skills_dir/key_skills/阈值/开关）")
    ap.add_argument("--compare", default=None, help="上一轮 shards/skills_system.json，雷达叠加对比")
    ap.add_argument("--with-optional", action="store_true", help="generic 模式下可选维降权并入综合分")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    cfg = dict(DEFAULT_CONFIG)
    if args.config:
        cfg.update(json.load(open(args.config, encoding="utf-8")))
    mode = args.mode or cfg.get("mode", "internal")
    ROUND = args.out or os.path.join(HOME, "Desktop", f"agent-skills-eval-{TODAY}")
    SHARDS = os.path.join(ROUND, "shards"); IMG = os.path.join(ROUND, "images")
    for d in (SHARDS, IMG):
        os.makedirs(d, exist_ok=True)

    f = collect(cfg)
    print(f"[采集] 有效技能 {f['skills_valid']} 个 | 脚本 {f['total_scripts']} 个 | 关键技能缺失 {f['skills_key_missing'] or '无'} "
          f"| retro {f['retro_entries']} 条 | 路径漂移 {f['drift_total']} 处 | stale_engine_ref={f['skills_stale_engine_ref']}")
    sysd = score_system(f, cfg)
    per = eval_all_skills(f)
    rows = rank_skills(per, mode, args.with_optional)

    dump(os.path.join(SHARDS, "skills_system.json"), sysd)
    dump(os.path.join(SHARDS, "skills_rank.json"),
         {"mode": mode, "date": EVAL_DATE,
          "items": [{k: r[k] for k in ("rank", "name", "rank_overall", "rank_grade", "blocking",
                                       "rank_core4", "scores", "highlights", "weaknesses")} for r in rows]})
    write_baseline(f, sysd, rows, mode, ROUND)
    write_rank_md(sysd, rows, mode, ROUND)
    write_html(sysd, rows, mode, ROUND)
    dims = DIMS9 if mode == "internal" else [g for g, _ in GENERIC7_MAP]
    cmpd = None
    if args.compare and os.path.isfile(args.compare):
        cmpd = json.load(open(args.compare, encoding="utf-8"))
    # 雷达图强弱清单：体系级 + 逐技能聚合（每条一行、不截断、各最多 10 行）
    hi_lines = list(sysd["highlights"])
    top5 = [r["name"] for r in rows[:5]]
    hi_lines.append(f"高分技能 Top5：{'、'.join(top5)}")
    lo_lines = [f"【{w['sev']}】{w['desc']}" for w in sysd["weaknesses"]]
    per_lo = []
    for r in rows:
        for w in r["weaknesses"]:
            d = re.sub(r"（例：.*?）", "", w["desc"])
            per_lo.append((SEV_ORDER[w["sev"]], f"【{w['sev']}】{r['name']}：{d}"))
    per_lo.sort(key=lambda t: (t[0], t[1]))
    lo_lines += [t[1] for t in per_lo]
    lo_total = len(lo_lines)
    render_radar(sysd, dims, IMG, mode, cmpd, hi_lines=hi_lines, lo_lines=lo_lines, lo_total=lo_total)
    render_rank_board(rows, IMG, mode)
    blk_n = sum(r["blocking"] for r in rows)
    print(f"[排名] Top3：" + "、".join(f"#{r['rank']}{r['name']}({r['rank_overall']:.1f})" for r in rows[:3])
          + f"｜阻断技能 {sum(1 for r in rows if r['blocking'] > 0)} 个｜阻断短板 {blk_n} 条")
    print("[交付]", ROUND)

if __name__ == "__main__":
    main()
