# Real-model Pareto front

The frontier uses mean judged quality and mean production cost. p95 latency is reported as a separate deployment guardrail.

| Strategy | Quality mean | Production cost mean (AFP) | p95 latency (ms) | On quality-cost front |
|---|---:|---:|---:|:---:|
| `node-oracle` | 58.000 | 0.99005000 | 50419 | Yes |
| `node-type-rule` | 17.500 | 0.99225000 | 17136 | No |
| `strong-all` | 27.500 | 3.18010000 | 37120 | No |
| `task-oracle` | 27.500 | 0.36870000 | 51716 | Yes |
| `weak-all` | 27.500 | 0.36870000 | 51716 | Yes |
