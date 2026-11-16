# Xj-engine — Standalone agent-engine kernel

> The default engine of the dsh-skills ecosystem: ET contracts, node scheduling & control, deliverable signing, event reporting — **the engine never runs the model for you**.
>
> [中文说明](README_zh.md) · [← back to dsh-skills](../README.md)

## What it is / What pain it solves

Workflow orchestration for LLM agents usually blurs two layers: *who decides* and *who executes*. Xj-engine keeps them apart — the host session (with its model) does the reasoning; the engine does everything mechanical:

- Python package `engine`, API entry `engine.kernel.et`, CLI `xj-engine`.
- **Execution carrier boundary (2026-11-13 ruling)**: execution = host pulls the shape — `assemble → spawn (session/sub-agent) → snapshot`; the model *is* the current session. The engine only does: contract compile/verify, node scheduling & control, deliverable signing, event reporting.
- `default_runner` (`SCI_RUNNER_CMD`) is a test/custom bridge only — **not a production entry**; unconfigured = explicit error, silent stub runs are forbidden.
- 12 pytest suites under `tests/` guard kernel gates, flow enforcement, paradigm selection, team decisions and more.

## 30-second install

```bash
pip install -r Xj-engine/requirements.txt
pip install -e Xj-engine          # register as editable install (local default engine)
# optional Claude execution engine:
pip install -r Xj-engine/requirements-optional.txt
```

## 5-minute quickstart

CLI:

```bash
xj-engine health
xj-engine run --payload '{"op": ...}'
xj-engine workflow init | validate
xj-engine flow
```

Python entry:

```python
from engine.kernel import et
# pass a payload conforming to the ET contract
```

Task lifecycle payload example:

```json
{
  "task": {
    "action": "complete",
    "task_id": "task-001",
    "evidence": {"output_file": "result.json"},
    "targets": ["dsh"]
  }
}
```

Bridge execution (host adapters register by contract):

```python
from engine.task import get_bridge_executor

def adapter_dsh(event):
    # e.g. call todo_write to mark completed
    return {"ok": True}

get_bridge_executor().register_adapter("dsh", adapter_dsh)
```

Details: `docs/bridge_contract.md`, plus `docs/node_executor_contract.md` / `docs/stage_runtime_contract.md`.

## Input / output

- **In**: ET-contract payloads (kernel), task lifecycle events (`complete` / `cancel` / `archive` with evidence), workflow definitions (init/validate).
- **Out**: contract-verified dispatch, signed deliverables, audit events, state persistence.
- **Layout**: `kernel.py` (unified entry incl. task bridging) · `et_contract.py` / `et_sign.py` (contract + signatures) · `audit.py` · `state_store.py` / `state_wiring.py` (dual-write) · `task.py` (lifecycle + BridgeExecutor) · `et_test_gates.py` · `database.py` (standalone SQLite) · `engine/flow/` (compiler / builder / validator / graph / parallel / checkpoint).

## Capabilities & boundaries

- **Good at**: contract-verified orchestration, state persistence with dual-write wiring, signed deliverables, audit trails, test gates inside the ET contract.
- **Not in scope**: the engine never runs the model, never reasons node bodies, and has no production runner of its own — hosts execute, engines account.
- **Compatibility**: platform database dependency removed (local `database.py`); external test-skill service removed (`skills.py` stub); no private paths; no platform business code.
- **Env vars** (see `.env.example`): `XJ_ENGINE_DB_URL` (database), `AGENT_ENGINE_SECRET` (kernel signing key).

## Combines with

- **[gate-switch](../gate-switch/README.md)** — `et_test_gates` embeds gate semantics in the ET contract.
- **[parallel-dispatch](../parallel-dispatch/README.md)** — ≥10-unit batches route to engine workflow orchestration.

Registration: on machines that use it, the engine is registered as local default in `engine_registry.json` files (see `.env.example` and repo docs).

---

License: [Custom Source-Available](../LICENSE) (中文对照: [LICENSE-zh.md](../LICENSE-zh.md)) — personal non-commercial local use; no public forks, commercial distribution, or SaaS without written permission. Author: [xu-jin-cs](https://github.com/xu-jin-cs).
