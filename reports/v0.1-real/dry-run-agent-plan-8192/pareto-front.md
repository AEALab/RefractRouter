# Real-model Pareto front

The frontier uses mean judged quality and mean production cost. p95 latency is reported as a separate deployment guardrail.

| Strategy | Quality mean | Production cost mean (AFP) | p95 latency (ms) | On quality-cost front |
|---|---:|---:|---:|:---:|
| `node-oracle` | 84.000 | 0.50680000 | 41082 | No |
| `node-type-rule` | 93.000 | 3.03530000 | 43055 | No |
| `strong-all` | 86.000 | 8.77525000 | 83907 | No |
| `task-oracle` | 100.000 | 0.50640000 | 49527 | Yes |
| `weak-all` | 100.000 | 0.50640000 | 49527 | Yes |
