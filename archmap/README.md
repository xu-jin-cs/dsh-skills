# ArchMap — Architecture cartography agent

> Terminal-native static analysis: build an architecture baseline once, then let every change be measured — impact surfaces, line-level diffs, test selection — **instead of re-reading the whole repo with your LLM**.
>
> [中文说明](README_zh.md) · [← back to dsh-skills](../README.md)

## What it is / What pain it solves

Agents re-read entire repositories to answer "what does this change affect?" — burning tokens and still missing routes or closures. ArchMap replaces full-repo re-reading with **deterministic computation**:

- **Zero-arg auto-routing**: no baseline → `full` initialization; baseline present → `lite` incremental (seconds, unchanged modules reused).
- **Impact surface from a requirement**: requirement text → affected modules / files / functions / routes (`precise_analysis.json`).
- **Line-level diff mode (zero LLM)**: exact changed line ranges, import closures, test selection + change ledger — pure deterministic computation, no tokens burned.
- Precise development, massive token savings.

## 30-second install

```bash
curl -fsSL https://raw.githubusercontent.com/xu-jin-cs/dsh-skills/main/scripts/dsh-skill.sh | bash -s -- install archmap --with-deps
```

Symlinked into `~/.dsh/skills` (DSH watcher hot-reload); `--with-deps` installs `PyYAML / numpy / scipy`. Already cloned? `./install.sh archmap --with-deps`. Uninstall/doctor via the same installer.

## 5-minute quickstart

Five modes, one entry (zero-arg auto-routes; explicit `full`/`lite` override):

```bash
/archmap <project-path>                     # auto: full (no baseline) or lite (baseline exists)
/archmap <project-path> full | lite [note]  # force a mode
/archmap <project-path> <requirement text>  # incremental impact surface
/archmap <project-path> sync                # merge changes into baseline, regenerate reports
/archmap <project-path> diff [note]         # line-level diff impact + test selection
```

Typical rhythm:

1. Baseline: `/archmap /path/to/project`
2. Impact: `/archmap /path/to/project "add a user points system"` → `precise_analysis.json`
3. Develop.
4. Before review: `/archmap /path/to/project diff change-note` → `diff_impact.json` + change ledger
5. After acceptance: `/archmap /path/to/project sync`

## Input / output

All artifacts land in `<project-path>/archmap/`:

```
full_index.json        # full architecture baseline
vector_cache.json      # module vector cache
module_hashes.json     # module content fingerprints (SHA256)
file_line_hashes.json  # line-level snapshots (diff/lite basis)
01_执行摘要.md ~ 09_粒度校验报告.md   # reports incl. Mermaid architecture / data-flow / sequence diagrams
precise_analysis.json  # incremental impact surface (file / function / route precision)
diff_impact.json       # diff impact + test selection
diff_history.jsonl     # machine-readable change trail
10_变更历史.md          # change ledger (retro input)
recall_report.json     # recall verification
etl_rules/             # auto-generated for ETL-shaped projects
```

**Five modes**: full (zero-arg, no baseline) · lite (zero-arg, baseline exists) · incremental impact (path + requirement) · sync (path + sync) · diff (path + diff).

## Capabilities & boundaries

- **Good at**: architecture survey of mid/large codebases (modules, API/storage inventory, dependency matrix, Mermaid diagrams); daily incremental maintenance; pre-development impact analysis; pre-retro change ledgers; ETL-shaped projects (7-layer rule docs + contract-drift detection).
- **Not in scope**: read-only analyst — runs no code, modifies no business source, validates no execution results (consumers own that); granularity stops at api/function level (by design — token savings first); no web service; state lives entirely in `<project>/archmap/`; text-only outputs (JSON/Markdown/Mermaid).
- **Deps**: required PyYAML/numpy/scipy; optional sentence-transformers (falls back to deterministic hash vectors offline — fully functional, slightly lower recall). Offline-friendly: no network requests.

## Combines with

- **test-case-designer** — consumes reports 02–08; incremental reads `precise_analysis.json` to scope tests.
- **whitebox-coverage** — diff mode scopes work via `diff_impact.json`.
- **Retros** — `10_变更历史.md` + `diff_history.jsonl` are the ledger inputs.
- **[gate-switch](../gate-switch/README.md)** — verify artifact freshness with `mtime_after` before consuming.

Details: [`SKILL.md`](SKILL.md) (trigger modes, expert slots, node inventory).

---

License: [Custom Source-Available](../LICENSE) (中文对照: [LICENSE-zh.md](../LICENSE-zh.md)) — personal non-commercial local use; no public forks, commercial distribution, or SaaS without written permission. Author: [xu-jin-cs](https://github.com/xu-jin-cs).
