# Paired strategy comparisons

Descriptive paired differences; repeats are nested within tasks. Identical assignments measure generation/judge variation, not a routing change. Task-oracle is the post-hoc best of all three judged single-model runs in that block. Node-oracle is a local greedy selection on fixed upstream probes, not a global upper bound.

| Comparison | Pairs / excluded | Tasks | Repeats | Quality Δ mean ± sd | Cost Δ mean ± sd | Identical assignments | Mixed |
|---|---:|---:|---|---:|---:|---:|---:|
| node-oracle vs strong-all | 3 / 0 | 1 | [1, 2, 3] | 3.66666667 ± 3.29983165 | -2.20173333 ± 2.04184032 | 0 | 3 |
| node-oracle vs task-oracle | 2 / 1 | 1 | [1, 2] | -2.5 ± 0.5 | 1.985325 ± 2.578025 | 0 | 2 |
| node-type-rule vs strong-all | 3 / 0 | 1 | [1, 2, 3] | -2.66666667 ± 1.24721913 | -3.8019 ± 2.02371157 | 0 | 3 |
| node-type-rule vs task-oracle | 2 / 1 | 1 | [1, 2] | -6.0 ± 0.0 | 1.3746 ± 1.4163 | 0 | 2 |

Included cohorts (identical for every displayed delta):
- node-oracle vs strong-all: report_001/1, report_001/2, report_001/3.
- node-oracle vs task-oracle: report_001/1, report_001/2.
  Excluded report_001/3: task-oracle:missing-judge, task-oracle:judge:incomplete-single-model-evaluations.
- node-type-rule vs strong-all: report_001/1, report_001/2, report_001/3.
- node-type-rule vs task-oracle: report_001/1, report_001/2.
  Excluded report_001/3: task-oracle:missing-judge, task-oracle:judge:incomplete-single-model-evaluations.

Positive quality Δ favors the candidate. Negative cost Δ means lower production cost.
Probe and judge expenses are reported separately in the run ledger.
