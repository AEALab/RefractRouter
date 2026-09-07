# Repository Guidelines

## Project Structure & Module Organization

Python implementation lives in `src/refractrouter/`, and benchmark entry points in `experiments/`.
DSH plugin TypeScript sources and contracts live in `validation/dsh/plugin/src/` and
`validation/dsh/plugin/tests/`.
Frozen tasks, sources, manifests and rubrics live in `data/`, Python tests in `tests/`, and DSH integration
in `validation/dsh/`. Historical evidence lives in `reports/`; preserve completed run artifacts.

## Implementation language boundary

- Python owns Router business logic: task DAGs, node execution and model assignment, strategies,
  scoring and evaluation, datasets, adapters, cost/latency metrics and experiment runners.
- TypeScript owns the DSH plugin entry, configuration/tool types, native host integration,
  subprocess/credential boundaries, structured results and plugin contract tests.
- Do not duplicate routing, scoring, budget accounting or Go/No-go logic in TypeScript. The plugin
  may enforce deployment limits before calling the authoritative Python runner.
- Markdown, JSON and YAML are documentation/data. JavaScript is allowed as TypeScript compiler
  output; do not add handwritten JavaScript implementation.
- A new implementation language or cross-layer business-logic duplication requires a documented
  architecture issue/ADR and maintainer approval before merge. Record ownership, alternatives,
  costs, drift prevention, verification and rollback. See `docs/architecture.md`.

## Build, Test, and Development Commands

Use `uv sync --frozen --extra dev --extra deepagents` to install dependencies and `uv run pytest`
to run the full suite, including TypeScript DSH contract tests. First install the plugin's locked
build tools with `npm ci --prefix validation/dsh/plugin`. Run
`npm run --prefix validation/dsh/plugin typecheck` and `npm run --prefix validation/dsh/plugin build`.
The plugin entry is generated `dist/index.js`; build before `dsh plugin add`. Do not edit or commit
`dist/` or `.test-dist/`. `npm pack` builds the distribution via `prepack`.
`experiments/run_real_v0_1.py` defaults to zero-call preflight. Paid runs require explicit scoped budget authorization and fresh output paths.
For this project, Ark calls must use the Agent Plan `/api/plan/v3` endpoint.

## Coding Style & Naming Conventions

No language-specific formatter or linter is configured. For Markdown, use one blank line between sections, wrap lines near 100 characters where practical, and use sentence-style headings. Prefer descriptive, lowercase filenames with hyphens (for example, `architecture-overview.md`). Follow the formatting conventions of any framework or language introduced later.

## Testing Guidelines

Put Python behavior tests in `tests/` and TypeScript DSH contracts in `validation/dsh/plugin/tests/`.
Use deterministic fake adapters and mocked judge responses for network-free tests; never make paid calls from tests. Run `uv run pytest` before every pull request.

## Commit & Pull Request Guidelines

Use short, imperative commit subjects (for example, `Add routing benchmark`) and add body details when the reason for the change is not obvious. Pull requests should include a clear summary, scope of changes, verification performed, and links to related issues or specifications.

## Security & Configuration Tips

Do not commit secrets, credentials, or environment-specific configuration. Add a `.gitignore` when generated files or dependencies appear.
