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

93 tests and 5 subtests pass locally, including all seven recorded failures, complete evidence
acceptance, missing-field rejection, M3 request-format selection, absent-score semantics,
zero-call preflight, seven-case simulated replay, early failure and budget rejection.
DSH tests verify the replay phase, bounded repeats, disabled retries and existing paid controls.

One replay pass allows at most seven production calls, no judge calls and no retries. The
byte-based input allowance plus 8192 output tokens estimates 27.24785 AFP. The planned production
ceiling is 32 AFP within the user's existing 2505-AFP total authorization; DSH's positive
evaluation ceiling is set to 1 AFP with zero evaluation calls. A passing replay does not validate
final report quality or the full oracle comparison.

The live replay evidence will be saved separately after execution on a clean committed version.
