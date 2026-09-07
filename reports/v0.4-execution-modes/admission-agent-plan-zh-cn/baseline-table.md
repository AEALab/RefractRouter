# 执行方式对照汇总

质量、成本和延迟使用相同的成功且完成独立评审的任务／轮次集合。
失败与缺失评审不会被静默丢弃，已发生的费用仍计入总账。

| 策略 | 质量均值 | 路线费用均值（AFP） | 延迟中位数／95分位（毫秒） | 成功率 | 评审覆盖率 |
|---|---:|---:|---:|---:|---:|
| `dag-oracle` | 100.0 | 0.689 | 67339／67339 | 100.00% | 100.00% |
| `dag:cheap` | 100.0 | 0.689 | 67339／67339 | 100.00% | 100.00% |
| `dag:mid` | 95.0 | 5.01575 | 67581／67581 | 100.00% | 100.00% |
| `dag:strong` | 87.0 | 10.05345 | 112377／112377 | 100.00% | 100.00% |
| `node-mixed` | 91.0 | 4.33895 | 68058／68058 | 100.00% | 100.00% |
| `one-shot-oracle` | 不可用 | 不可用 | 不可用／不可用 | 0.00% | 0.00% |
| `one-shot:cheap` | 不可用 | 不可用 | 不可用／不可用 | 0.00% | 100.00% |
| `one-shot:mid` | 94.0 | 1.416 | 32300／32300 | 100.00% | 100.00% |
| `one-shot:strong` | 不可用 | 不可用 | 不可用／不可用 | 0.00% | 100.00% |

## 比较样本

- `dag-oracle`：有效 1／预期 1。
- `dag:cheap`：有效 1／预期 1。
- `dag:mid`：有效 1／预期 1。
- `dag:strong`：有效 1／预期 1。
- `node-mixed`：有效 1／预期 1。
- `one-shot-oracle`：有效 0／预期 1。
  排除 report_001／1；原因代码：failed-execution, missing-final-output, missing-judge, judge:incomplete-single-model-evaluations。
- `one-shot:cheap`：有效 0／预期 1。
  排除 report_001／1；原因代码：failed-execution。
- `one-shot:mid`：有效 1／预期 1。
- `one-shot:strong`：有效 0／预期 1。
  排除 report_001／1；原因代码：failed-execution。
