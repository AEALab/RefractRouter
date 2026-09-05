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

To capture the same validation in a DSH session, ask the headless profile to run exactly that
command and add `--invoked-by dsh`. Use an isolated workspace and `DSH_HOME`; DSH is responsible
for the outer session log, while `runner.py` remains responsible for deterministic checks.

```bash
dsh --profile headless \
  "Run uv run python validation/dsh/runner.py --task data/tasks/report_001.json \
  --strategy strong-all --output reports/v0.1/report_001-dsh.html \
  --evidence reports/v0.1/dsh-evidence.json --invoked-by dsh. \
  Do not edit source files. Return the validator status and evidence path."
```

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

For the final DSH session, run this command through the headless profile and add
`--invoked-by dsh`. The canonical validator requires all six report artifacts, checks the
node-oracle run record against the experiment summary, validates final-output source trace,
recomputes cost reduction and latency ratio, and applies the 120% latency gate independently.

The v0.1 integration does not require a custom DSH plugin. A thin deterministic wrapper is
sufficient; DSH must not select models or calculate the benchmark score.

For the real-model phase, invoke `validation/dsh/real_runner.py`. Default execution is preflight-only.
Paid execution is invalid unless the caller supplies `--execute-paid-run`, a positive production cost
limit, a positive evaluation cost limit, and the API-key environment variable named by the model
manifest. Evidence records only whether the variable exists; it never records the value.

Run the zero-cost final preflight through DSH with:

```bash
dsh --profile headless \
  "Run UV_CACHE_DIR=/tmp/refractrouter-uv-cache uv run --extra dev --extra deepagents \
  python validation/dsh/real_runner.py --dataset data/benchmarks/v0.1.json \
  --manifest data/model-manifests/openai-gpt-5.4.json --phase final \
  --output-dir /tmp/refractrouter-real-preflight \
  --evidence /tmp/refractrouter-real-preflight-evidence.json --invoked-by dsh. \
  Do not edit source files or execute paid model calls. Return the validator status, issues, \
  call plan, cost estimate, input hashes, and evidence path."
```

This is an actual DSH session but not an actual candidate-model benchmark. A paid benchmark must be
launched separately only after the API key, phase, disclosure scope, and both cost ceilings are
explicitly approved.
