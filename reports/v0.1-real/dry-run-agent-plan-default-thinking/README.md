# Agent Plan paid dry run: default thinking

Executed on 2026-09-06 through DSH plugin 0.3.0 from commit `926146e`. The run used only
`https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions`, with Agent Plan overage disabled,
zero retries, and invocation ceilings of 160.16 production AFP and 46 evaluation AFP.

## Outcome

The DSH tool returned `status=fail`, `mode=paid`, with `benchmark-incomplete` and
`plugin-runner-exit:1`. This is the expected outer failure projection of an experiment summary whose
status is `incomplete`; it is an experiment No-go, not a provider or process failure.

All 28 HTTP requests that were actually dispatched succeeded in one attempt and returned a provider
request ID. They used 13,707 input, 30,455 output, 1,059 cached-input, and 22,920 reasoning tokens.
Production cost was 12.1471 AFP; no judge request was sent because none of the five strategies
produced a final report.

The 1,200-token response cap included reasoning tokens. Selected run records show five initial-node
failures with `finish_reason=length`: two empty outputs and three invalid JSON outputs. Those failures
caused 29 downstream nodes to be skipped and five judge evaluations to report `missing-final-output`.
The resulting gate was `No-go`, with `judge_complete=false`.

## Evidence

- DSH evidence SHA-256: `8b88b7226c48da73d180fefd3d3e4f754e9366e039faff25af60ae8a60294d65`
- Benchmark summary SHA-256: `c373093559497dfc8c68a4407c0460e30a97de03450431691929b6d94953537e`
- Model progress SHA-256: `a66935363aea937c25c6e61a06562fdee234a0b2bcdaa6a8c6fc9f013fa7afc5`
- Evidence index SHA-256: `2dae0802d7164313b110c7315b734d3071a877d577a999ad5489532720023608`
- Secret scan: 14 files scanned, zero matches for the configured Agent Plan credential.

The immediate corrective action is to send the supported
`thinking: {"type": "disabled"}` request option while retaining the same 1,200-token response cap.
One low-output live probe for each of the three candidates and the independent judge returned
`reasoning_tokens=0` with one attempt.
