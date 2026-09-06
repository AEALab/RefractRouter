# DSH Validation Boundary

DeepSeek Harness is the outer validation environment for RefractRouter v0.1. The integration is an
installable DSH bundle, not a natural-language request to assemble and execute a shell command.

## Responsibilities

- Start a reproducible experiment run.
- Verify task package, model configuration, and source-pack hashes.
- Capture execution evidence.
- Run deterministic HTML and scoring checks.
- Apply the DSH profile's credential, sandbox, lifecycle, and tool-dispatch policies.

## Non-responsibilities

- DSH does not select models.
- DSH does not replace the DeepAgents/LangGraph execution loop.
- DSH does not own task decomposition.

## Plugin contract

`validation/dsh/plugin/` is the `dsh-refractrouter-validation` bundle. Its `dsh.bundle` manifest
contributes one Cordis plugin row, which registers the structured `refractrouter_validate` tool.
The plugin:

- uses `ctx.subprocess` for process ownership and bounded output;
- uses `ctx.sandbox` and `ctx.sandboxPolicy` for the profile's file boundary;
- uses `ctx.credentials` for credential readiness and direct-HTTP credential resolution;
- uses `ctx.llm` only for manifests that explicitly select the generic DSH LLM bridge;
- returns typed status, plan, cost, hashes, issues, and evidence paths;
- defaults `allowPaidRuns` to false and enforces deployment-level production/evaluation ceilings.

The v0.1 release contract supports DSH `0.1.1-rc.2`, Node `>=22.19.0 <23`, and pnpm `10.15.0`.
The package is private and installed from the same repository commit as the Python runner; no
registry publication is planned while DSH remains pre-release. Full installation, configuration,
phase examples, troubleshooting, and rollback guidance live in
[`plugin/README.md`](plugin/README.md).

Install it into a base-backed profile from this checkout:

```bash
npm install --global pnpm@10.15.0 @deepseek-ai/dsh@0.1.1-rc.2
dsh plugin --profile headless add ./validation/dsh/plugin
dsh --profile headless --dump-config | rg refractrouter-validation
```

Validate install, override, removal, reinstall, and boot in a disposable profile:

```bash
python3 scripts/validate_dsh_plugin_lifecycle.py
```

Run the real-model final preflight through the plugin:

```bash
dsh --profile headless \
  'Call refractrouter_validate exactly once with {"phase":"final","executePaidRun":false}. Return the tool result unchanged.'
```

The DSH provider handles the short orchestration turn. The plugin launches a fixed argv rather than
letting the model construct one. It never returns credential values.

## Python runner contract

The deterministic runner accepts:

```bash
uv run python validation/dsh/runner.py \
  --task data/tasks/report_001.json \
  --strategy strong-all \
  --output reports/v0.1/report_001-dsh.html \
  --evidence reports/v0.1/dsh-evidence.json
```

It invokes the fixed RefractRouter CLI and emits a validation evidence record containing the
exact command, exit code, standard streams, dependency versions, Git state, input hashes,
generated HTML hash, and final-output source-trace issues. See `runner.md` for local runner and DSH
plugin examples.

`canonical_runner.py` is the experiment-level validator. It runs all five canonical strategies
in an isolated output directory, requires every report artifact, cross-checks the node-oracle
run record, and independently derives the oracle Go / No-Go result from the experiment summary.

The bundle installation, composition and tool invocation have been exercised through DSH
`0.1.1-rc.2` in disposable profiles. CI tests the oldest supported Node release and latest Node 22,
including clean-profile lifecycle, package contents, service-seam behavior, output bounds,
credential redaction, timeout/abort behavior, and a real zero-cost Python preflight through the
registered tool. A read-only sandbox is insufficient because the runner must write temporary output;
use the default `workspace-write` profile or an explicitly approved wider policy.

## Real-model boundary

`real_runner.py` wraps the 20-task real-model benchmark. Its default mode is a zero-cost preflight:

```bash
uv run python validation/dsh/real_runner.py \
  --dataset data/benchmarks/v0.1.json \
  --manifest data/model-manifests/openai-gpt-5.4.json \
  --phase dry-run \
  --output-dir /tmp/refractrouter-real-preflight \
  --evidence /tmp/refractrouter-real-preflight-evidence.json
```

The preflight validates the dataset/model boundary, records corpus and code hashes, and calculates the
call plan without invoking a candidate or judge model. A paid run additionally requires
`--execute-paid-run`, both cost limits, and the manifest credential. A `dsh-llm` manifest also
requires every frozen provider/model route to resolve in DSH; its requests pass through a bounded
stdio bridge and its credential remains inside the DSH provider.

The issue #19 correction uses `data/model-manifests/volcengine-agent-plan.json`: three Agent Plan candidates,
`kimi-k3` as the independent judge, AFP billing, proposed 400/90 AFP deployment ceilings, and zero retries.
Its benchmark requests use the exact Agent Plan OpenAI-compatible base URL
`https://ark.cn-beijing.volces.com/api/plan/v3`; the plugin rejects the ordinary Ark `/api/v3`
endpoint for any AFP manifest. DSH resolves the plan credential and passes it only to the scrubbed
Python child. The corrected 8,192-token cap yields a 456.47 AFP estimate. Its new budget and validation status
are recorded in [`../../reports/v0.1/issue-19-output-truncation.md`](../../reports/v0.1/issue-19-output-truncation.md).

DSH is still only the outer validator. It must not choose candidate models, change the frozen manifest,
or replace the DeepAgents/LangGraph execution path. Before launching a DSH headless session, explicitly
approve sending the repository context to the configured external DSH model. Before a paid run, also
enable it in the higher-precedence profile patch and approve both cost ceilings.
