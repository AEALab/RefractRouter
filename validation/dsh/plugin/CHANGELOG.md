# Changelog

## 0.7.0

- 新增 `k3-baseline` 类型化阶段及独立评审交接路径，支持准备、组合两个原生调用阶段。
- 保持默认零调用、单轮零重试、Agent Plan 专用端点与部署额度限制。
- 本阶段允许内部评审额度为零；外部评审费用另计，未知费用不按零处理。
- 新增原生工具到 Python 的零调用验证；成本选模、评审校准、材料冻结和核算由 Python 负责。

## 0.6.0

- Add the typed `execution-modes` phase for Python's explicit v0.4 A/B/C report comparison.
- Default that phase to v2 selection, require zero retries and at most three repeats, and retain
  disabled paid runs, exact Agent Plan endpoint and both deployment ceilings.
- Validate a real zero-call subprocess preflight through the registered tool. Evidence ownership,
  experimental comparisons, accounting and judging remain in Python.

## 0.5.0

- Add a typed `selectionPolicy` argument and forward it through the DSH runner to Python.
- Preserve v1 defaults; expose explicit v2 known-rejection exclusion with fail-closed unknowns.
- Keep policy semantics and comparison cohorts in Python; add argument contract regressions.

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
