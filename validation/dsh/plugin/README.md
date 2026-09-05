# RefractRouter DSH validation bundle

This package is an installable DeepSeek Harness bundle. It contributes one normal Cordis tool,
`refractrouter_validate`, to any base-backed DSH profile.

## Design boundary

- DSH owns composition, lifecycle, tool dispatch, credential resolution, process confinement, and
  session evidence.
- The plugin owns typed arguments, paid-run policy, budget ceilings, and projection of the Python
  evidence into a structured tool result.
- `validation/dsh/real_runner.py` remains the only owner of benchmark execution, hashing, scoring,
  and artifact validation.
- The plugin launches a fixed argv through `ctx.subprocess`; it never asks the model to construct a
  shell command and never returns credential values.
- The checkout bundle has no runtime package imports, so `dsh plugin add ./path` can link it without
  a package-local install or an install-time build script.
- A single package is intentional: the provider and consumer do not yet need independent evolution.

## Install

From the RefractRouter checkout:

```bash
dsh plugin --profile headless add ./validation/dsh/plugin
```

`dsh plugin` links the checkout into the profile and appends the declared bundle layer. Restart a
running profile after installing or removing the bundle.

Inspect the composed tree without starting an agent:

```bash
dsh --profile headless --dump-config | rg refractrouter-validation
```

## Run zero-cost preflight

```bash
dsh --profile headless \
  'Call refractrouter_validate exactly once with {"phase":"final","executePaidRun":false}. Return the tool result unchanged.'
```

The DSH provider still handles the short orchestration turn. The RefractRouter validation itself
does not call candidate or judge models in preflight mode.

## Enable a paid dry run

Paid execution is disabled in `cordis.patch.yml`. Enable it only in the profile's own
`cordis.patch.yml`, which has higher precedence than this bundle:

```yaml
- id: refractrouter-validation
  config:
    allowPaidRuns: true
    maxProductionCostUsd: 2
    maxEvaluationCostUsd: 1
```

Then configure `OPENAI_API_KEY` through DSH credentials or an approved environment source and ask
the tool to run with both limits:

```text
Call refractrouter_validate with phase dry-run, executePaidRun true,
maxProductionCostUsd 2, and maxEvaluationCostUsd 1.
```

The plugin resolves the credential for that operation and explicitly forwards it to the scrubbed
child environment. Evidence records presence only, never the value.
