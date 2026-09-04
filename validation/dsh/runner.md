# DSH Runner Notes

The DSH integration should wrap the RefractRouter CLI, not replace it.

1. Resolve the task and source-pack paths.
2. Record environment and dependency versions.
3. Invoke `refractrouter run`.
4. Validate the generated HTML.
5. Persist the run record and scoring evidence.

The v0.1 integration does not require DSH plugins. A thin wrapper is sufficient.
