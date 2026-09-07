# Real-model baseline summary

Quality, cost and latency use the same successful, independently judged task/repeat cohort.
Success and judge coverage use all expected blocks; excluded costs remain in totals and the run ledger.
Partial cohorts are descriptive; paired comparisons are the primary comparison evidence.

| Strategy | Quality mean ± sd | Production cost mean ± sd (AFP) | p50 / p95 latency (ms) | Success | Judge coverage |
|---|---:|---:|---:|---:|---:|
| `node-oracle` | 89.000 ± 0.000 | 6.29415000 ± 0.00000000 | 89814 / 89814 | 100.00% | 100.00% |
| `node-type-rule` | 91.000 ± 0.000 | 5.84220000 ± 0.00000000 | 92268 / 92268 | 100.00% | 100.00% |
| `strong-all` | 96.000 ± 0.000 | 9.30160000 ± 0.00000000 | 115671 / 115671 | 100.00% | 100.00% |
| `task-oracle` | 96.000 ± 0.000 | 9.30160000 ± 0.00000000 | 115671 / 115671 | 100.00% | 100.00% |
| `weak-all` | 87.000 ± 0.000 | 0.55335000 ± 0.00000000 | 50627 / 50627 | 100.00% | 100.00% |

Cohorts (task/repeat; same blocks for quality, cost and latency):
- `node-oracle`: 1/1 blocks: report_001/1.
- `node-type-rule`: 1/1 blocks: report_001/1.
- `strong-all`: 1/1 blocks: report_001/1.
- `task-oracle`: 1/1 blocks: report_001/1.
- `weak-all`: 1/1 blocks: report_001/1.
