# DSH Runner

The DSH integration wraps the RefractRouter CLI; it does not replace it.

Run the deterministic validator locally:

```bash
uv run python validation/dsh/runner.py \
  --task data/tasks/report_001.json \
  --strategy strong-all \
  --output reports/v0.1/report_001-dsh.html \
  --evidence reports/v0.1/dsh-evidence.json
```

DSH validation is delivered as the installable `dsh-refractrouter-validation` bundle. Install the
checkout into a base-backed profile:

```bash
npm install --global pnpm@10.15.0 @deepseek-ai/dsh@0.1.1-rc.2
dsh plugin --profile headless add ./validation/dsh/plugin
dsh --profile headless --dump-config | rg refractrouter-validation
```

The bundle is a normal Cordis patch layer. It registers `refractrouter_validate` beside the profile's
other tools and relies on DSH's injected subprocess, sandbox, policy, and credential services.

The evidence record contains:

1. Task, source-pack, lockfile, and generated HTML hashes.
2. Python, DSH, DeepAgents, LangGraph, RefractRouter, Git, and platform versions.
3. The exact CLI command, stdout, stderr, and exit code.
4. HTML envelope and final-output source-trace validation results.

Validate the complete five-strategy canonical experiment and independently recompute the oracle
gate with:

```bash
uv run python validation/dsh/canonical_runner.py \
  --task data/tasks/report_001.json \
  --output-dir /tmp/refractrouter-canonical-validation \
  --evidence /tmp/refractrouter-canonical-evidence.json
```

The canonical validator requires all six report artifacts, checks the node-oracle run record against
the experiment summary, validates final-output source trace, recomputes cost reduction and latency
ratio, and applies the 120% latency gate independently. It remains a Python domain runner; the DSH
plugin does not duplicate its score implementation.

For the real-model phase, invoke `validation/dsh/real_runner.py`. Default execution is preflight-only.
Paid execution is invalid unless the caller supplies `--execute-paid-run`, a positive production cost
limit, a positive evaluation cost limit, and the API-key environment variable named by the model
manifest. Evidence records only whether the variable exists; it never records the value.

Run the zero-cost final preflight through the installed DSH plugin with:

```bash
dsh --profile headless \
  'Call refractrouter_validate exactly once with {"phase":"final","executePaidRun":false}. Return the tool result unchanged.'
```

The plugin sends a fixed argv through `ctx.subprocess`, confines it with the active sandbox policy,
and projects the evidence JSON into a structured tool result. This is an actual DSH session but not
an actual candidate-model benchmark.

Paid calls are disabled by the bundle default. A higher-precedence profile patch must explicitly set
`allowPaidRuns: true` and define the maximum production/evaluation ceilings. The tool call must then
request `executePaidRun: true` and supply two positive limits no larger than those ceilings. The
plugin resolves the credential for that operation only and never returns its value.

The supported versions, all three phase examples, clean-profile lifecycle check, output limits,
failure diagnosis, upgrade procedure, and rollback procedure are maintained in
[`plugin/README.md`](plugin/README.md). Run `python3 scripts/validate_dsh_plugin_lifecycle.py` after a
DSH or Node upgrade and before any paid benchmark.
