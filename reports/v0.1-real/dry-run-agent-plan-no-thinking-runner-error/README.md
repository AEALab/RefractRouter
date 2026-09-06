# Agent Plan paid dry run: judge budget field error

Executed on 2026-09-06 through DSH plugin 0.3.0 from commit `633df01`. The run used only
`https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions`, with Agent Plan overage disabled,
zero retries, `thinking: {"type": "disabled"}`, and invocation ceilings of 160.16 production AFP
and 46 evaluation AFP.

## Outcome

The DSH tool returned `status=fail`, `mode=paid`, because the experiment process exited before it
could write summary artifacts. The captured traceback identifies a deterministic code error in the
evaluation budget reservation: `_evaluate_with_budget` referenced `judge.model`, while
`IndependentJudge` exposes the frozen model as `judge.judge_model`.

All 41 HTTP requests dispatched before that line succeeded in one attempt and returned a provider
request ID. They used 39,454 input, 33,312 output, 3,752 cached-input, and zero reasoning tokens.
Recorded production cost was 18.8087 AFP, with per-request latency from 2,745 to 29,953 ms. The
failure occurred at the first judge budget check, before any `kimi-k3` request was sent.

## Evidence

- DSH evidence SHA-256: `9094759a19ebdc3d81403512c1277b0ddee48f590e961b45755e5d27a8d99c69`
- Model progress SHA-256: `1b88a65de2fb7a786391a23057a3e4be8dd0993120c23fa77225ed84a153d13c`
- Preflight SHA-256: `b241d92693f166ad1180af5dff0fdd6c8958606245f3ffacd3bf5fe0c8f02b74`
- Secret scan: 3 captured files scanned, zero matches for the configured Agent Plan credential.

The correction changes the budget reservation to `judge.judge_model` and adds a regression test that
executes the successful evaluation-budget path.
