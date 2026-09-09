# 策略配对比较复核

配对差值仅作描述性观察，重复轮次嵌套于任务。相同分配的差异反映生成或评审波动；task-oracle 是同轮三条经过评审的单模型路线中的事后最优者，node-oracle 是固定上游探针上的局部贪心候选，不能当作全局上界。

| 对照 | 配对数 / 排除数 | 任务数 | 轮次 | 质量差均值 ± 标准差 | 费用差均值 ± 标准差 | 相同分配数 | 混合分配数 |
|---|---:|---:|---|---:|---:|---:|---:|
| node-oracle vs strong-all | 3 / 0 | 1 | [1, 2, 3] | 3.66666667 ± 3.29983165 | -2.20173333 ± 2.04184032 | 0 | 3 |
| node-oracle vs task-oracle | 2 / 1 | 1 | [1, 2] | -2.5 ± 0.5 | 1.985325 ± 2.578025 | 0 | 2 |
| node-type-rule vs strong-all | 3 / 0 | 1 | [1, 2, 3] | -2.66666667 ± 1.24721913 | -3.8019 ± 2.02371157 | 0 | 3 |
| node-type-rule vs task-oracle | 2 / 1 | 1 | [1, 2] | -6.0 ± 0.0 | 1.3746 ± 1.4163 | 0 | 2 |

纳入集合（各差值使用相同样本）：
- node-oracle vs strong-all: report_001/1, report_001/2, report_001/3.
- node-oracle vs task-oracle: report_001/1, report_001/2.
  排除 report_001/3: task-oracle:missing-judge, task-oracle:judge:incomplete-single-model-evaluations.
- node-type-rule vs strong-all: report_001/1, report_001/2, report_001/3.
- node-type-rule vs task-oracle: report_001/1, report_001/2.
  排除 report_001/3: task-oracle:missing-judge, task-oracle:judge:incomplete-single-model-evaluations.

质量差为正表示候选得分更高；费用差为负表示候选生产费用更低。
探针与评审费用在运行账本中单列。
