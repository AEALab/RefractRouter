# Real-model Pareto front

The frontier uses mean judged quality and mean production cost. p95 latency is reported as a separate deployment guardrail.

| Strategy | Quality mean | Production cost mean (AFP) | p95 latency (ms) | On quality-cost front |
|---|---:|---:|---:|:---:|
| `node-oracle` | 91.500 | 5.36502500 | 81017 | No |
| `node-type-rule` | 91.333 | 5.06706667 | 71355 | No |
| `strong-all` | 84.333 | 9.16153333 | 89691 | No |
| `task-oracle` | 94.000 | 2.12130000 | 77164 | Yes |
| `weak-all` | 90.333 | 0.66526667 | 76655 | Yes |

Cohorts (task/repeat; same blocks for quality, cost and latency):
- `node-oracle`: 2/3 blocks: report_001/2, report_001/3.
  Excluded report_001/1: failed-execution, missing-final-output, missing-judge, judge:missing-final-output.
- `node-type-rule`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `strong-all`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `task-oracle`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `weak-all`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
