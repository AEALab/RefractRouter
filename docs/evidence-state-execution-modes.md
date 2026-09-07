# Evidence ownership and execution-mode comparison

## Decision and scope

The third Flash single-model DAG run in the preceding three-repeat experiment returned synthesis
analysis without the required evidence array. Its writer, renderer and verifier never ran. This is
an observed v0.3 handoff failure; it does not establish that a one-call report would pass or cost less.
The saved response and its original verdict remain unchanged.

The explicit v0.4 protocol makes Python the owner of validated extraction evidence. It adds no
implementation language or business logic to the TypeScript host. Existing task defaults, source
files, v0.3 prompts and archived artifacts retain their original protocol. User approval on
2026-09-07 covers this implementation and offline validation, not a new paid experiment or public
publication of local evidence.

## Evidence lifetime

`with_evidence_state` creates a task copy. It adds extraction as a direct parent of synthesis,
generation, rendering and verification. `evidence_artifact` reads only the extraction node's raw
output, validates source ID/title/hash and nonempty claims, and exposes frozen evidence items plus
the raw output's SHA-256. A descendant cannot substitute its own evidence array. Snapshots persist
each completed route's extraction record separately from raw model responses.

Synthesis returns analysis with `[source_###]` citations. Generation returns a title and cited
sections. Neither returns evidence arrays. Rendering reads the application-owned extraction record
to construct the source trace. Missing or invalid extraction blocks dependent calls before spending;
unknown or unextracted citations and replacement evidence arrays are rejected. The executor,
adapter, node judge and selection validator use the same evidence rules and direct-parent context.

The state validates provenance identity, not truth. An extraction claim can still misrepresent its
source, and a citation can still fail to support an assertion. Independent semantic node judging
uses rubric v0.4; final reports retain the same independent final rubric v0.1 for every arm.
The state is reconstructed from immutable raw extraction in each check; it is not a mutable cache or
a new model-generated summary. Evidence still occupies input tokens when consumers need it.

Alternatives were continued model-to-model copying, silently repairing missing arrays, and a global
unversioned relaxation. Copying preserves the observed failure mode and spends output tokens on
unchanged data. Repair would hide raw contract failures; a global relaxation would change historical
interpretation. The chosen approach requires explicit dependencies and a new rubric. Roll back by
using the original task and runner; never relabel v0.3 evidence as v0.4.

## Frozen A/B/C experiment

| Arm | Production per candidate / route | Purpose |
|---|---:|---|
| A: one-shot | 1 call per candidate | Full source pack to complete standalone HTML |
| B: single-model DAG | 7 calls per candidate | Same model executes the complete v0.4 DAG |
| C: composed DAG | 7 calls for the selected route | v2 independently judged node assignments |

The initial candidate pool remains Flash, M3 and Pro, with K3 excluded from routing and reserved as
judge. The broader catalog is already separate from this frozen pool. Expanding candidates and
changing decomposition simultaneously would make attribution harder and increase probe costs.

A and B are compared for each identical model and task/repeat; C is compared to every A and B as
well as their complete family-best baselines. Family-best is post-hoc and unavailable if any member
fails execution or judging. It is not a deployable router. C uses frozen strong-model reference
contexts for 21 probes and reruns the selected assignments in its own DAG. All nodes may select the
same model; no diversity is forced. Node-local selection does not prove globally optimal composition.

All arms use the same frozen task, sources, final requirements, independent final judge, temperature
zero, thinking disabled, 8192-token output limit and no retries. A sees the full sources in its only
call. B/C perform extraction and downstream writing separately; that is the intended intervention.
Final semantic analysis scores do not depend on an intermediate synthesis node being present.

One repeat has 52 production calls (3 A + 21 B + 21 probes + 7 C) and 28 judges (21 node + 7 final),
80 total. Post-hoc baseline reuse incurs no new requests. Report per-route costs separately from
probe and evaluation costs; the experimental selection overhead is not a zero-cost online router.
Every delta uses its declared identical task/repeat pairs and reports missing pairs. One-task results
cannot establish broad generalization. Fewer than three complete real repeats cannot pass Go.

## Reproduction without paid calls

```bash
uv run python experiments/run_execution_modes.py --output-dir /tmp/refractrouter-v04-preflight-new
uv run python experiments/run_execution_modes.py --mode offline --repeats 3 \
  --output-dir /tmp/refractrouter-v04-offline-new
```

Both require fresh output directories. Offline uses deterministic synthetic report and judge
fixtures, records zero network calls and zero actual paid cost, and labels every gate
`Simulation-only`. Fixture scores and token estimates are not evidence of model quality or savings.
The output includes frozen transformed tasks, code/input hashes, raw observations, extraction
snapshots, exhaustive node matrix, selection decisions, paired comparisons and artifact hashes.

DSH plugin 0.6.0 adds `execution-modes` and forwards it to the fixed Python runner. TypeScript only
validates tool arguments and deployment limits. Paid mode requires the native boundary marker,
exact Agent Plan endpoint, configured credential and both ceilings; defaults remain paid-disabled.
The marker is a local deployment guard, not a security boundary against arbitrary local code.
Malformed/truncated final judge responses retain their paid usage and raw failure records rather
than disappearing from the cost ledger. Any such response makes that observation unavailable.

## Next paid admission proposal

The one-repeat zero-call estimate is 202.39 production + 453.38 evaluation = **655.76 AFP** before
outer DSH usage (total uses unrounded components). Assumptions are 4000 production input tokens,
8000 judge input tokens and each model's 8192 output cap, with no cache discount. These input
assumptions are estimates, not hard token bounds; call reservations and actual costs are tracked.

A concrete future envelope is 210 production + 460 evaluation + 0.5 outer = **670.5 AFP** for one
fresh admission run. It is a proposal, not authorization. Inspect completeness, source grounding,
per-model B/A quality-cost-latency pairs and C/B pairs before proposing any repeated paid experiment.
No new live calls are part of the implementation validation.
