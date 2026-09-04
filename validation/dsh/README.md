# DSH Validation Boundary

DeepSeek Harness is used only as the outer validation environment for RefractRouter v0.1.

## Responsibilities

- Start a reproducible experiment run.
- Verify task package, model configuration, and source-pack hashes.
- Capture execution evidence.
- Run deterministic HTML and scoring checks.

## Non-responsibilities

- DSH does not select models.
- DSH does not replace the DeepAgents/LangGraph execution loop.
- DSH does not own task decomposition.

## Runner contract

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
generated HTML hash, and final-output source-trace issues. See `runner.md` for local and DSH
headless invocation examples.

`canonical_runner.py` is the experiment-level validator. It runs all five canonical strategies
in an isolated output directory, requires every report artifact, cross-checks the node-oracle
run record, and independently derives the oracle Go / No-Go result from the experiment summary.

The complete flow has been exercised through DSH `0.1.1-rc.2` in a disposable workspace. The
runner reported no validation or source-trace issues, and its code and artifact hashes matched an
independent local run. The durable next step is to retain a stable session-evidence index in CI;
temporary workspace paths are not treated as permanent evidence locations.
