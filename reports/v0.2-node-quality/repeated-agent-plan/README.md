# Three-repeat Agent Plan node-quality validation

Date: 2026-09-06. Execution commit: `d1602cf` (PR #24). Phase: one-task dry run,
`report_001`, three repeats. **Benchmark incomplete; oracle decision: Insufficient-evidence.**
Follow-up: [issue #25](https://github.com/AEALab/RefractRouter/issues/25).

## Evidence and interpretation

All 215 requests returned successfully with `finish_reason=stop`, one attempt and no retries.
The run saved all 63 matrix cells (7 nodes × 3 models × 3 repeats), 9 single-model artifacts,
and 15 strategy artifacts. Of the 63 cells, 60 are eligible; three M3 generation cells fail
the frozen output contract. Recorded coverage is complete, but admissible evaluation coverage
and final oracle comparisons are incomplete. DSH correctly reports `fail: benchmark-incomplete`.

Read [reviewed-summary.json](reviewed-summary.json),
[reviewed-baseline-table.md](reviewed-baseline-table.md),
[reviewed-single-models.md](reviewed-single-models.md), and
[reviewed-oracle-gap.md](reviewed-oracle-gap.md) for the corrected presentation.
Original run summaries are retained unchanged for provenance: their unjudged oracle fallback
scores (100 for task-oracle; 27.5/0/0 for node-oracle) **are not independent quality scores**.
Reviewed summaries display these as N/A and exclude incomplete strategies from Pareto selection.
Raw task-oracle success flags refer only to the fallback execution, not oracle validity.
Costs/latencies of failed or unexecuted strategies do not establish a routing advantage.

## Three-repeat comparison

Quality uses the independent Kimi final judge with the frozen deterministic caps. Costs below
are mean production AFP per task, excluding probes and evaluation. Standard deviations are
population descriptive statistics across three repeats of one task, not confidence intervals.

| Strategy | Repeat 1 / 2 / 3 quality | Mean ± sd | Mean production AFP | Valid final judgments |
|---|---|---:|---:|---:|
| All Flash | 92 / 83 / 90 | 88.333 ± 3.859 | 0.50558333 | 3/3 |
| All Pro (most expensive candidate) | 89 / 89 / 87 | 88.333 ± 0.943 | 7.77351667 | 3/3 |
| Fixed mixed rule | 87 / 89 / 84 | 86.667 ± 2.055 | 3.02880000 | 3/3 |
| All M3 | N/A / N/A / N/A | N/A | 2.65825000 (failed attempts) | 0/3 |
| Adaptive node-oracle | N/A / N/A / N/A | N/A | Not a valid completed-route comparison | 0/3 |
| Full three-candidate task-oracle | N/A / N/A / N/A | N/A | Not a valid oracle comparison | 0/3 |

The fixed mixed rule costs 61.04% less than all Pro, with mean quality 1.667 points lower.
All Flash ties Pro on average quality and costs less; against Flash the fixed mix costs 5.99×
as much and has lower mean quality. This sample does not establish a mixed-routing advantage
over the best observed fixed single model. It also does not establish that adaptive routing
cannot work: its final output was not successfully evaluated.

As a supplementary observation only, the best **valid available** single result in each repeat
is Flash 92, Pro 89, Flash 90 (mean 90.333). This excludes failed M3 and is not the frozen
three-candidate task-oracle. It must not replace that baseline in the Go gate.

## Failure diagnosis

- M3 full runs return HTML at `write_report` in all three repeats, which requires JSON.
  Its generation probes return HTML in repeats 2 and 3; repeat 1 returns JSON with missing
  evidence titles. These are frozen contract failures, not HTTP errors or truncation.
- Repeat 1 selects M3 for parse/outline/extraction/synthesis/render, Flash for writing, and
  Pro for verification. The composed Flash writer preserves all eight source IDs, titles
  and hashes but drops every required evidence `claim`. The executor rejects the output;
  rendering/verification are skipped and no final judge is available.
- Repeats 2 and 3 do not execute a node-oracle route because the current fail-closed policy
  rejects the incomplete probe evaluation. Matrices preserve all attempted candidates.
- M3 has no valid final judgment in any repeat, so the full task-oracle is invalid in all three.

See [node-quality-matrix.md](node-quality-matrix.md) and
[node-quality-matrix.json](node-quality-matrix.json) for per-cell scores, raw outputs,
exact parent contexts, dimensions, rationales, eligibility and selected assignments.
Issue #25 tracks scoped node schemas, evidence preservation, real-output regression fixtures,
and checkpoint-based minimal replay before another full comparison. No post-hoc contract or
gate relaxation was applied to this run.

## Usage and authorization

All model requests used the Agent Plan `/api/plan/v3` endpoint. The signed-in subscription was
checked before execution and additional pay-as-you-go usage switches were off. The temporary
DSH profile's `allowPaidRuns` was reset to `false` after completion.

The user approved total admission budgets of 2505 AFP. After interrupting the initial scorer
bug run, unused production reserve was shifted to evaluation within that same total. The fresh
corrected run used ceilings of 1160 production / 1270 evaluation AFP; including prior measured
usage, the unsettled-request reserve and the full 5-AFP outer allowance, admitted exposure was
2497.618 AFP. Per-call reservations are estimates, not provider settlement guarantees.

| Ledger | AFP |
|---|---:|
| Corrected run production (including probes) | 81.21435 |
| Corrected run node judging | 225.76300 |
| Corrected run final judging | 31.04200 |
| Corrected run total | 338.01935 |
| Initial interrupted run, known benchmark usage | 46.42600 |
| Outer DSH Flash, both attempts combined | 1.82535 |
| Combined known usage-derived cost | **386.27070** |
| Initial interrupted request, unsettled estimate retained | 16.19200 |
| Known cost plus unsettled reserve | **402.46270** |

These are task-specific token-usage estimates using frozen AFP coefficients, not account-wide
billing totals. The interrupted request has no finish telemetry; actual cost remains unknown.
See [cost-accounting.json](cost-accounting.json), [outer-agent-usage.json](outer-agent-usage.json),
and the [initial interruption](../interrupted-duplicate-source-check/interruption.json).

## Offline verification

All 36 original indexed artifact hashes match. Every matrix output and parent-context hash
matches its saved payload; each node/repeat gives the same parent context to all three models.
[reviewed-audit.json](reviewed-audit.json) records these checks and endpoint/request counts.
The credential value and credential-shaped strings were checked before committing the archive;
no credential was included. Only task-specific evidence is published.

Reproduce the reviewed summaries without API calls or rewriting original indexed artifacts:

```bash
uv run python experiments/review_node_quality_evidence.py \
  reports/v0.2-node-quality/repeated-agent-plan
uv run pytest
```

The review corrects presentation only; it does not repair model outputs, reevaluate them, or
turn the original incomplete run into a successful validation. Issue #22 remains open until
the missing oracle evidence is resolved; the larger #5 pilot remains deferred.
