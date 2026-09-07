# Paired strategy comparisons

Descriptive paired differences; repeats are nested within tasks. Identical assignments measure generation/judge variation, not a routing change. Task-oracle is the post-hoc best of all three judged single-model runs in that block. Node-oracle is a local greedy selection on fixed upstream probes, not a global upper bound.

| Comparison | Pairs / excluded | Tasks | Repeats | Quality Δ mean ± sd | Cost Δ mean ± sd | Identical assignments | Mixed |
|---|---:|---:|---|---:|---:|---:|---:|
| node-oracle vs strong-all | 1 / 0 | 1 | [1] | -7.0 ± 0.0 | -3.00745 ± 0.0 | 0 | 1 |
| node-oracle vs task-oracle | 1 / 0 | 1 | [1] | -7.0 ± 0.0 | -3.00745 ± 0.0 | 0 | 1 |
| node-type-rule vs strong-all | 1 / 0 | 1 | [1] | -5.0 ± 0.0 | -3.4594 ± 0.0 | 0 | 1 |
| node-type-rule vs task-oracle | 1 / 0 | 1 | [1] | -5.0 ± 0.0 | -3.4594 ± 0.0 | 0 | 1 |

Included cohorts (identical for every displayed delta):
- node-oracle vs strong-all: report_001/1.
- node-oracle vs task-oracle: report_001/1.
- node-type-rule vs strong-all: report_001/1.
- node-type-rule vs task-oracle: report_001/1.

Positive quality Δ favors the candidate. Negative cost Δ means lower production cost.
Probe and judge expenses are reported separately in the run ledger.
