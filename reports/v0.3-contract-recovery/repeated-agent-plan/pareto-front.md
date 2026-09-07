# Real-model Pareto front

The frontier uses mean judged quality and mean production cost. p95 latency is reported as a separate deployment guardrail.

| Strategy | Quality mean | Production cost mean (AFP) | p95 latency (ms) | On quality-cost front |
|---|---:|---:|---:|:---:|
| `node-oracle` | 91.500 | 3.57668333 | 79630 | No |
| `node-type-rule` | 91.333 | 5.06706667 | 71355 | No |
| `strong-all` | 84.333 | 9.16153333 | 89691 | No |
| `task-oracle` | 94.000 | 2.12130000 | 77164 | Yes |
| `weak-all` | 90.333 | 0.66526667 | 76655 | Yes |
