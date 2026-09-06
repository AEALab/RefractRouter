# Issue #19 output truncation correction

## Observed failure

The original evidence remains unchanged in `../v0.1-real/dry-run-agent-plan-final-no-go/`.
All five selected strategy failures ended at exactly 1,200 output tokens with
`finish_reason=length`: one outline, three report JSON results (including the reused single-model
result), and one HTML result. HTTP success did not imply a complete artifact. This dry run exposes
an output-budget configuration failure; it cannot establish a routing-effectiveness conclusion.

## Implemented correction

- The Agent Plan manifest now permits 8,192 output tokens for candidates and the judge, retaining
  disabled thinking and the dedicated `/api/plan/v3` endpoint.
- Planning returns flat section titles and short constraints; synthesis and report prose have length
  guidance. Rendering preserves the report and source trace without expanding prose or decorative CSS.
- The node adapter reports `output-truncated` for length termination, even when the partial response
  happens to parse. Partial content, usage, cost, and request ID remain available without retries.
- Direct request progress now includes finish reason.
- Preflight derives its default output estimate from the maximum manifest cap. Explicit
  underestimates are rejected before any preflight success or paid dispatch. This also corrects the
  existing USD manifest's old 1,200-token estimate for an 8,192-token request cap.

The larger cap and prompt changes address the observed causes. Offline checks cannot prove that
live models will now complete every contract, citation and judge response.

## Validation and live budget

Offline replay of all five saved truncations verifies failure classification, preservation of billed
usage/partial output, one attempt, and an 8,192-token request. A separate case verifies that syntactically
valid JSON terminated by length still fails. Preflight rejects an output underestimate in both paid
and zero-cost paths.

Validation: 61 Python tests (including five saved-response subtests), 12 Node contract tests, and
local execution of the DSH Python wrapper in zero-cost mode passed. No live models were called for
this correction. The local wrapper check is not a new native DSH headless model turn.

The corrected dry run plans 56 production calls and 5 judge calls. Using the existing input
assumptions (4,000 production / 8,000 judge tokens), 8,192 output tokens and no cache discount:

| Ledger | Estimate (AFP) | Proposed new limit (AFP) |
|---|---:|---:|
| Production | 375.51 | 400 |
| Evaluation | 80.96 | 90 |
| Outer DSH agent | separate allowance | 5 |
| Total | 456.47 plus outer usage | 495 |

Input token counts are estimates, not hard bounds. The existing per-call reservation and Plan overage
settings remain relevant to spend control. The 495 AFP proposal is for one new run, in addition to
previous usage. It exceeds the original 265 AFP authorization and needs a new approval before paid
execution. The old dry-run evidence and its budget remain historical facts.

Issue #19 remains open until live validation is recorded. Issue #5 stays blocked pending a successful
admission run; passing offline tests does not unblock it.
