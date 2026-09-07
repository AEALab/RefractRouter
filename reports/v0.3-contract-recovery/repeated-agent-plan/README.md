# Three-repeat oracle validation after contract recovery

The 2026-09-07 Agent Plan run completed all 237 dispatched requests on clean commit
`3e9f99d97bf9bb769732aa94065590a9d34b608a`. The recorded configuration remained
`all-candidates-required-v1`, prompt protocol v0.3, node checks v0.3 and independent Kimi
node/final judging. This is one canonical task (`report_001`) repeated three times, not three
independent tasks. No retries or sampling-count changes were introduced.

**Decision: Insufficient-evidence.** All 63 matrix cells are recorded, 62 are eligible and
14 are selected. The first node-oracle block is unjudged because the frozen selection policy
stopped on one known contract rejection. The other two blocks execute genuinely mixed routes,
but neither beats its paired best single-model report on quality. No pilot is started.

## Final quality and production cost

Scores come from independent final judges; N/A is not replaced by a deterministic fallback.
Cost is the executed route's production cost, excluding probe and judge overhead.

| Strategy | Repeat 1 score | Repeat 2 score | Repeat 3 score | Mean quality ± sd | Mean route cost (AFP) |
|---|---:|---:|---:|---:|---:|
| All Flash | 90 | 100 | 81 | 90.333 ± 7.760 | 0.66526667 |
| All M3 | 85 | 89 | 92 | 88.667 ± 2.867 | 5.12316667 |
| All Pro | 85 | 86 | 82 | 84.333 ± 1.700 | 9.16153333 |
| Fixed node-type mix | 95 | 88 | 91 | 91.333 ± 2.867 | 5.06706667 |
| Task-oracle (best single per block) | 90 (Flash) | 100 (Flash) | 92 (M3) | 94.000 ± 4.320 | 2.12130000 |
| Composed node-oracle | N/A | 92 | 91 | 91.500 ± 0.500, repeats 2–3 only | 5.36502500, repeats 2–3 only |

Flash is the best single model by three-repeat mean quality in this sample. Task-oracle is the
post-hoc best single model *within each repeat*, and therefore switches to M3 in repeat 3.
The node-oracle row uses the same two executed, judged runs for both quality and cost.
Generic raw/reviewed aggregates retain a three-block cost mean of 3.57668333 AFP, which includes
the skipped first block's zero execution cost. That value must not be paired with the two-run
quality mean as an apparent route efficiency result. The recorded failure and probe expenses
are still included in the run ledger.

## Paired comparisons

| Candidate / baseline | Included repeats | Quality delta mean ± sd | Cost delta mean (AFP) | Critical-path latency delta mean |
|---|---|---:|---:|---:|
| Node-oracle / all Pro | 2, 3 | +7.5 ± 1.5 | -3.734175 | -2.1455 s |
| Node-oracle / task-oracle | 2, 3 | -4.5 ± 3.5 | +2.598275 | +17.749 s |
| Fixed mix / all Pro | 1, 2, 3 | +7.0 ± 3.559 | -4.09446667 | -8.2873 s |
| Fixed mix / task-oracle | 1, 2, 3 | -2.667 ± 7.040 | +2.94576667 | +2.774 s |

Positive quality delta favors the candidate; negative cost/latency deltas favor the candidate.
These are descriptive within-task differences, not significance tests or evidence of general
performance across tasks. Node-oracle is a greedy node-local choice on fixed Pro upstream
probes; composed results, rather than sums of isolated node scores, determine final quality.

The two valid node-oracle runs have different mixed assignments:

| Node | Repeat 2 | Repeat 3 |
|---|---|---|
| parse_requirements | M3 | Flash |
| build_outline | Flash | M3 |
| extract_evidence | M3 | Flash |
| synthesize_analysis | M3 | M3 |
| write_report | Pro | Pro |
| render_html | M3 | Flash |
| verify_report | Pro | M3 |

Repeat 2 costs 6.53065 AFP for node-oracle versus 0.58550 AFP for its best single model,
with quality 92 versus 100. Repeat 3 costs 4.19940 versus 4.94800 AFP, with quality 91 versus
92; that is a 15.13% saving and 1.518× critical-path latency, below the frozen 20% saving
threshold and above its 1.2× latency limit. The complete three-repeat gate remains unavailable.

## Remaining failure and unchanged policy

Repeat 1's Flash synthesis probe returned a JSON object containing `analysis` but no
`evidence`. It completed with `finish_reason=stop` in one attempt. Shared local checks
correctly recorded `invalid-evidence`, score 0 and `method=deterministic-rejection`; this is
a known output-contract rejection, not a transport failure or an unknown judge result.
The same probe passed in repeats 2 and 3. All nine full single-model runs completed and were
independently judged, including all three M3 reports.

The frozen policy requires every candidate to execute successfully, so the one rejected probe
caused `node-quality-incomplete` for repeat 1's composed route. No route was forced and no
rule was changed during the experiment. A possible future policy may exclude known rejected
candidates while keeping unknown evaluations fail-closed; that change requires a separately
versioned decision and validation. This archive does not adopt it.
[Issue #29](https://github.com/AEALab/RefractRouter/issues/29) records this follow-up and the
need to keep displayed quality/cost cohorts aligned; issue #22 remains open.

## Cost and provenance

| This run | AFP |
|---|---:|
| Candidate execution, including probes | 114.31870 |
| Independent node judging | 241.60800 |
| Independent final judging | 56.92300 |
| Outer DSH calls (2) | 1.19945 |
| Total | **414.04915** |

Only `https://ark.cn-beijing.volces.com/api/plan/v3` was used. Production and evaluation
admission ceilings were 740 and 1290 AFP. Costs are reconstructed from task-specific usage
and frozen coefficients, not account-wide settlement. The paid profile was disabled afterward.

Across the existing 2505-AFP authorization, known cost is now 807.33615 AFP. Retaining the
16.192-AFP estimate for the earlier interrupted request gives 823.52815 AFP accounted for
and 1681.47185 AFP remaining. The earlier request's actual settlement remains unknown.
Total known outer DSH cost is 4.22525 AFP against its original 5-AFP allowance.

The approval chain was checked first with an unauthenticated HEAD request, which was approved
and returned 401 as expected. Local configuration still selected automatic review. No approval
settings were changed and the completed seven-case replay was not repeated.

## Evidence and offline audit

- [Original matrix and complete node outputs](node-quality-matrix.json),
  [readable matrix](node-quality-matrix.md), and [incremental records](node-evaluations.ndjson).
- [Paired comparison records](reviewed-strategy-comparisons.json),
  [single-model summary](reviewed-single-models.md), and [reviewed gate](reviewed-oracle-gap.md).
- [DSH evidence](dsh-evidence.json), [request telemetry](model-progress.ndjson),
  [budget ledger](cost-accounting.json), and [outer usage](outer-agent-usage.json).
- [Audit](reviewed-audit.json): all 36 original indexed hashes, 63 output/upstream hashes,
  identical upstream contexts across each three-candidate group, 9 single-model artifacts,
  15 strategy artifacts, and 237/237 matching request starts/finishes verified.

All requests finished with `stop`, each with one attempt. No original artifact is overwritten;
the `reviewed-*` files are reproducible offline:

```bash
uv run python experiments/review_node_quality_evidence.py \
  reports/v0.3-contract-recovery/repeated-agent-plan
```

The archive was scanned for the active credential before publication. No raw DSH session or
account-wide billing data is included.

Repository verification after archiving: `uv run --offline pytest` passed all 94 tests,
including the DSH Node contract checks. Original artifact hashes, credential scan and report
links were also checked without any model calls.
