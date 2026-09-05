# v0.1 真实模型阶段就绪报告

## 结论

真实模型实验的代码、数据、模型清单、独立裁判、人工抽检入口、预算保护和 DSH 证据链已
实现并通过本地验证。当前状态是 **ready for paid dry run**，不是“真实模型结果已完成”。
运行环境未设置 `OPENAI_API_KEY`，因此没有产生真实质量分、真实 API 成本或真实线上延迟，
也不能据此给出真实模型 Go / No-Go 结论。

## 已实现范围

- 20 个固定任务：训练集 10 个、测试集 10 个；每个任务 7 个节点、8 份冻结 source。
- 三档候选模型与一个候选池外独立 judge 的日期快照、价格和请求参数 manifest。
- OpenAI-compatible Chat Completions adapter；密钥只从环境变量读取。
- input/output/cache/reasoning token、实际调用成本、延迟、重试、finish reason、request ID
  和标准化失败类型遥测。
- 七种策略，包括固定强上游上下文的 isolated node probe，以及 node-oracle composed
  end-to-end rerun。
- 确定性 HTML/source trace 检查与独立 judge 的五维 100 分 rubric。judge 必须逐条核验
  冻结的 `expected_claims`；不受 source pack 支持的主张会限制证据分。
- 10% 冻结样本的人工复核模板；judge 与人工分差超过 10 分时，最终结论强制 No-go。
- baseline、质量—生产成本 Pareto front、oracle gap、failure taxonomy、逐次运行记录和
  artifact evidence index。
- 显式付费开关与生产/评测两类预算上限；默认命令只做零成本 preflight。

## 本次验证证据

验证日期：2026-09-05。

- 测试：`46 passed`（含 DSH bundle manifest、Standard Schema、原生 service 接线与
  plugin provenance 测试）。
- canonical fake-model 隔离复跑：`pass`，issues 为空，六项 artifact hash 全部生成。
- real-model final preflight：`pass`，issues 为空，`credential_available=false`。
- 数据集 SHA-256：`8b5e6842132bd02928a8b5db52d40b24c98f098d6ecc975eaf25f8b26f62df17`。
- 模型 manifest SHA-256：`0a7b0f4e502c660584cac25e8d20d020b606dcf60ab2f2d2596f9cdbdef369b9`。
- 20-task corpus SHA-256：`ca9d3919aed145177fcd15b8e55541df261de7273abfcdb174aea77356548157`。
- 实验代码 SHA-256：`09e7e6f95834a27d1ddf84ba22352840579350f0aeaf37dce641e4ab671f94ad`。
- 验证环境：Python 3.12.13、DeepAgents 0.7.13、LangGraph 1.2.11、DSH 0.1.1-rc.2。
- DSH plugin：隔离 profile 安装与配置组合成功；真实 headless tool call 返回 `pass`、
  `issues=[]`、`invoked_by=dsh-plugin`，且仍为零费用 preflight。

这些 hash 来自当前工作树内容；提交后应由 CI 在干净 checkout 中再次生成持久证据。

## 调用计划与估算

估算假设每个生产调用 4,000 input / 1,200 output tokens、每个 judge 调用 8,000 input /
1,200 output tokens，不计算缓存折扣。它是按冻结价格和最贵候选模型计算的保守上界，
不是账单或已发生费用。

| 阶段 | 训练 / 测试任务 | 生产调用 | Judge 调用 | 总调用 | 保守估算 |
|---|---:|---:|---:|---:|---:|
| dry-run | 0 / 1 | 56 | 5 | 61 | $1.95 |
| pilot | 5 / 5 | 455 | 35 | 490 | $15.40 |
| final | 10 / 10 | 910 | 70 | 980 | $30.80 |

## 分数与结论如何产生

每个最终 HTML 先执行确定性检查，再交给候选池外 judge。需求覆盖、证据准确性和 HTML
有效性取两者较低值；分析深度、结构与可读性取 judge 分。五维上限依次为
25/25/20/15/15，总分 100。生产执行成本与 judge 评测成本分开统计；Pareto 比较只使用
生产成本。

真实 gate 同时支持 Issue #1 的两条收益路径：同成本（差距小于 5%）时质量至少提高 5 分，
或同质量（差距小于 2 分）时生产成本至少降低 20%。任一路径都还必须满足 node-oracle
p95 关键路径延迟不超过 task-oracle 的 120%、成功率不退化、两种 oracle 的 judge 覆盖率
均为 100%。只有 final 模型运行完成、冻结的 10% 人工抽检通过且 DSH 证据一致，才会产生
最终 Go；否则为 No-go 或 incomplete。

## 尚未完成

1. 经授权执行 1-task 付费 dry run，并审查输出、失败类型与实际成本。
2. dry run 通过后执行 10-task pilot；如需观察波动，用 `--repeats 3` 并相应提高预算。
3. pilot 通过后执行 20-task final benchmark。
4. 人工填写冻结的 4 条 audit record 并运行 finalizer。
5. 在明确允许披露仓库上下文后，通过 `refractrouter_validate` plugin tool call 复核真实
   阶段，发布最终 Go / No-Go。
