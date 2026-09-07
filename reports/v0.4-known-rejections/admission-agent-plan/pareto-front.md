# Real-model Pareto front

The frontier uses mean judged quality and mean production cost. p95 latency is reported as a separate deployment guardrail.

| Strategy | Quality mean | Production cost mean (AFP) | p95 latency (ms) | On quality-cost front |
|---|---:|---:|---:|:---:|
| `node-oracle` | 89.000 | 6.29415000 | 89814 | No |
| `node-type-rule` | 91.000 | 5.84220000 | 92268 | Yes |
| `strong-all` | 96.000 | 9.30160000 | 115671 | Yes |
| `task-oracle` | 96.000 | 9.30160000 | 115671 | Yes |
| `weak-all` | 87.000 | 0.55335000 | 50627 | Yes |

Cohorts (task/repeat; same blocks for quality, cost and latency):
- `node-oracle`: 1/1 blocks: report_001/1.
- `node-type-rule`: 1/1 blocks: report_001/1.
- `strong-all`: 1/1 blocks: report_001/1.
- `task-oracle`: 1/1 blocks: report_001/1.
- `weak-all`: 1/1 blocks: report_001/1.
