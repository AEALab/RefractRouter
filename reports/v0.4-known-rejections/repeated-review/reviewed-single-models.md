# Real-model baseline summary

Quality, cost and latency use the same successful, independently judged task/repeat cohort.
Success and judge coverage use all expected blocks; excluded costs remain in totals and the run ledger.
Partial cohorts are descriptive; paired comparisons are the primary comparison evidence.

| Strategy | Quality mean ± sd | Production cost mean ± sd (AFP) | p50 / p95 latency (ms) | Success | Judge coverage |
|---|---:|---:|---:|---:|---:|
| `cheap` | 90.500 ± 2.500 | 0.56832500 ± 0.01142500 | 48699 / 49694 | 66.67% | 66.67% |
| `mid` | 92.333 ± 2.625 | 4.84641667 ± 0.13473127 | 55977 / 61192 | 100.00% | 100.00% |
| `strong` | 88.333 ± 3.091 | 7.70696667 ± 1.51075208 | 74931 / 105662 | 100.00% | 100.00% |

Cohorts (task/repeat; same blocks for quality, cost and latency):
- `cheap`: 2/3 blocks: report_001/1, report_001/2.
  Excluded report_001/3: failed-execution, missing-final-output, missing-judge, judge:missing-final-output.
- `mid`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `strong`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
