# Paired strategy comparisons

Descriptive paired differences; repeats are nested within tasks. Identical assignments measure generation/judge variation, not a routing change. Task-oracle is the post-hoc best of all three judged single-model runs in that block. Node-oracle is a local greedy selection on fixed upstream probes, not a global upper bound.

| Comparison | Pairs / excluded | Tasks | Repeats | Quality Δ mean ± sd | Cost Δ mean ± sd | Identical assignments | Mixed |
|---|---:|---:|---|---:|---:|---:|---:|
| node-oracle vs strong-all | 0 / 3 | 0 | [] | None ± None | None ± None | 0 | 0 |
| node-oracle vs task-oracle | 0 / 3 | 0 | [] | None ± None | None ± None | 0 | 0 |
| node-type-rule vs strong-all | 3 / 0 | 1 | [1, 2, 3] | -1.66666667 ± 1.24721913 | -4.74471667 ± 1.00674353 | 0 | 3 |
| node-type-rule vs task-oracle | 0 / 3 | 0 | [] | None ± None | None ± None | 0 | 0 |

Positive quality Δ favors the candidate. Negative cost Δ means lower production cost.
Probe and judge expenses are reported separately in the run ledger.
