# Oracle Gap Analysis

| Metric | task-oracle | node-oracle | Delta |
|---|---:|---:|---:|
| Task score | 100.000 | 100.000 | +0.000 |
| Cost (USD) | 0.016764 | 0.004141 | -0.012623 |
| Critical path (ms) | 3441 | 8721 | 2.53x |

- Cost reduction: 75.30%
- Latency ratio: 2.53x
- Full three-objective gate: **No-go**

The current canonical task shows a clear quality-cost advantage for node-oracle, but it fails the latency ceiling in the v0.1 Go/No-Go rule. Node candidates are probed with a fixed strong-model upstream context.
