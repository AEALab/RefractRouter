# Paired strategy comparisons

Descriptive paired differences; repeats are nested within tasks. Identical assignments measure generation/judge variation, not a routing change. Task-oracle is the post-hoc best of all three judged single-model runs in that block. Node-oracle is a local greedy selection on fixed upstream probes, not a global upper bound.

| Comparison | Pairs / excluded | Tasks | Repeats | Quality Δ mean ± sd | Cost Δ mean ± sd | Identical assignments | Mixed |
|---|---:|---:|---|---:|---:|---:|---:|
| node-oracle vs strong-all | 2 / 1 | 1 | [2, 3] | 7.5 ± 1.5 | -3.734175 ± 3.932675 | 0 | 2 |
| node-oracle vs task-oracle | 2 / 1 | 1 | [2, 3] | -4.5 ± 3.5 | 2.598275 ± 3.346875 | 0 | 2 |
| node-type-rule vs strong-all | 3 / 0 | 1 | [1, 2, 3] | 7.0 ± 3.55902608 | -4.09446667 ± 1.83461416 | 0 | 3 |
| node-type-rule vs task-oracle | 3 / 0 | 1 | [1, 2, 3] | -2.66666667 ± 7.03957069 | 2.94576667 ± 1.54431591 | 0 | 3 |

Included cohorts (identical for every displayed delta):
- node-oracle vs strong-all: report_001/2, report_001/3.
  Excluded report_001/1: node-oracle:failed-execution, node-oracle:missing-final-output, node-oracle:missing-judge, node-oracle:judge:missing-final-output.
- node-oracle vs task-oracle: report_001/2, report_001/3.
  Excluded report_001/1: node-oracle:failed-execution, node-oracle:missing-final-output, node-oracle:missing-judge, node-oracle:judge:missing-final-output.
- node-type-rule vs strong-all: report_001/1, report_001/2, report_001/3.
- node-type-rule vs task-oracle: report_001/1, report_001/2, report_001/3.

Positive quality Δ favors the candidate. Negative cost Δ means lower production cost.
Probe and judge expenses are reported separately in the run ledger.
