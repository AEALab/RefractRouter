Simulation only; not empirical evidence.

# Real-model baseline summary

Quality, cost and latency use the same successful, independently judged task/repeat cohort.
Success and judge coverage use all expected blocks; excluded costs remain in totals and the run ledger.
Partial cohorts are descriptive; paired comparisons are the primary comparison evidence.

| Strategy | Quality mean ± sd | Production cost mean ± sd (AFP) | p50 / p95 latency (ms) | Success | Judge coverage |
|---|---:|---:|---:|---:|---:|
| `dag-oracle` | 100.000 ± 0.000 | 0.27390000 ± 0.00000000 | 3339 / 3339 | 100.00% | 100.00% |
| `dag:cheap` | 100.000 ± 0.000 | 0.27390000 ± 0.00000000 | 3339 / 3339 | 100.00% | 100.00% |
| `dag:mid` | 100.000 ± 0.000 | 1.36950000 ± 0.00000000 | 3339 / 3339 | 100.00% | 100.00% |
| `dag:strong` | 100.000 ± 0.000 | 3.01290000 ± 0.00000000 | 3339 / 3339 | 100.00% | 100.00% |
| `node-mixed` | 100.000 ± 0.000 | 0.27390000 ± 0.00000000 | 3339 / 3339 | 100.00% | 100.00% |
| `one-shot-oracle` | 100.000 ± 0.000 | 0.07735000 ± 0.00000000 | 770 / 770 | 100.00% | 100.00% |
| `one-shot:cheap` | 100.000 ± 0.000 | 0.07735000 ± 0.00000000 | 770 / 770 | 100.00% | 100.00% |
| `one-shot:mid` | 100.000 ± 0.000 | 0.38675000 ± 0.00000000 | 770 / 770 | 100.00% | 100.00% |
| `one-shot:strong` | 100.000 ± 0.000 | 0.85085000 ± 0.00000000 | 770 / 770 | 100.00% | 100.00% |

Cohorts (task/repeat; same blocks for quality, cost and latency):
- `dag-oracle`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `dag:cheap`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `dag:mid`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `dag:strong`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `node-mixed`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `one-shot-oracle`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `one-shot:cheap`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `one-shot:mid`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `one-shot:strong`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
