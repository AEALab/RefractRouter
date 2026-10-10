# 研究与历史证据索引

本索引从用户入门文档中分离历史研究，保留实验原始产物和原冻结合同。
日期与结论只说明对应证据范围，不将旧结果改写成当前版本的普遍收益。

## 当前产品资料

| 内容 | 入口 |
| --- | --- |
| 安装、升级与回滚 | [安装指南](refractagent-local-quickstart.md) |
| 规划路由 | [日常使用](planning-routing-daily-use.md)、[支持矩阵](planning-routing-support-matrix.md) |
| 独立 Base URL | [独立模型接口](independent-model-router.md) |
| 自动路由实际工作 | [实际流程](automatic-real-workflows.md)、[最新工具与审核更新](automatic-tool-evidence-and-next-steps.md) |
| 金额与订阅 | [统一金额计价](currency-only-migration.md) |
| 职责边界 | [架构](architecture.md) |

## DAG 与模型分配研究

| 证据 | 对应问题与结论 |
| --- | --- |
| [v0.1](../reports/v0.1-real/) | 初期基准可运行；任务 oracle 与节点 oracle 未证明同质收益 |
| [v0.2 节点质量](../reports/v0.2-node-quality/repeated-agent-plan/README.md) | 中间合同与评审缺项，收益证据不足 |
| [v0.3 修复后复验](../reports/v0.3-contract-recovery/repeated-agent-plan/README.md) | 有异构分配，但完整配对与最佳单模型对照仍不足 |
| [v0.4 重复对照](../reports/v0.4-known-rejections/repeated-agent-plan/README.md) | 有效配对中未取得更优质量／费用，保留失败与缺项 |
| [Issue #32 后续实验](../reports/dag-decomposition/) | 并发、失败切换、独立样本、规划与任务适用性研究 |
| [成本与时间开发对照](../reports/pareto-development-v1/README.md) | 资源点与质量达标 Pareto 前沿分别判断 |
| [自动 Direct／DAG](../reports/automatic-functional-20261004/README.md) | 实际调用路径与冻结范围核对，不将模拟当收益 |
| [自动路由价值](../reports/automatic-value-20261005/README.md) | 失败、输出容量与对照完整性须计入总体成本 |
| [质量与最终纠正](../reports/automatic-quality-20261009/README.md) | 真实内容、审核误放行与有界纠正分别记录 |

当前不能根据这些历史实验宣称：只要拆分 DAG 就比最合适的固定模型更便宜或更快。
对照须使用相同任务质量标准，并计入规划、汇总、Judge、失败及全部尝试。

## 规划策略与 Judge

| 证据 | 范围 |
| --- | --- |
| [六策略稳定性](../reports/dsh-strategy-stability-20260929-v3/README.md) | 受控主路径，不解释成开放任务成功率 |
| [复杂分支](../reports/dsh-strategy-branches-20260930-v3/README.md) | 升级、保持、返工、复审与工具续接 |
| [Advisor](../reports/advisor-acceptance-20260928/README.md) | 审核后端固定案例与失败边界 |
| [Composite](../reports/composite-acceptance-20260928/README.md) | Task／Stage 交接及独立状态 |
| [Escalation](../reports/escalation-acceptance-20260927/README.md) | 本地与 LLM 判别、一次接管与账本 |
| [Jev／Laya 对照](../reports/planning-jev-comparison-20260930/README.md) | 同题、分用途标签与判别质量，不合并为总体准确率 |
| [OpenRouter Jev](../reports/jev-openrouter-20261003/README.md) | 新渠道实际工具接线；正常工具请求的误升级风险保留 |
| [Jev 门槛](../reports/jev-gate-review-20261003/README.md) | 获选概率、confidence、分动作实验与默认规则 |

## 原始证据原则

历史 AFP、USD、用量与失败状态按原协议保留，不改成今天的 CNY 账本。
重算、诊断与复验另存；未知用量预留不删除。受控错误夹具只验证功能，不能冒充自然任务收益。
Hermes 等历史接线继续保留，本轮产品维护范围仍为 DSH 与 Codex CLI。
