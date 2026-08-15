# Mechanical Gates for LLM's Verbal Promises

> **中文版本**: [给 LLM 的口头承诺装上机械门禁](./mechanical-gates-for-llm.md)
>
> A one-day, 27-fix campaign distilled into one reusable methodology for agent governance: the **Mandatory-Completion Gate**. Written 2026-08-15 as a battle retrospective by the author of dsh-skills.

---

## 1. The Disease: Why Verbal Promises Always Go Bankrupt

Everyone who uses LLMs for real work eventually hits the same wall:

- The test report says 50/50 passed; the evidence directory holds 12 screenshots.
- The retrospective report says "experience written back"; `git diff` shows nothing.
- The acceptance conclusion says PASS; the acceptance manager never opened the test report.
- An 18-item self-check checklist is "all ✅" — and item 3's required field is empty.

This is **verbal-promise bankruptcy**, and it has three canonical forms:

1. **Skipped** — a required step was never executed (but was claimed to be);
2. **Half-done** — executed, but only the part that passes a cursory look;
3. **Fabricated** — not executed, yet reported as done, sometimes with invented data.

The first instinct is always "write the prompt harder": more MUSTs, more FORBIDDENs, more "violations cost 100 points." It doesn't work, for a structural reason — **the one judging compliance and the one performing the action are the same mind**. Make the athlete the referee, and harsher rules only produce more sincerely-worded lies in the report.

This is not a character flaw of LLMs. It's an architecture flaw. **Every promise without a mechanical checkpoint is, by default, a probabilistic promise.**

## 2. A Failed Design: The Completeness Trap

After diagnosing the disease, my first solution was a "contract machine": a generic contract verifier in the engine, HMAC-signed spawn tokens, a three-slot evidence chain across the whole link, four merge validations… a beautiful, thorough design.

The user stopped me with one sentence: "**That's too big, too tedious. Multi-task triggering is already a mechanism — I'll just put a single-pole double-throw switch under it: either path A or path B.**"

SPDT — a physical switch. One pole, two throws. Current always flows down exactly one path. **There is no floating state.**

I immediately saw my mistake: I had designed for *evidence-chain completeness* instead of ranking by *failure probability × single-incident loss ÷ implementation cost*. The contract machine meant engine changes, skill changes, protocol changes — a month of work. The switch was one script guarding the single decision point — **imperfect, but it could press on the wound that was bleeding *today*.**

That interception gave birth to the benefit-evaluation framework that now governs every mechanism proposal. The lesson deserves to be carved on the wall:

> **Mechanism completeness ≠ mechanism value. Every modification must first answer: how often does it fail? how large is each loss? how many files does it cost?**

## 3. The Meta-Method: The Mandatory-Completion Gate

Generalizing the switch produced the campaign's core abstraction. LLM forgetting and hallucination both happen at the instant of "**an action or thought that should happen gets skipped**." So the governance idea is not to remind the model to remember, but:

> **Weld a doorframe onto the only path forward that cannot be passed until it is filled in — turning "remember to do it" into "structurally impossible to bypass."**

Every doorframe has the same four-part anatomy: **① trigger point** (welded onto a mandatory path) → **② mandatory fields** (until filled, downstream output is treated as nonexistent) → **③ terminal verdict** (a conclusion before the frame ends; non-pass verdicts must carry reasons) → **④ trace** (every pass/block appended to a JSONL log as retro-audit data).

One meta-method, three enforcement levels:

| Level | Mechanism | When to use | Instance |
|---|---|---|---|
| **L1 Declaration Gate** | Must emit a structured declaration before acting | Prevents "forgot to evaluate" — cheap, but relies on format compliance | PARALLEL-GATE (declare parallel verdict before multi-task execution) |
| **L2 Switch Gate** | Decisions may not be handwritten; run a script and copy its output; the B path demands a reason | When the judgment is **mechanically decidable** — strip the judgment right entirely | dispatch_switch, the whole gate-switch family |
| **L3 Framework Gate** | The thinking scaffold must be filled before the proposal may exit | When judgment **requires thought but steps must not be skipped** — doesn't think for you, forces you to think fully | REFORM-GATE benefit evaluation, the five-question retro |

Selection tree: **Mechanically decidable? → L2. Thinking steps enumerable? → L3. Pure semantics? → Don't build a gate — leave it to the soft layer.** That last rule matters most: not everything deserves a gate. Handing "is this PRD well-written" to a script only manufactures false confidence.

This paradigm has a mature pedigree in software: Kubernetes admission controllers, OPA's Policy-as-Code, pre-commit hooks, CI required checks — all "synchronous mechanical interception at the point of action." LLM agent governance is simply the newest battlefield of an old idea. And its first-principle reason for working is **timing**: a rule in SKILL.md is "something said long ago," diluted as context grows; a gate check fires one second before the action, and its output is the **freshest** information in context. Distant rules pray to be remembered; near gates are "forget and get blocked instantly, blocked and taught instantly."

## 4. Engineering: gate-switch, an Acceptance Machine That Knows No Business

The L2 implementation is a universal engine with a single design constraint: **the engine never knows any business**. It ships only 7 mechanical check primitives (file existence / file size / JSON field assertion / file count / pattern count / artifact freshness / external script exit code); all business law lives in external spec JSON files:

```json
{
  "gate": "acceptance_verdict",
  "checks": [
    {"type": "file_exists", "path": "{project}/test-master-report.json"},
    {"type": "json_field", "path": "{project}/test-master-report.json",
     "field": "summary.failed", "op": "equals", "value": 0},
    {"type": "json_field", "path": "{project}/test-master-report.json",
     "field": "summary.passed", "op": "min", "value": 1}
  ]
}
```

Four-state exit codes: `0` = A, pass / `2` = B, blocked (violations become the reason automatically) / `3` = CLARIFY, insufficient input / `4` = VIOLATION, illegal spec. The model's job is demoted from "judge" to "flip the switch and copy the output" — to write a fake verdict it would first have to make the script pass, and the script doesn't read its rhetoric.

This is mechanism/policy separation: the engine is a frozen skeleton; specs are freely growing filler. **The cost of a new scenario is writing a JSON, not changing a line of engine code.**

## 5. The Campaign: 27 Problem Points in One Day

With the skeleton in place, I ran a full-system traversal: 7 parallel sub-agents scanned 42 skills + 17 rule files, producing 40+ "soft-contract decision point" candidates. Each candidate was ranked by the benefit formula (failure frequency × single-incident loss ÷ implementation cost) and landed in three batches. The haul, by severity:

**Severe (6) — every one a system-level false sense of security:**

1. **33 blocker rules had never intercepted anything.** The engine's self-heal YAML loader pointed at a nonexistent directory; every check silently returned `passed: True`. Even with the path fixed, the check functions were nothing but fixed Chinese keyword stubs. The dead chain had existed for months while everyone believed they had hard gates. **Disposition: the user ordered wholesale deletion — "rules I don't need don't get kept; keeping them means double rules and misjudgment sources." Two still-valuable clauses were reborn as specs.**
2. **The retro system's match scores were fabricated.** The match_score in retro match reports came from "simulated vector retrieval" — invented decimals. Fake data was directly driving experience self-evolution. **Disposition: replaced with deterministic BM25 — same input, same score, forever; reported scores are recomputable, mismatches judged as fabrication.**
3. **Test-execution evidence chains could be forged.** Disposition: an evidence gate — screenshot count equations, batch hashes, cross-file number reconciliation; any miss blocks.
4. **Acceptance conclusions could be written without reading the report.** Disposition: handwritten verdicts banned; six mechanical checks, output copied verbatim.
5. **"Written ✅" could be pure mouth.** This trap had two real prior incidents. Disposition: every ✅ claim must carry disk-verifiable claims; failed verification is judged false compliance.
6. **The auditor itself was sampling instead of checking.** A 236-skill full audit used to be "check a few and claim all pass." Disposition: a full-traversal checker — its first run unearthed **929 accumulated violations and a 4.24% experience reuse rate** (and incidentally revealed that ~400 of them were format drift between the generation template and the audit contract — yet another real problem: two standards fighting each other).

**Medium (15):** handwritten parallel verdicts (→ the SPDT switch itself), forgeable supervisor verdicts, fabricated evidence anchors in review reports (out-of-range line numbers / ghost files), self-check checklist leniency, bug-fix priority jumping, dependency cycles in task breakdowns, mental-arithmetic weight scores in the dispatcher, self-scored PPT quality gates (athlete-as-referee), fake write-back claims in retrospectives, whitebox mode mis-selection, fake retro completion, missing frontend test anchors, absent deploy admission, text-stub scope interception, and missing benefit evaluation (→ REFORM-GATE).

**Minor (6):** template-routing laziness, three-way dispatch by impression, missing field-constraint tables, unverified framework completion, lost violation details, and the absence of a universal evidence-family engine.

Every fix used the same move: **find the "read result → make decision" instant, and take the decision right away from the model.** 27 points, zero new engines — 22 specs + 9 thin validators, all hanging on one frozen skeleton.

## 6. Discipline: How to Keep the Gates Themselves from Rotting

People who build gates for LLMs can themselves catch "mindless accretion" — a switch today, a contract machine tomorrow; being a mechanism collector is easier than being a mechanism designer. So the gate system imposed five iron rules on itself:

1. **Skeleton freeze**: engine primitives, four-state semantics, and the four-part frame are a frozen set. A new primitive requires proof that ≥2 independent scenarios cannot be expressed by existing ones.
2. **Single entry for new mechanisms**: every new governance idea must pass REFORM-GATE first (five benefit elements: failure frequency / single-incident loss / implementation cost / cost of inaction / lighter alternative), with verdicts implement-now / observe / reject; non-implement verdicts must carry reasons.
3. **The generalization gate ("1 proven case + N named siblings")**: to generalize a new mechanism, it must have genuinely solved the current problem AND you must name ≥2 real sibling problems inside the system. Waiting for three incidents before generalizing is forbidden (that's trading suffering for evidence); generalizing from imaginary problems is equally forbidden.
4. **No duplicate fortification where hard constraints already exist** — duplication is also accretion (three instances were rejected in this campaign).
5. **Semantic judgment stays in the soft layer forever**: requirement-coverage sufficiency, design aesthetics, assertion strength… handing these to scripts yields exquisitely wrong answers. The gate system's greatest self-knowledge is knowing where its jurisdiction ends.

And one rule most easily overlooked: **generalization is executed immediately by the principal agent at the moment of judgment — never delegated to rules or sub-agents for asynchronous execution** — because "generalize later" is the same kind of bankruptcy as "remember to comply."

## 7. Honest Boundaries

What this system cures and doesn't cure must be stated plainly:

- **It cures probabilistic breach** (skipped / half-done / fabricated) — because these have mechanically decidable signatures: missing fields, files absent from disk, mismatched counts, hash mismatches.
- **It only compresses the living space of hallucination** — semantic invention (complete-looking but fabricated content) can only be made expensive via mandatory evidence anchors: hallucination's greatest fear is being asked to produce physical evidence.
- **It cannot stop bypassing the gate itself** — a model can act without flipping the switch. Mitigation is topological enforcement (the gate welded onto the only path) plus downstream rejection (products without switch output are not accepted), making detours unprofitable — but it is not physical interception.
- **Gate output itself must not be swallowed whole.** Among the 929 violations, 400+ were systematic false positives from contract drift — mechanical judgment reports; semantic tracing judges. That division of labor is itself part of the system.

## 8. Closing

What LLM engineering lacks most today is not a stronger model, but **the institutionalization of distrust in probabilistic execution** — distrust verbal promises, while respecting the probabilistic layer's capabilities: hand "was it done, was it done fully" to deterministic machines, and leave "was it done well" to the model.

Verbal promises will never become reliable — until there's a mechanical door on the path to keeping them.

And gate builders must remember: gates are code too, and code can lie too — so the gates themselves must be gated.

---

## Appendix: The Campaign in Numbers

- Scan: 42 skills + 17 rule files → 40+ candidates → benefit-formula filtering → **27 problem points fixed** (6 severe / 15 medium / 6 minor)
- Built: 1 `gate-switch` engine (7 frozen primitives) + 9 validators + 22 gate specs + 1 L3 framework template + 1 SPDT dispatch switch
- Deleted: 33 blocker rules that had never fired (dead chain + keyword stubs)
- Discovered: 929 accumulated violations (incl. 400+ contract-drift false positives), 4.24% experience reuse rate, structural self-scoring inflation
- Traced: 3 audit ledgers (gate_switch / dispatch_switch / bug_fix), 90+ flip records, B/A ratios feeding retrospectives continuously
- Open source: all universal skeletons at [dsh-skills](https://github.com/xu-jin-cs/dsh-skills), one curl to install

*2026-08-15 · Methodology retrospective · Companion to the Mandatory-Completion Gate family, gate-switch, and dispatch_switch*
