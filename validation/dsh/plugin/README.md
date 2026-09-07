# RefractRouter DSH validation bundle

This package contributes the structured `refractrouter_validate` tool to a base-backed DeepSeek
Harness profile. The tool runs the repository's fixed Python validation entry point and projects its
evidence into a bounded result.

Version 0.4.0 adds `phase: "contract-replay"` for the seven archived issue #25 writer failures.
It defaults to preflight, permits at most three repeats, requires configured `maxRetries: 0`,
and stops on the first failed output contract. Paid calls retain the same deployment enablement,
credential resolution, exact Agent Plan endpoint, and two budget ceilings. No judge is invoked;
the tool still requires a positive evaluation ceiling for a paid request, but replay evaluation
spend is zero. A replay pass establishes contract validity only, not semantic quality or Go.

## Supported versions

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
dsh plugin --profile headless add /tmp/refractrouter-plugin/dsh-refractrouter-validation-0.4.1.tgz
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

## Design boundary

- DSH owns composition, lifecycle, tool dispatch, model providers, credential resolution, process
  confinement, and session evidence.
- The plugin owns typed arguments, paid-run policy, budget ceilings, bounded diagnostics, and the
  projection of Python evidence into a structured tool result.
- `validation/dsh/real_runner.py` remains the only owner of benchmark execution, hashing, scoring,
  and artifact validation.
- The plugin launches a fixed argv through `ctx.subprocess`; it never asks a model to construct a
  shell command.
- Direct HTTP manifests resolve their credential once per paid operation, forward it only in the
  scrubbed child environment, and redact it from diagnostics. AFP manifests additionally require
  provider `ark-plan` and the exact Agent Plan `/api/plan/v3` base URL. Generic `dsh-llm` manifests
  keep provider credentials inside DSH; a bounded stdio bridge carries prompts, results, and telemetry.

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
