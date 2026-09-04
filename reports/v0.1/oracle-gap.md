# Oracle Gap Analysis

| Metric | task-oracle | node-oracle | Delta |
|---|---:|---:|---:|
| Task score | 100.000 | 100.000 | +0.000 |
| Cost (USD) | 0.100416 | 0.025152 | -0.075264 |
| Critical path (ms) | 4036 | 9316 | 2.31x |

- Cost reduction: 74.95%
- Latency ratio: 2.31x
- Full three-objective gate: **No-go**

The current canonical task shows a clear quality-cost advantage for node-oracle, but it fails the latency ceiling in the v0.1 Go/No-Go rule. Node candidates are probed with a fixed strong-model upstream context.
