# Changelog

## 0.2.2

- Enforce per-request timeouts locally while consuming DSH streams, including providers that ignore
  the supplied abort signal.
- Persist prompt-free request start and finish records so long paid runs expose their current model
  and completed-call progress.

## 0.2.1

- Reject DSH model routes whose provider-owned retry policy is not normal mode with zero retries.
- Carry the runner's per-model timeout across the stdio bridge and abort stalled DSH streams.

## 0.2.0

- Add an AFP-billed Volcengine Agent Plan manifest and generic billing-unit budgets.
- Route Agent Plan calls through the hosting DSH `llm` service over a bounded stdio bridge, so the
  provider credential remains owned by DSH and is never copied into the Python child.
- Validate the frozen provider/model routes before a paid run and expose the billing unit in
  structured preflight and evidence results.
- Reject paid ceilings below the conservative preflight estimate, reserve an estimated call before
  each invocation, and default DSH runner retries to zero.

## 0.1.1

- Bound evidence and standard-stream capture, fail on truncation, and redact resolved credentials
  from returned diagnostics.
- Declare and test the v0.1 DSH, Node, and pnpm compatibility contract.
- Add clean-profile installation lifecycle validation and release, troubleshooting, upgrade, and
  rollback documentation.

## 0.1.0

- Add the `refractrouter_validate` Cordis tool with preflight-safe defaults and two-level paid-run
  budget enforcement.
- Use DSH subprocess, sandbox, policy, and credential services while keeping benchmark logic in the
  Python runner.
