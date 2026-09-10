# 自动拆分与执行

RefractAgent 新增 `auto` 模式：先根据原始任务生成 DAG，再由 Python 核心选择模型、
检查整张图的容量和资源约束、执行节点并独立评审最终答案。简单任务允许一个节点；
需要分别分析的任务可形成多个节点。直接 HTTP 模型最多两个节点并发，DSH stdio 仍串行。

`single` 保持直接回答，`compare` 保持固定成本／风险模板。默认模式保持 `single`。
`auto` 需要额外的真实规划调用；预检和模拟不会自动规划，也不能当作拆分质量证据。

## 使用方法

使用自己已有的 provider/model 配置执行：

```bash
refractagent run --task '在给定材料内分别分析方案成本和实施风险，再给出建议。材料：……' \
  --template auto --provider-config ./provider-config.json \
  --mode live --execute-paid-run --max-output-tokens 4096 \
  --production-budget 40 --evaluation-budget 40 --timeout-ms 300000
```

生成 DSH 自动模式配置，然后按安装指南启动：

```bash
refractagent dsh-config --output ./refractagent-auto.json --template auto \
  --provider-config ./provider-config.json --mode live --max-output-tokens 4096
```

按既有部署流程启用生成配置中的 `allowPaidRuns`。更新插件和 Python 核心后一起使用；
自动模式会核对核心确实返回模型生成的计划，避免把旧核心的固定模板当成自动拆分。
推荐把任务的明确交付要求写入请求文件的 `acceptanceCriteria`；所有节点和最终评审都会收到。

## 规划、能力与容量的衔接

规划器现在能看到可用模型的输入／输出上限、画像覆盖、质量下限、剩余费用、时间和并发限制。
默认规划模型按配置或清单中的能力预测优先选择；节点执行仍按所选的省成本／均衡／质量策略路由。
它不能为了命中画像而改变任务难度或风险。输出契约、原始验收条目和最终交付仍需完整保留。

两种画像来源分别处理：

- **用户配置**：自动计划形成后，按实际节点匹配配置预测；记录为 `configured`、零观测。
  输入容量根据完整消息和父输出上限预留；预计输入用量采用完整基础消息和计划中的父输出需求。
  容量是能容纳多少，预测是预计使用多少，二者分开记录；预测不构成质量或时延保证。
- **实测画像**：继续严格匹配已观测分层，缺少覆盖时报告缺口，不扩充历史画像、不重标风险，
  也不自动退回配置预测。此前冻结的 #39/#40 失败仍然保留。

所有真实请求派发前，根据实际序列化输入和输出上限预留费用，累计费用不能突破硬预算。
父输出预留系数只是一种容量估算；运行时仍检查实际输入，过长时停止，不截断任务材料。
整张图在第一个节点调用前检查可用模型，避免先执行可用分支，再发现汇总节点完全不可执行。

应用自动模式允许对已结算的规划结构错误修正一次，错误、两次原文与费用全部保存。
请求文件可设置 `maxPlanRepairs: 0` 禁用；底层 HTTP 重试始终为零。
本版没有执行中再拆或节点输出修复。显式提供的计划不自动改写。
规划失败、无可行路由、未知用量和最终质量不达标分别保留；最终分数也必须达到质量下限。

## 查看结果和成本

每次调用生成独立目录，包含 `request.json`、`manifest.json`、`profile.json`、`plan.json`、
`result.json`、`summary.json`，有正文时另存 `answer.md`。
结果中保留规划原文、编译前计划、执行计划、节点分配、输入输出、逐次用量及费用。
供应商响应的原始 usage 与尝试数也归档，便于核对零重试和费用。

`summary.json` 展示规划、节点执行、评审费用和完整墙钟耗时；DSH 的运行信息也展示这些字段。
墙钟耗时从核心开始处理任务到最终评审结束，包含规划、路由检查及执行；DSH 进程启动开销另计。
AFP 是冻结费率下的订阅用量记账，不等同于新增现金账单。
有未知用量时单列保守预留，不能把它解释为零费用或已确认的实际消耗。

## 验收范围

新开发样例与未参与调试的任务分别运行；自动路线不输入手写 DAG，直接路线使用相同模型配置、
策略、材料、验收条件、预算和输出上限。每条路线都记录质量、完整 AFP 和总耗时。
两条路线独立生成，单次比较不能排除供应商负载和生成波动，不给出总体收益结论。

预检命令默认零调用，实跑必须绑定其返回的源码和协议摘要：

```bash
uv run python experiments/run_automatic_dag_acceptance.py \
  --protocol data/research/automatic-dag-acceptance-v3.json \
  --split holdout --output-dir /tmp/automatic-dag-preflight
```

原始报告见 [自动 DAG 验收](../reports/automatic-dag/README.md)。
