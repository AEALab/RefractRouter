# Intermediate node contract recovery

Follow-up to [issue #25](https://github.com/AEALab/RefractRouter/issues/25), 2026-09-06.
The original three-repeat archive remains unchanged.

## Implemented changes

- Prompt protocol v0.3 scopes standalone HTML to the final rendering artifact and gives every
  intermediate node an explicit JSON schema description. Synthesis and writing must preserve
  complete evidence objects with source ID, exact title/hash and nonempty claim text.
- The execution adapter and node scorer now share hard contract checks, preventing malformed
  evidence from reaching the next node. Missing-section coverage remains a graded cap.
- M3 uses a manifest-controlled prompt-only JSON strategy. MiniMax's own
  [format verifier](https://github.com/MiniMax-AI/MiniMax-Provider-Verifier/blob/main/m3_format_check/docs/m3_text_cases.md)
  marks its JSON-object response-format tests unsupported (accessed 2026-09-06). This is evidence
  against assuming portable parameter enforcement, not proof of Ark's hosted implementation.
- The matrix distinguishes known contract rejection (zero eligibility) from unavailable execution
  or judging (null score and explicit error). The existing fail-closed selection rule remains:
  failed execution or unavailable evaluation prevents selection. No original gate is reinterpreted.
- DSH plugin 0.4.0 provides bounded `contract-replay`: three saved M3 probes, three M3 single-run
  writers, and one composed Flash writer. Verify original artifact hashes and exact upstreams,
  reserve each request before dispatch, persist output/usage/checks, and stop at the first failure.

## Verification

94 tests and 5 subtests pass locally, including all seven recorded failures, complete evidence
acceptance, missing-field rejection, M3 request-format selection, absent-score semantics,
zero-call preflight, seven-case simulated replay, early failure and budget rejection.
DSH tests verify the replay phase, bounded repeats, disabled retries and existing paid controls.

One replay pass allows at most seven production calls, no judge calls and no retries. The
byte-based input allowance plus 8192 output tokens estimates 27.24785 AFP. The planned production
ceiling is 32 AFP within the user's existing 2505-AFP total authorization; DSH's positive
evaluation ceiling is set to 1 AFP with zero evaluation calls. A passing replay does not validate
final report quality or the full oracle comparison.

## Live replay result

All seven cases passed on clean commit `2210b601b13c448b204d248bba6ffca39f6e1868`.
DSH reports `pass`: six M3 writers and the composed Flash writer now satisfy the complete
JSON/evidence contract on their original saved upstream inputs. Each request completed normally
in one attempt. Production cost was 5.81585 AFP; outer DSH cost was 1.20045 AFP from usage.
The temporary paid profile was disabled afterward. This validates the scoped contract recovery,
not the semantic quality or end-to-end reliability of a newly generated DAG.

Original results, parent hashes, request telemetry, manifest/code provenance and billing estimates
are in [agent-plan-replay/](agent-plan-replay/). The five original indexed hashes were verified
and the saved output was scanned for the credential before publication.

## Full-repeat budget preparation

Preflight now prices the known candidate sweeps by their assigned models; it retains the most
expensive per-call price for unknown composed/learned assignments. At three repeats, 42 calls
per candidate are fixed (126 total), and the remaining 42 calls retain the most expensive bound.
The existing 4000 input / 8192 output token assumptions are unchanged. The estimate becomes
716.89 production + 1262.98 evaluation = 1979.87 AFP. Tests verify the bound and use actual
input/output token weights when choosing the most expensive request.

Known cost across the initial interrupted run, repeated run and seven-case replay, including
DSH outer calls, is 393.287 AFP; add the retained 16.192 AFP unsettled request estimate to get
409.479 AFP. A fresh 740-production / 1290-evaluation admission envelope plus the remaining
1.9742 AFP of the original outer allowance gives total admitted exposure 2441.4532 AFP,
within the existing 2505-AFP approval. Per-request reservations remain estimates, and the
existing budget checks stop new requests when the remaining allowance is insufficient.

## Completed three-repeat run, 2026-09-07

The prepared full run subsequently completed 237/237 requests on clean `3e9f99d`, without
changing approval settings or repeating the seven-case replay. All 63 matrix cells are saved;
62 are eligible, and the second/third repeats execute different mixed node-oracle routes.
One first-repeat Flash synthesis probe omitted evidence, so the frozen all-candidates-required
policy skipped that composed route. All nine single-model reports were independently judged.

The two valid paired mixed routes score 7.5 points above all Pro and cost 3.734175 AFP less on
average, but score 4.5 points below the paired best single model and cost 2.598275 AFP more.
The complete three-repeat decision remains **Insufficient-evidence**. The selection policy
has not been changed; [issue #29](https://github.com/AEALab/RefractRouter/issues/29) tracks the
remaining rejection/availability distinction and aligned comparison cohorts.

This run used 412.84970 AFP in model calls plus 1.19945 AFP for two outer DSH calls, totaling
414.04915 AFP. Known cost across the original authorization is now 807.33615 AFP; including
the retained 16.192-AFP unsettled estimate leaves 1681.47185 AFP of the approved 2505 AFP.
The paid profile is disabled. See the [full report and audit](repeated-agent-plan/README.md).
