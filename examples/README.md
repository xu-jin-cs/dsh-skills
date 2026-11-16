# Examples — runnable demos

> Three self-contained demos with expected outputs. CLI demos need no agent host; host-required demos are labeled.
>
> [中文说明](README_zh.md) · [← back to dsh-skills](../README.md)

## 1. gate-switch: see a mechanical gate decide in 30 seconds (pure CLI)

From the repo root:

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

Exit code `0` = A. Then run the experiment that makes it click: delete two badge lines from `README.md` and rerun — the verdict flips to `B`, and `violations` lists exactly which items are missing. **Judgment lives in the script, not the model.** New scenario = a new spec JSON; the engine changes zero lines (the 7 check primitives are listed in [`gate-switch/SKILL.md`](../gate-switch/SKILL.md)).

## 2. archmap: cartograph any project (inside an agent host)

archmap runs inside an agent host (DSH / Claude Code / Kimi Code). After installing, in a session:

```
/archmap <your-project-path>          # zero-arg auto-routing: no baseline → full; baseline → lite
/archmap <your-project-path> +diff    # line-level diff impact + import closure + test selection (zero LLM)
/archmap <your-project-path> +sync    # incremental baseline sync + regenerate reports
```

Expected artifacts: an `archmap/` directory in the target project — `full_index.json` (module/API inventory), `file_routes.json` (route→file mapping), report series `01~09` plus the change ledger. The `diff` mode is pure deterministic computation — zero LLM tokens.

## 3. parallel-dispatch: throw the SPDT switch (pure CLI, verdict visible)

```bash
python3 parallel-dispatch/scripts/dispatch_switch.py --files 6 --units 3 --desc "demo"
```

Expected: a JSON gate declaration. In a bare shell it **refuses to throw** and lists the reasons (task list not registered in this turn, no baseline) — **that's not an error, it's the gate working**: parallel fan-out must first register a task list and pass baseline checks, all trailed in `~/.agents/logs/dispatch_switch.jsonl`. Inside an agent host, ≥2 independent subtasks automatically trigger the same decision.

---

Methodology deep-dive: [Mechanical Gates for LLM's Verbal Promises](../docs/mechanical-gates-for-llm.md) ([English](../docs/mechanical-gates-for-llm.en.md)).

License: [Custom Source-Available](../LICENSE) (中文对照: [LICENSE-zh.md](../LICENSE-zh.md)) — personal non-commercial local use; no public forks, commercial distribution, or SaaS without written permission. Author: [xu-jin-cs](https://github.com/xu-jin-cs).
