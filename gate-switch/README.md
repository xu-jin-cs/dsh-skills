# gate-switch — Mechanical verification gates for LLM claims

> Turn "I did it" into checkable facts. Spec-driven gate engine: **verdict A (pass) / B (block) decided by script, not by the model.**
>
> [中文说明](README_zh.md) · [← back to dsh-skills](../README.md)

## What it is / What pain it solves

LLMs chronically fail in three ways: **steps skipped, checklists half-done, "done" claims fabricated**. Prompting harder doesn't fix it — judgment must move out of the model.

gate-switch writes "what must be true" as a **spec JSON**; the engine verifies each check mechanically:

- All pass → **verdict A** (pass); any failure → **verdict B** (block) with per-item violations auto-listed as the block reason.
- Four-state exit codes: `0 = A / 2 = B / 3 = CLARIFY / 4 = VIOLATION`, full JSONL audit trail.
- New scenario = **a new spec JSON; the engine changes zero lines of code**.

## 30-second install

```bash
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install gate-switch
```

Already cloned? `./install.sh gate-switch` (symlinks into `~/.dsh/skills`, hot-reloaded by DSH watcher; works in Claude Code / Kimi Code / Codex skill roots too).

## 5-minute quickstart

Run the demo gate that verifies this repo's own README (from repo root):

```bash
python3 gate-switch/scripts/gate_switch.py --spec examples/gate-switch/demo_spec.json --set target=README.md
```

Expected output (excerpt):

```json
{
  "verdict": "A",
  "gate": "demo_release_hygiene",
  "passed": ["README 至少 3 枚 shields.io badges: 命中=4 ...", "..."]
}
```

Exit code `0` = A. Now the experiment that makes it click: delete two badge lines from `README.md`, rerun — verdict flips to `B` and `violations` lists exactly which items failed. **Judgment lives in the script, not the model** — that is the whole point of gate-switch.

## Input / output

- **Input**: a spec JSON — a list of checks built from **7 frozen primitives**: `file_exists` / `file_min_size` / `json_field` / `glob_count` / `grep_count` / `mtime_after` / `script_exit`. Path fields support `~`, cmd fields support `$HOME` expansion, so specs are portable across machines. Runtime values injected via `--set key=value`.
- **Output**: JSON verdict (`passed[]` / `violations[]` with auto-generated B-grade reasons) + JSONL trail.
- **Layout**: `scripts/` (engine + 21 instance-gate checkers) · `specs/` (gate specs incl. archive/fixtures) · `data/` (trigger-signal registry & word lists) · `templates/` (L3 framework-gate templates). Session state (`runtime/`, `council/`) is per-machine and **not distributed**.

## Capabilities & boundaries

- Typical gates: pre-release hygiene (`publish_sync_check`: symlink / clean tree / nothing unpushed — one gate, three checks), acceptance gates, test-evidence gates, deploy admission, mode routing.
- **Boundary**: mechanically decidable 0/1 facts. Anything requiring taste or open-ended semantics is out of scope — write that part as a human checklist, not a spec.

## Combines with

- **[parallel-dispatch](../parallel-dispatch/README.md)** — every pre-throw precondition (task list, baseline file) can be guarded by a gate-switch spec.
- **[archmap](../archmap/README.md)** — `mtime_after` checks `diff_impact.json` freshness before consuming its impact surface.
- **[Xj-engine](../Xj-engine/README.md)** — `et_test_gates` ships gate semantics inside the engine's ET contract.

## FAQ

**Q: My check needs custom logic. Must I modify the engine?**
No — use the `script_exit` primitive to run any command; exit 0 = pass, anything else = violation with stdout/stderr as evidence.

**Q: Where does session state live?**
`gate-switch/runtime/` (verdict state) and `council/` (review reports) are generated per machine and stay out of the repo.

**Q: Can I share a spec I wrote?**
Specs are plain JSON — put it in `specs/` of your local install; it works everywhere the engine runs.

---

License: [Custom Source-Available](../LICENSE) (中文对照: [LICENSE-zh.md](../LICENSE-zh.md)) — personal non-commercial local use; no public forks, commercial distribution, or SaaS without written permission. Author: [xu-jin-cs](https://github.com/xu-jin-cs).
