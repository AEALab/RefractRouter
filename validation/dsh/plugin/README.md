# RefractRouter DSH 验证与接入插件

## 0.10.0：RefractAgent 本机策略模型

安装 Python 核心 `refractrouter` 0.2.0 和本插件后，DSH 模型列表增加
`refractagent/economy`（省成本）、`refractagent/balanced`（均衡）和
`refractagent/quality`（质量优先）。它们调用同一 Python 核心，支持文本任务、
对话上下文、整任务与预设 DAG；当前模型接口不生成 DSH 工具调用。

收到核心 wheel 和插件 tgz 后，可在任务工作目录执行：

```bash
uv tool install /absolute/path/refractrouter-0.2.0-py3-none-any.whl
dsh plugin --profile web add /absolute/path/dsh-refractrouter-validation-0.10.0.tgz
refractagent dsh-config --output ./refractagent-demo.json \
  --runs-dir ./.refractagent/runs --mode demo --strategy balanced
dsh --profile web --patch ./refractagent-demo.json
```

在模型选择器中选择三个 RefractAgent 模型之一。默认是带 `[SIMULATED]` 标记的零调用演示。
真实执行需生成 `--mode live` 配置，设置生产与评审预算，显式开启 `allowPaidRuns`，
并由宿主解析 `CODEX_ARK_API_KEY`；密钥不写入配置。Ark 固定使用 Agent Plan `/api/plan/v3`。
安装环境要求 Python 3.11+、Node 22.19+（22.x）、DSH `0.1.1-rc.2`。

核心安装包自带运行所需的清单、profile 和计划，新模型入口可脱离源码目录运行。
答案与模型、状态、费用记录分开返回，`refractagent show RUN_DIRECTORY` 可查看保存的结果。
完整构建、headless、真实执行和故障处理见
[本机安装说明](../../../docs/refractagent-local-quickstart.md)。

## 0.9.0：复用 K3 基线继续 DAG

`stage: "resume"` 接收成功的 `baseline-ready` 输入目录，默认只执行零调用预检。
获批后只运行 Pro 参考路线与三模型节点探针，最多 28 次，完成后等待节点评审。
Python 验证原始索引、配置和代码兼容记录，并分别保存基线历史费用与本阶段新增费用。
不重新生成 K3，不自动进入组合阶段。具体交接见
[恢复准备记录](../../../reports/v0.5-k3-resume-readiness/README.md)。

## 0.8.0：仅执行 K3 基线

`{"phase":"k3-baseline","stage":"baseline"}` 默认生成单次零调用预检。
获批真实执行时，只生成 K3 整任务报告，等待上限 300 秒；成功后返回 `baseline-ready`，
失败则返回 `blocked`，两者均不运行参考路线或探针。仍需冻结输入、已通过的校准、
生产额度和显式付费开关。其他阶段的等待上限仍为 120 秒。

## 0.7.0：K3 整任务主对照

新增 `phase: "k3-baseline"`，支持 `stage: "prepare" | "compose"`、`inputDir` 和
`reviewsPath`；路径相对工作区解析。默认零调用预检，单轮、零重试，付费开关保持关闭。
本阶段采用 Python 冻结的质量达标后最低费用策略，不接收旧 `selectionPolicy`。
真实执行必须先通过独立评审校准，阶段间校验冻结材料和同一评审身份。
`prepare` 返回等待节点评审，`compose` 返回等待最终评审；工具 `pass` 仅表示该阶段
交接完整，不代表实验完成或收益成立。最终汇总由 Python 纯读取入口完成。

```json
{"phase":"k3-baseline","stage":"prepare","executePaidRun":false}
```

配置 Agent Plan 清单、`billingUnit: "AFP"`、`credentialEnv: "CODEX_ARK_API_KEY"` 和
`maxRetries: 0`。初始阶段计划 29 次生产调用，组合阶段最多 7 次；外部评审费用单列未知。
新阶段无内部评审调用，获批付费请求的 `maxEvaluationCost` 可为零；其他阶段规则不变。
完整说明见 [实验设计与交接方法](../../../docs/k3-baseline-comparison.md)。

本包是 RefractRouter 的 DSH 宿主适配层，与核心保留在同一仓库，通过
`validation/dsh/plugin/` 明确区分。Router 是项目核心；插件用于验证核心能力，
“DSH + 插件连接核心 Router”也是未来产品化的实现形态之一。

插件注册 `refractrouter_validate` 和 `refractrouter_task`，分别提供冻结基准验证和
文本任务入口。任务规划、DAG 校验、节点选模、执行与评估由 Python 核心及运行时负责。
上述两个历史工具通过本地 Python runner 执行，仍依赖匹配的 RefractRouter 源码环境；
0.10.0 的 RefractAgent 模型入口另由已安装核心提供。当前没有独立 Router 服务。详见
[项目架构](../../../docs/architecture.md) 和 [集成边界](../README.md)。

Version 0.4.0 adds `phase: "contract-replay"` for the seven archived issue #25 writer failures.
It defaults to preflight, permits at most three repeats, requires configured `maxRetries: 0`,
and stops on the first failed output contract. Paid calls retain the same deployment enablement,
credential resolution, exact Agent Plan endpoint, and two budget ceilings. No judge is invoked;
the tool still requires a positive evaluation ceiling for a paid request, but replay evaluation
spend is zero. A replay pass establishes contract validity only, not semantic quality or Go.

## 文本任务工具（0.7.0）

`refractrouter_task` 通过 Python 核心规划和执行文本任务。模型规划使用
`text-task-plan-v2`，节点须声明输入字段、依赖理由、输出契约、能力需求与验收覆盖。
支持单节点和独立分支，并保存结构诊断；默认串行，可用 `maxConcurrency` 配置
有界并发，并传递 `providerConcurrency`、`providerMinIntervalMs`。核心负责实际调度与
预算原子预留；DSH stdio LLM 桥仍限串行。
`acceptanceCriteria` 可传入 1 至 10 项不可由规划器改写的验收条件。

`preflight` 使用单节点保守预览，`demo` 使用模拟产物；`plan` 调用真实规划器并返回
路由，`run` 继续执行与独立评审。A 使用约束，B 还需显式三项权重。
详细格式、例子和限制见 [DAG 拆分机制](../../../docs/dag-decomposition.md) 与
[文本任务指南](../../../docs/text-task-routing.md)。

`taskProfilePath` 默认为 `data/routing/demo-usd-v1.json`，仅用于预检和模拟。
Agent Plan 可使用与 AFP 清单匹配的 `data/routing/report-transfer-v1.json`，但这仍是
单一报告任务的迁移预测。付费模式保留部署开关、双预算、原生凭证和进程控制及零重试。

## 基准候选选模策略

0.5.0 加入的 `selectionPolicy` 参数继续保留，仅由 `refractrouter_validate` 传给
Python 基准 runner 的 `--selection-policy`；默认 `all-candidates-required-v1`。
显式 `exclude-known-contract-rejections-v2` 保留完整矩阵中的已知契约拒绝证据，
但从候选选择中排除这些模型。执行或评分缺失、参考上下文无效、重复单元格和节点无可用
候选仍会停止组合。Python 负责全部业务规则，契约回放只接受默认策略。

```json
{"phase":"dry-run","repeats":1,"selectionPolicy":"exclude-known-contract-rejections-v2","executePaidRun":false}
```

策略记录在预检、矩阵、总结和 DSH 证据中；新真实运行必须使用新目录。已知拒绝保留在
`failure_taxonomy`，阻断实验的问题另列 `blocking_failures`；最终质量及 Go 阈值不变。
文本任务工具使用自己的 A/B 路由参数，不向文本 runner 传递基准专用策略。

## Supported versions

Version 0.6.0 adds `phase: "execution-modes"`, the explicit v0.4 evidence-state experiment.
It defaults to v2 selection, accepts one to three repeats and requires configured `maxRetries: 0`.
Configure the Agent Plan manifest, `billingUnit: "AFP"` and
`credentialEnv: "CODEX_ARK_API_KEY"`, then invoke:

```json
{"phase":"execution-modes","repeats":1,"executePaidRun":false}
```

The zero-call preflight reports 80 planned requests for one task/repeat: three one-shot reports,
three seven-node single-model reports, 21 node probes, one seven-node composed report, and 28 judges.
Python owns the versioned evidence state, comparison cohorts and call ledger. The plugin only
forwards this bounded phase. A paid execution needs fresh output, explicit scoped authorization,
enabled deployment configuration, resolved Agent Plan credentials and both budget ceilings.
See [the experiment design](../../../docs/evidence-state-execution-modes.md).

The v0.1 compatibility contract is intentionally narrow:

| Component | Supported | CI coverage |
|---|---|---|
| DSH CLI | `0.1.1-rc.2` exactly | `0.1.1-rc.2` |
| Node.js | `>=22.19.0 <23` | `22.19.0` and latest Node 22 |
| pnpm | `10.15.0` | `10.15.0` |
| Python | `>=3.11` | `3.12` |

DSH is still a release candidate, so a different DSH version requires a compatibility review and a
passing clean-profile lifecycle run before use. `dsh.compatibility` in `package.json` records the DSH
and Node contract for automation and review; current DSH does not enforce that metadata itself.

The package follows SemVer while it remains on `0.x`: compatible fixes increment the patch version;
changes to tool arguments, output, bundle configuration, or the Python runner contract increment the
minor version. The repository pins the tested DSH and pnpm versions in CI.

## Distribution decision for v0.1

v0.1 is a private, repository-owned package installed from a checkout path. It will not be published
to a registry while the DSH contract is pre-release and the benchmark is still experimental. This
keeps the plugin and its Python runner on the same reviewed commit.

For an immutable handoff, create a tarball from that commit and install the resulting file:

```bash
mkdir -p /tmp/refractrouter-plugin
npm pack ./validation/dsh/plugin --pack-destination /tmp/refractrouter-plugin
dsh plugin --profile headless add /tmp/refractrouter-plugin/dsh-refractrouter-validation-0.9.0.tgz
```

The package contains only generated `dist/` JavaScript and declarations, `cordis.patch.yml`,
`README.md`, `CHANGELOG.md`, and `package.json`. It has no runtime npm dependencies or install
scripts. `prepack` compiles the source before packing; first install the locked build dependencies
with `npm ci --prefix validation/dsh/plugin` (all examples run from the repository root).

## TypeScript source and build

Version 0.4.1 migrates the plugin and its contracts to strict TypeScript. `src/index.ts` is the source
entry; `src/contracts.ts` defines configuration, arguments, results and the consumed DSH host ports;
`src/evidence.ts` decodes fields projected from the Python runner's JSON. Routing, scoring, cost
accounting and Go / No-go remain in Python. Malformed evidence fields now fail as structured
`invalid-evidence` diagnostics instead of being forwarded with incorrect types.

```bash
npm ci --prefix validation/dsh/plugin
npm run --prefix validation/dsh/plugin typecheck
npm test --prefix validation/dsh/plugin
uv run pytest
```

`npm test` builds `src/` to `dist/`, compiles `tests/*.test.ts` to `.test-dist/`, and runs the compiled
contracts against the generated plugin. Both compiler configurations enable `strict` and
`noEmitOnError`. `main` and `exports` resolve to `dist/index.js`; `types` resolves to
`dist/index.d.ts`. The generated directories are ignored by Git. Never edit them manually.
A checkout must be built before installation; a packed tarball is ready to load without TypeScript.
The package-content contract installs a tarball in isolation and imports its declared entry.

The dependency-free structural host ports target DSH 0.1.1-rc.2. They are checked with typed fixtures
and real profile loading; they do not vendor DSH implementations. New languages or duplicated
cross-layer business logic require a documented architecture review and maintainer approval before
merge. The repository's `docs/architecture.md` records the review requirements.

## 职责边界

- DSH 提供组合、生命周期、工具调度、模型 provider、凭证解析、进程隔离与会话证据。
  DSH 外层助手的模型配置与 Router 对 DAG 节点的选模分别管理。
- 插件负责参数类型、部署级付费开关与预算上限、受限诊断输出，以及 Python 证据到
  结构化工具结果的转换。
- `real_runner.py` 组织基准验证，`task_runner.py` 组织文本任务调用与证据落盘；
  路由、评分和调用预算记账复用 Python 实现，不在插件中复制。
- 插件通过 `ctx.subprocess` 启动固定参数列表，不让模型拼装 Shell 命令。
- 直接 HTTP 清单在获准付费操作时解析凭证，仅传给经过筛选的子进程环境，并对诊断
  脱敏。AFP 清单还要求 `ark-plan` 和精确的 Agent Plan `/api/plan/v3` 端点。
  通用 `dsh-llm` 清单将凭证保留在 DSH 内，由受限 stdio 桥传递请求、结果和遥测；
  桥接层执行核心已确定的模型调用，不作路由决策。

## Install, inspect, remove, and restore

Install the pinned CLI tools first. `dsh plugin` invokes `pnpm` from `PATH`.

```bash
npm install --global pnpm@10.15.0 @deepseek-ai/dsh@0.1.1-rc.2
npm ci --prefix validation/dsh/plugin
npm run --prefix validation/dsh/plugin build
dsh plugin --profile headless add ./validation/dsh/plugin
dsh --profile headless --dump-config | rg -A6 refractrouter-validation
dsh --profile headless --help
```

The config dump must show `allowPaidRuns: false`. The help command boots the composed profile and
validates plugin loading without starting a model turn.

Remove and reinstall the bundle with:

```bash
dsh plugin --profile headless remove dsh-refractrouter-validation
dsh plugin --profile headless add ./validation/dsh/plugin
```

Restart any running profile after installation, removal, or configuration changes. The automated
equivalent uses a disposable `DSH_HOME`:

```bash
python3 scripts/validate_dsh_plugin_lifecycle.py
python3 scripts/validate_dsh_plugin_lifecycle.py --packed
```

## Configuration

Bundle defaults live in `cordis.patch.yml`. Override them in the profile's higher-precedence
`$DSH_HOME/profiles/<profile>/cordis.patch.yml`:

```yaml
- id: refractrouter-validation
  config:
    allowPaidRuns: true
    billingUnit: USD
    maxProductionCost: 8
    maxEvaluationCost: 2
    maxRetries: 0
```

The main deployment fields are:

| Field | Default | Purpose |
|---|---:|---|
| `allowPaidRuns` | `false` | Deployment switch required for any model call |
| `billingUnit` | `USD` | Unit required to match the selected manifest (`USD` or `AFP`) |
| `maxProductionCost` | `2` | Maximum production budget in `billingUnit` |
| `maxEvaluationCost` | `1` | Maximum judge budget in `billingUnit` |
| `maxRetries` | `0` | Retry count passed to the runner; zero bounds Agent Plan attempts |
| `timeoutMs` | `7200000` | Whole runner deadline |
| `processGraceMs` | `5000` | Managed subprocess termination grace |
| `outputCaptureBytes` | `262144` | Tail retained for each standard stream |
| `maxEvidenceBytes` | `2097152` | Largest accepted evidence JSON |
| `credentialEnv` | `OPENAI_API_KEY` | Credential reference; direct HTTP also uses it as the scrubbed child variable |

Paths for the runner, dataset, manifest, `uv` executable, and `uv` cache are also configurable for
deployment. Unknown fields fail configuration validation.

Paid execution requires all three independent gates: `allowPaidRuns: true` in deployment config,
positive production and evaluation limits in the individual tool call, and a configured credential.
Either requested limit above its deployment ceiling is rejected before credential resolution or
subprocess launch. The runner also rejects a limit below its conservative preflight estimate before
the first model call and reserves one estimated call against the remaining ledger before each call.

For the Agent Plan dry run, configure a DSH provider route named `ark-plan` for the short outer agent
turn through ArkCLI Helper, the official `ark-plan-api` plugin, or the DSH Models UI. Use the Agent
Plan endpoint and the same credential reference as the manifest. The outer route needs only the
low-coefficient `deepseek-v4-flash` model and zero provider retries:

```yaml
llm-pi-ai:
  providers:
    ark-plan:
      displayName: Ark Agent Plan
      apiKeyEnv: CODEX_ARK_API_KEY
      api: openai-responses
      baseURL: https://ark.cn-beijing.volces.com/api/plan/v3
      retryPolicy:
        mode: normal
        maxRetries: 0
      models:
        - id: deepseek-v4-flash
          name: deepseek-v4-flash
```

Then apply this profile override:

```yaml
- id: refractrouter-validation
  config:
    allowPaidRuns: false
    billingUnit: AFP
    maxProductionCost: 400
    maxEvaluationCost: 90
    maxRetries: 0
    manifestPath: data/model-manifests/volcengine-agent-plan.json
    credentialEnv: CODEX_ARK_API_KEY
```

The zero-cost preflight verifies AFP billing, provider `ark-plan`, and the exact base URL
`https://ark.cn-beijing.volces.com/api/plan/v3`. It rejects the ordinary Ark `/api/v3` endpoint before
credential resolution or process launch. During a paid operation, DSH resolves the Agent Plan key and
injects it only into the scrubbed Python child, which calls `/api/plan/v3/chat/completions` directly.
The runner uses a 120-second per-request timeout and zero retries. The manifest caps every response at
8,192 tokens; the preflight output estimate defaults to the manifest cap and rejects a lower explicit
estimate even in zero-cost mode. Because this cap includes reasoning tokens, the manifest sends
`thinking: {"type": "disabled"}` to reserve the output allowance for the required structured result.

Paid direct runs create `model-progress.ndjson` beside `preflight.json`. Each request writes a
prompt-free start record before dispatch and a finish record with status, latency, request ID, and
token usage and finish reason. `finish_reason=length` is classified as `output-truncated` by the
node adapter while preserving the partial output and billed usage. This file identifies the current model during a long run without storing prompts,
generated content, or credentials, and its hash is included in the final evidence. Generic
`dsh-llm` manifests retain the equivalent `bridge-progress.ndjson` evidence.

When the DSH orchestration turn also uses Agent Plan, pin it to the lowest-coefficient candidate:

```yaml
- id: agent-default-model
  config:
    provider: ark-plan
    model: deepseek-v4-flash
```

The outer agent calls occur outside the plugin's production/evaluation ledgers. Issue #19 proposes
400 AFP production, 90 AFP evaluation, and a separate 5 AFP outer allowance (495 AFP total). This
is a new budget request, not covered by issue #4's prior 265 AFP authorization. Keep paid execution
disabled until the new budget is approved.

## Invoke each phase

Zero-cost preflight examples:

```text
Call refractrouter_validate exactly once with
{"phase":"dry-run","executePaidRun":false} and return the tool result unchanged.

Call refractrouter_validate exactly once with
{"phase":"pilot","repeats":1,"executePaidRun":false} and return the tool result unchanged.

Call refractrouter_validate exactly once with
{"phase":"final","repeats":1,"executePaidRun":false} and return the tool result unchanged.
```

Pass one of those tasks to `dsh --profile headless '<task>'`. The DSH orchestration provider still
handles the short agent turn; `executePaidRun:false` guarantees the RefractRouter candidate and judge
models are not called.

After configuring the credential and deployment switch, a paid dry run call is:

```text
Call refractrouter_validate exactly once with
{"phase":"dry-run","executePaidRun":true,"maxProductionCost":8,"maxEvaluationCost":2}
and return the tool result unchanged.
```

With the Agent Plan override above, the corresponding call uses AFP ceilings:

```text
Call refractrouter_validate exactly once with
{"phase":"dry-run","executePaidRun":true,"maxProductionCost":400,"maxEvaluationCost":90}
and return the tool result unchanged.
```

Do not move to `pilot` or `final` until the preceding issue's evidence and budget checks pass.

## Failure diagnosis

| Symptom | Meaning and action |
|---|---|
| `pnpm not found on PATH` | Install pinned pnpm and repeat `dsh plugin add`. |
| Plugin missing from `--dump-config` | Remove and reinstall it; inspect the profile `package.json` dependency and `dsh.profile.bundles`. |
| Profile boot rejects configuration | Remove unknown fields and verify value types in the higher-precedence patch. |
| `paid validation is disabled` | Keep the safe default, or explicitly enable paid runs for an approved execution. |
| `requires configured credential` | Configure the manifest's credential reference in DSH; never put the value in a patch or tool call. |
| `missing-llm-provider:*` | A generic `dsh-llm` manifest references an unavailable DSH provider. |
| `unresolved-llm-model:*` | A generic `dsh-llm` manifest references an unavailable provider/model route. |
| `llm-provider-retry-policy-not-zero:*` | Set a generic bridge provider's nested `retryPolicy` to `mode: normal` and `maxRetries: 0`. |
| `plugin-runner-timeout` / `plugin-runner-aborted` | Inspect the evidence and bounded stream tails, then adjust the deployment timeout only if the run plan justifies it. |
| `plugin-runner-stdout-truncated` / `plugin-runner-stderr-truncated` | Increase the capture limit for diagnosis; truncation fails closed. |
| `invalid-evidence` / `missing-evidence` | Verify runner paths, write access, evidence size, Python dependencies, and the child exit code. |
| Sandbox provider refuses confinement | Use a supported DSH sandbox backend and a `workspace-write` profile. The runner needs temporary output writes. |

Captured stdout and stderr are diagnostic tails, not complete logs. DSH bounds each stream, and the
plugin rejects oversized evidence instead of parsing an unbounded file. Caller cancellation before
spawn prevents process creation; cancellation or timeout during execution terminates the managed
process tree through `ctx.subprocess`.

## Upgrade and rollback

Before upgrading, record the current repository commit, plugin version, DSH version, profile patch,
and evidence hashes. Update the checkout, run the complete test and lifecycle commands, then restart
the profile. A DSH version change also requires updating the compatibility metadata and CI matrix.

To roll back, switch to the recorded clean commit or install its saved tarball, restore the previous
profile patch, remove and reinstall the plugin, and run a zero-cost preflight before any paid run.
