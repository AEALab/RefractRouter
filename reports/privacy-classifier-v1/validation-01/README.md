# 隐私分级器验证 A3（validation-01）

跟踪 Issue #87。本目录为分级器验证的冻结证据：两个标注集、确定性第一道指标、
第二道调用合同与 fail-safe 放置检查。全部分级器本地调用，零网络、零付费模型调用。

- 数据集与 sha256 见 validation.json 的 datasets 字段；
- 严格门槛只统计非 known_issue 样本，门禁值见 gate 字段；
- known_issue 是保守设计的已文档化代价，见 known_issues 与 limitations。

结论：通过严格门禁。
