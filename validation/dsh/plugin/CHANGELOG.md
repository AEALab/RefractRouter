# 变更日志

## 0.7.0

- 新增 `refractrouter_task` 与 `taskProfilePath`，由 Python 完成文本 DAG 规划、A/B 选模、执行和独立评审。
- 合并既有基准候选策略时按 runner 职责区分参数，避免将基准选模选项传入文本任务。

- 文本任务新增有界并发、provider 并发上限及启动间隔参数；默认串行。
- 结果增加执行模式、最大并发、观测峰值和预测时延，Python 负责调度与原子预算。
- A/B 使用完整 DAG 调度时延；B 不再奖励对总耗时没有贡献的分支加速。
- 支持分层 profile 与固定校准/测试协议，提供零调用预检及完整模拟对照。
- 取消或失败后停止新派发并结算在途调用；真实组合收益仍待完整对照验证。

## 0.6.0

- 新增 `acceptanceCriteria`，原样转交 Python 核心并冻结规划验收条件。
- 模型规划采用 `text-task-plan-v2`，明确依赖字段与理由、节点契约、能力需求和验收覆盖。
  旧版显式计划仍可使用并标注缺少交接契约，模型生成计划不得降级。
- 零调用预览改为单节点，避免把固定模板当成任务拆分；提供并行机会、依赖深度及汇总
  诊断产物。运行时仍串行，质量 profile 仍是迁移预测。
- 核心校验结构化交接输出，失败时保存原文与费用并阻止后续执行；插件只负责接入。

## 0.5.0

- 新增有类型的 `selectionPolicy`，经 DSH 基准 runner 原样传给 Python。
- 保留 v1 默认行为，支持显式 v2 排除已知契约拒绝；未知失败继续阻断。
- 选模语义与配对样本规则留在 Python，并补充参数契约回归。

## 0.4.1

- Migrate plugin and service contracts to strict TypeScript, with explicit host/config/tool/result
  types and validated Python evidence projection. Malformed evidence fields fail closed.
- Build the ESM entry and declarations into `dist/`; pack only the runtime distribution, with no
  runtime dependencies. Retain endpoint, credential, budget and replay safeguards.

## 0.4.0

- Add `contract-replay` for the seven frozen issue #25 writer failures. Default to preflight,
  limit repeats to three, prohibit retries, stop after the first failure, and retain all existing
  Agent Plan credential and budget controls. Replay results establish contract validity only.

## 0.3.0

- Send AFP benchmark calls directly to the Agent Plan OpenAI-compatible Chat Completions endpoint,
  avoiding the DSH stdio bridge that could stall before dispatch.
- Reject AFP manifests unless every model uses provider `ark-plan` and the exact
  `https://ark.cn-beijing.volces.com/api/plan/v3` base URL, preventing fallback to ordinary Ark
  pay-as-you-go billing.
- Resolve the Agent Plan key through DSH credentials only for a paid operation, inject it into the
  scrubbed child environment, and persist prompt-free `model-progress.ndjson` request evidence.

## 0.2.2

- Enforce per-request timeouts locally while consuming DSH streams, including providers that ignore
  the supplied abort signal.
- Persist prompt-free request start and finish records so long paid runs expose their current model
  and completed-call progress.

## 0.2.1

- Reject DSH model routes whose provider-owned retry policy is not normal mode with zero retries.
- Carry the runner's per-model timeout across the stdio bridge and abort stalled DSH streams.

## 0.2.0

- Add an AFP-billed Volcengine Agent Plan manifest and generic billing-unit budgets.
- Route Agent Plan calls through the hosting DSH `llm` service over a bounded stdio bridge, so the
  provider credential remains owned by DSH and is never copied into the Python child.
- Validate the frozen provider/model routes before a paid run and expose the billing unit in
  structured preflight and evidence results.
- Reject paid ceilings below the conservative preflight estimate, reserve an estimated call before
  each invocation, and default DSH runner retries to zero.

## 0.1.1

- Bound evidence and standard-stream capture, fail on truncation, and redact resolved credentials
  from returned diagnostics.
- Declare and test the v0.1 DSH, Node, and pnpm compatibility contract.
- Add clean-profile installation lifecycle validation and release, troubleshooting, upgrade, and
  rollback documentation.

## 0.1.0

- Add the `refractrouter_validate` Cordis tool with preflight-safe defaults and two-level paid-run
  budget enforcement.
- Use DSH subprocess, sandbox, policy, and credential services while keeping benchmark logic in the
  Python runner.
