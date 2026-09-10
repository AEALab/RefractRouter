# 真实模型基线复核

质量、费用和时延使用同一组成功且经过独立评审的任务与轮次。
成功率和评审覆盖率以全部预期样本为分母；排除样本的费用仍计入总账。
不完整集合仅作描述性观察，策略比较以同轮配对为依据。

| 策略 | 质量均值 ± 标准差 | 生产均费 ± 标准差（AFP） | p50 / p95 时延（ms） | 成功率 | 评审覆盖率 |
|---|---:|---:|---:|---:|---:|
| `node-oracle` | 92.000 ± 1.633 | 5.50523333 ± 1.10285804 | 91402 / 96785 | 100.00% | 100.00% |
| `node-type-rule` | 85.667 ± 4.190 | 3.90506667 ± 0.73239189 | 60134 / 77635 | 100.00% | 100.00% |
| `strong-all` | 88.333 ± 3.091 | 7.70696667 ± 1.51075208 | 74931 / 105662 | 100.00% | 100.00% |
| `task-oracle` | 94.500 ± 1.500 | 2.76920000 ± 2.21230000 | 55788 / 61174 | 100.00% | 66.67% |
| `weak-all` | 90.500 ± 2.500 | 0.56832500 ± 0.01142500 | 48699 / 49694 | 66.67% | 66.67% |

比较集合（任务/轮次；各指标使用相同样本）：
- `node-oracle`: 3/3 个样本： report_001/1, report_001/2, report_001/3.
- `node-type-rule`: 3/3 个样本： report_001/1, report_001/2, report_001/3.
- `strong-all`: 3/3 个样本： report_001/1, report_001/2, report_001/3.
- `task-oracle`: 2/3 个样本： report_001/1, report_001/2.
  排除 report_001/3: missing-judge, judge:incomplete-single-model-evaluations.
- `weak-all`: 2/3 个样本： report_001/1, report_001/2.
  排除 report_001/3: failed-execution, missing-final-output, missing-judge, judge:missing-final-output.
