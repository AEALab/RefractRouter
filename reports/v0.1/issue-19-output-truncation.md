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

## Pre-run validation and budget proposal

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
previous usage. At preparation time it exceeded the original 265 AFP authorization and required new approval before
execution (the subsequent approval and result are recorded below). The old dry-run evidence and its budget remain historical facts.

## Live validation completed

The user subsequently approved the additional 495 AFP allowance. A single live run from clean
merged commit `f69e0d2` completed with DSH `status=pass`, `issues=[]`, 61/61 calls, zero truncations,
zero failures, and 100% strategy success and judge coverage. All five final source traces and all
20 indexed hash checks passed. Production cost was 30.44395 AFP and evaluation cost 17.153 AFP;
the two outer DSH turns add an estimated 1.1972 AFP. No ordinary Ark endpoint was used.

The largest response used 2,430 output tokens, confirming that the previous 1,200-token cap was
too small for this workload. Evidence is in
[`../v0.1-real/dry-run-agent-plan-8192/`](../v0.1-real/dry-run-agent-plan-8192/README.md).

Issue #19 is verified and can close. Issue #5's output-completeness blocker is removed, while its
pilot budget and execution remain pending. The one-task routing-benefit result is still No-go:
node-oracle scored 84 versus task-oracle 100 at nearly equal cost. Both chose Flash for every node,
so the score gap comes from separately generated/judged reports and cannot demonstrate a benefit
or loss caused by different routing assignments. Multi-task/repeat assessment belongs to the pilot.
