# parallel-dispatch — The mechanical switch for parallel fan-out

> Master rules + a SPDT gate that decides **A = fan out / B = go serial** — with receipts, not vibes.
>
> [中文说明](README_zh.md) · [← back to dsh-skills](../README.md)

## What it is / What pain it solves

Multi-task scenes fail in two directions: everything serialized (slow, wasteful) or blind fan-out (chaos, context bleed, merge conflicts). parallel-dispatch installs a mechanical decision point:

- Any scene with **≥2 subtasks** must emit a `[PARALLEL-GATE]` declaration — no trigger words needed, it's forced.
- **`scripts/dispatch_switch.py`** throws the verdict: **A = parallel fan-out / B = serial** (a B verdict *must* carry a dependency-chain reason — an empty reason is itself a violation), full JSONL trail.
- Before an A verdict, three pre-conditions are enforced: task list registered, unified context baseline, probe evidence — **no blind fan-out**.
- Workload is measured in one unit only: **file count** (no hours, no vibes).

## 30-second install

```bash
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install parallel-dispatch
```

Already cloned? `./install.sh parallel-dispatch`.

## 5-minute quickstart

Throw the switch bare (no agent host needed):

```bash
python3 parallel-dispatch/scripts/dispatch_switch.py --files 6 --units 3 --desc "demo"
```

Expected: in a bare shell it **refuses to throw** and lists why (task list not registered, no baseline). **That is not an error — it's the gate working.** A real session example: a 5-task plan first threw `CLARIFY` → supplying `--files` / `--units` plus a `--baseline` plan file flipped it to `verdict: A` with a mixed topology.

## Input / output

- **Input**: `--files N --units N --desc "..."` plus optional `--coupled --baseline <file> --dep-reason "..."`. File count is the only workload unit.
- **Output**: JSON verdict (`verdict` / `mechanism` / `fanout` / violations & reasons) + JSONL trail at `~/.agents/logs/dispatch_switch.jsonl`.
- **Two-axis decision matrix** (see `SKILL.md` for the full table):
  - Scale axis: ≤3 files → light clone · >3 files or contract coupling → `task_breakdown` sizing · M/L → engine-level clones
  - Count axis: 2–5 → main-agent parallel · 6–9 → grouped · ≥10 → workflow orchestration

## Capabilities & boundaries

- Full rulebook lives in `SKILL.md`: scene auto-matching table, the three-slot clone contract (PRE-SPAWN / RECEIPT / MERGE), minimal probes, merge checkpoints, and a prohibitions list (violations count as intentional serialization or reckless parallelism).
- **Boundary**: parallel-dispatch decides *whether* and *how* to parallelize — it does not execute the tasks.

## Combines with

- **[gate-switch](../gate-switch/README.md)** — pre-throw preconditions (registered task list, baseline file exists) can be guarded as gate-switch specs.
- **task_breakdown** — M/L-scale jobs route through task-breakdown sizing before engine-level clones.
- **[Xj-engine](../Xj-engine/README.md)** — ≥10-unit batches route to workflow orchestration on the engine.

## FAQ

**Q: Why did my throw get rejected with "CLARIFY"?**
The switch only decides on mechanical signals. Supply `--files` / `--units`, and for coupled work a `--baseline` file — then it decides.

**Q: Can the model just decide to serialize quietly?**
No — evaluating options without executing counts as intentional serialization; the JSONL trail makes it auditable.

**Q: Does B mean "wrong"?**
No. B = serial with a stated reason is a first-class verdict. An *empty* reason is the violation.

---

License: [Custom Source-Available](../LICENSE) (中文对照: [LICENSE-zh.md](../LICENSE-zh.md)) — personal non-commercial local use; no public forks, commercial distribution, or SaaS without written permission. Author: [xu-jin-cs](https://github.com/xu-jin-cs).
