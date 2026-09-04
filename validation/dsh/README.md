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

The runner should accept:

```text
--task data/tasks/report_001.json
--strategy strong-all
--output reports/v0.1/report_001.html
```

and emit a run record compatible with `data/schema/run-record.schema.json`.
