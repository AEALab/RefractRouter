# 配对策略比较

A 为完整来源包的一次调用；B 为单模型七节点；C 为按独立节点评分选出的路线，允许全程使用同一模型。同模型 B/A 比较拆解效果，C/B 比较选模效果。组内最佳基线要求所有候选成功且完成评审；它是事后选择，不是可部署路由器。所有差值使用相同任务／轮次配对，探针与评审费用另计。

| 对照 | 有效／排除对数 | 质量差均值 | 费用差均值（AFP） | 延迟差均值（毫秒） |
|---|---:|---:|---:|---:|
| dag:cheap 对比 one-shot:cheap | 0／1 | 不可用 | 不可用 | 不可用 |
| dag:mid 对比 one-shot:mid | 1／0 | 1.0 | 3.59975 | 35281 |
| dag:strong 对比 one-shot:strong | 0／1 | 不可用 | 不可用 | 不可用 |
| node-mixed 对比 dag:cheap | 1／0 | -9.0 | 3.64995 | 719 |
| node-mixed 对比 dag:mid | 1／0 | -4.0 | -0.6768 | 477 |
| node-mixed 对比 dag:strong | 1／0 | 4.0 | -5.7145 | -44319 |
| node-mixed 对比 one-shot:cheap | 0／1 | 不可用 | 不可用 | 不可用 |
| node-mixed 对比 one-shot:mid | 1／0 | -3.0 | 2.92295 | 35758 |
| node-mixed 对比 one-shot:strong | 0／1 | 不可用 | 不可用 | 不可用 |
| node-mixed 对比 dag-oracle | 1／0 | -9.0 | 3.64995 | 719 |
| node-mixed 对比 one-shot-oracle | 0／1 | 不可用 | 不可用 | 不可用 |

正的质量差表示前者质量更高；负的费用差或延迟差表示前者更省或更快。
路线费用不含选路探针和评审费用，实验总开销另计。

## 同一配对集合

- dag:cheap 对比 one-shot:cheap：无。
  排除 report_001／1；原因代码：one-shot:cheap:failed-execution。
- dag:mid 对比 one-shot:mid：report_001／1。
- dag:strong 对比 one-shot:strong：无。
  排除 report_001／1；原因代码：one-shot:strong:failed-execution。
- node-mixed 对比 dag:cheap：report_001／1。
- node-mixed 对比 dag:mid：report_001／1。
- node-mixed 对比 dag:strong：report_001／1。
- node-mixed 对比 one-shot:cheap：无。
  排除 report_001／1；原因代码：one-shot:cheap:failed-execution。
- node-mixed 对比 one-shot:mid：report_001／1。
- node-mixed 对比 one-shot:strong：无。
  排除 report_001／1；原因代码：one-shot:strong:failed-execution。
- node-mixed 对比 dag-oracle：report_001／1。
- node-mixed 对比 one-shot-oracle：无。
  排除 report_001／1；原因代码：one-shot-oracle:failed-execution, one-shot-oracle:missing-final-output, one-shot-oracle:missing-judge, one-shot-oracle:judge:incomplete-single-model-evaluations。
