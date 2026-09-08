# Paired strategy comparisons

Simulation only; no measured model-quality or cost benefit. A is one model invocation with the complete frozen source pack; B is seven DAG nodes with one model; C is a composed node-local greedy route, which may select a single model. Compare B/A for the same model to measure decomposition; compare C/B to measure assignment. Oracles require every candidate in that family to succeed and be judged, are post-hoc, and are not deployable routers. All displayed deltas use the same task/repeat pair set. Probe and judge costs are separate.

| Comparison | Pairs / excluded | Tasks | Repeats | Quality Δ mean ± sd | Cost Δ mean ± sd | Identical assignments | Mixed |
|---|---:|---:|---|---:|---:|---:|---:|
| dag:cheap vs one-shot:cheap | 3 / 0 | 1 | [1, 2, 3] | 0.0 ± 0.0 | 0.19655 ± 0.0 | 0 | 0 |
| dag:mid vs one-shot:mid | 3 / 0 | 1 | [1, 2, 3] | 0.0 ± 0.0 | 0.98275 ± 0.0 | 0 | 0 |
| dag:strong vs one-shot:strong | 3 / 0 | 1 | [1, 2, 3] | 0.0 ± 0.0 | 2.16205 ± 0.0 | 0 | 0 |
| node-mixed vs dag:cheap | 3 / 0 | 1 | [1, 2, 3] | 0.0 ± 0.0 | 0.0 ± 0.0 | 3 | 0 |
| node-mixed vs dag:mid | 3 / 0 | 1 | [1, 2, 3] | 0.0 ± 0.0 | -1.0956 ± 0.0 | 0 | 0 |
| node-mixed vs dag:strong | 3 / 0 | 1 | [1, 2, 3] | 0.0 ± 0.0 | -2.739 ± 0.0 | 0 | 0 |
| node-mixed vs one-shot:cheap | 3 / 0 | 1 | [1, 2, 3] | 0.0 ± 0.0 | 0.19655 ± 0.0 | 0 | 0 |
| node-mixed vs one-shot:mid | 3 / 0 | 1 | [1, 2, 3] | 0.0 ± 0.0 | -0.11285 ± 0.0 | 0 | 0 |
| node-mixed vs one-shot:strong | 3 / 0 | 1 | [1, 2, 3] | 0.0 ± 0.0 | -0.57695 ± 0.0 | 0 | 0 |
| node-mixed vs dag-oracle | 3 / 0 | 1 | [1, 2, 3] | 0.0 ± 0.0 | 0.0 ± 0.0 | 3 | 0 |
| node-mixed vs one-shot-oracle | 3 / 0 | 1 | [1, 2, 3] | 0.0 ± 0.0 | 0.19655 ± 0.0 | 0 | 0 |

Included cohorts (identical for every displayed delta):
- dag:cheap vs one-shot:cheap: report_001/1, report_001/2, report_001/3.
- dag:mid vs one-shot:mid: report_001/1, report_001/2, report_001/3.
- dag:strong vs one-shot:strong: report_001/1, report_001/2, report_001/3.
- node-mixed vs dag:cheap: report_001/1, report_001/2, report_001/3.
- node-mixed vs dag:mid: report_001/1, report_001/2, report_001/3.
- node-mixed vs dag:strong: report_001/1, report_001/2, report_001/3.
- node-mixed vs one-shot:cheap: report_001/1, report_001/2, report_001/3.
- node-mixed vs one-shot:mid: report_001/1, report_001/2, report_001/3.
- node-mixed vs one-shot:strong: report_001/1, report_001/2, report_001/3.
- node-mixed vs dag-oracle: report_001/1, report_001/2, report_001/3.
- node-mixed vs one-shot-oracle: report_001/1, report_001/2, report_001/3.

Positive quality Δ favors the candidate. Negative cost Δ means lower production cost.
Probe and judge expenses are reported separately in the run ledger.
