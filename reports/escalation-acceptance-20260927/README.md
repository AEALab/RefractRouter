# Escalation v4 有限验收

## 范围

本目录保存 `escalation-decision-v1` 的 24 条冻结 Judge 案例、本地 Laya-MLX 离线结果、
Ark 轻量 LLM 结果，以及真实 DSH 接线的零调用与运行证据。验收只覆盖文本与原生工具，
不覆盖图片、影片、子 Agent 共享预算或相对 Static 的收益。

## Judge 结果

| 后端 | 匹配 | 明确缺陷放行 | 合格放行 | 时延 | 费用 | 结论 |
| --- | ---: | ---: | ---: | --- | ---: | --- |
| `deepseek-v4-flash`，关闭思考 | 20/24 | 0/6 | 6/6 | P50 1601 ms，P95 1984 ms | 0.52185 AFP | 达到有限日常使用门槛 |
| `laya-multilingual-mlx` 固定 revision | 5/24 | 0/6 | 0/6 | 冷启动 1073 ms；暖机 P50 22.9 ms，P95 24.7 ms | 无 API 费用 | 实验状态 |
| `glm-5.3-flash`，1024 token | 未形成有效批次 | 无有效判别 | 无有效判别 | 首次调用 23428 ms | 用量见中断证据 | 实验状态 |

轻量 LLM 的四条不匹配均为预期 `UNCERTAIN`、实际 `DEFECT`。两者都会立即接管，因此没有
错误放行；但轨迹原因的分类精度仍有限，不能把 20/24 解释为普遍正确率。

## 中断批次

真实验收保留三个互不覆盖的批次：

1. `llm-judge/`：`glm-5.3-flash` 默认思考占用 1023/1024 输出 token，HTTP 200 但正文为空。
2. `llm-judge-disabled-thinking/`：提供方以 HTTP 400 明确拒绝 `thinking.type=disabled`。
3. `llm-judge-deepseek-flash/`：前两案有效，第三案把候选工具调用 ID 当作证据 ID；严格合同
   停止批次。随后合同明确此区别，并把完整合同摘要纳入预检。

最终有效批次为 `llm-judge-contract-v2/`。所有批次均为零 HTTP 自动重试；出现新问题后使用
新输出目录和新预检摘要，没有覆盖旧证据或只重跑失败项后混合统计。

## 证据索引

- `local-laya.json`：本地 24 案逐条原始概率、用量与延迟。
- `llm-judge-contract-v2/preflight.json`：有效 Judge 批次的零调用预检。
- `llm-judge-contract-v2/judge-results.jsonl`：24 次实际调用的逐条用量、请求 ID 和判别。
- `llm-judge-contract-v2/judge-summary.json`：有限门槛与实际 0.52185 AFP 汇总。
- `llm-judge*/model-progress.ndjson`：请求级派发、HTTP、结束原因和用量证据。
- 各中断目录的 `interruption.json`：停止原因和下一批次唯一变更。
- `dsh-normal/preflight.json`：真实 DSH 工具续接流程的冻结模型、调用数与 AFP 上限。
- `dsh-normal/result.json`：真实 DSH 流程汇总。四次模型调用完成两次执行与两次审核，
  执行一次原生 `pwd` 工具，总计 2.3822 AFP，未创建 DAG，也未发生接管。
- `dsh-normal/stdout.log`：宿主最终交付的真实工具结果。

## DSH 接线范围

已在用户原有 `headless` profile 完成一条全真实正常工具续接：起始模型先生成原生
`pwd` 工具调用，Judge 放行后由 DSH 执行，第二个高效候选再次通过 Judge 后交付。
运行共四次模型调用、一次工具执行，耗时 13.444 秒，实际使用 2.3822 AFP。

明确缺陷、停滞、无法判断、工具调用丢弃和强模型锁定已由确定性 DSH 契约测试覆盖；
24 条真实 Judge 案例证明实际后端能够触发这些判别。当前没有把“固定错误候选、真实 Judge、
真实强模型接管和宿主工具”串成同一条付费 DSH 流程，因此不把它列为已完成的全真实接管
验收。该限制不影响状态机和宿主合同验收，但实际接管端到端仍需独立夹具提供方后再补证据。
