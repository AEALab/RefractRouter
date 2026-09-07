# Real-model Pareto front

The frontier uses mean judged quality and mean production cost. p95 latency is reported as a separate deployment guardrail.

| Strategy | Quality mean | Production cost mean (AFP) | p95 latency (ms) | On quality-cost front |
|---|---:|---:|---:|:---:|
| `node-oracle` | 92.000 | 5.50523333 | 96785 | Yes |
| `node-type-rule` | 85.667 | 3.90506667 | 77635 | Yes |
| `strong-all` | 88.333 | 7.70696667 | 105662 | No |
| `task-oracle` | 94.500 | 2.76920000 | 61174 | No |
| `weak-all` | 90.500 | 0.56832500 | 49694 | No |

Cohorts (task/repeat; same blocks for quality, cost and latency):
- `node-oracle`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `node-type-rule`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `strong-all`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `task-oracle`: 2/3 blocks: report_001/1, report_001/2.
  Excluded report_001/3: missing-judge, judge:incomplete-single-model-evaluations.
- `weak-all`: 2/3 blocks: report_001/1, report_001/2.
  Excluded report_001/3: failed-execution, missing-final-output, missing-judge, judge:missing-final-output.
