# Real-model baseline summary

Quality, cost and latency use the same successful, independently judged task/repeat cohort.
Success and judge coverage use all expected blocks; excluded costs remain in totals and the run ledger.
Partial cohorts are descriptive; paired comparisons are the primary comparison evidence.

| Strategy | Quality mean ± sd | Production cost mean ± sd (AFP) | p50 / p95 latency (ms) | Success | Judge coverage |
|---|---:|---:|---:|---:|---:|
| `node-oracle` | 92.000 ± 1.633 | 5.50523333 ± 1.10285804 | 91402 / 96785 | 100.00% | 100.00% |
| `node-type-rule` | 85.667 ± 4.190 | 3.90506667 ± 0.73239189 | 60134 / 77635 | 100.00% | 100.00% |
| `strong-all` | 88.333 ± 3.091 | 7.70696667 ± 1.51075208 | 74931 / 105662 | 100.00% | 100.00% |
| `task-oracle` | 94.500 ± 1.500 | 2.76920000 ± 2.21230000 | 55788 / 61174 | 100.00% | 66.67% |
| `weak-all` | 90.500 ± 2.500 | 0.56832500 ± 0.01142500 | 48699 / 49694 | 66.67% | 66.67% |

Cohorts (task/repeat; same blocks for quality, cost and latency):
- `node-oracle`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `node-type-rule`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `strong-all`: 3/3 blocks: report_001/1, report_001/2, report_001/3.
- `task-oracle`: 2/3 blocks: report_001/1, report_001/2.
  Excluded report_001/3: missing-judge, judge:incomplete-single-model-evaluations.
- `weak-all`: 2/3 blocks: report_001/1, report_001/2.
  Excluded report_001/3: failed-execution, missing-final-output, missing-judge, judge:missing-final-output.
