# Real-model Pareto front

The frontier uses mean judged quality and mean production cost. p95 latency is reported as a separate deployment guardrail.

| Strategy | Quality mean | Production cost mean (AFP) | p95 latency (ms) | On quality-cost front |
|---|---:|---:|---:|:---:|
| `node-oracle` | 9.167 | 0.56726667 | 38355 | No |
| `node-type-rule` | 86.667 | 3.02880000 | 57411 | No |
| `strong-all` | 88.333 | 7.77351667 | 87599 | No |
| `task-oracle` | 100.000 | 0.50558333 | 49258 | Yes |
| `weak-all` | 88.333 | 0.50558333 | 49258 | No |
