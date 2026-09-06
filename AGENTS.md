# Repository Guidelines

## Project Structure & Module Organization

Python implementation lives in `src/refractrouter/`, benchmark entry points in `experiments/`,
frozen tasks, sources, manifests and rubrics in `data/`, tests in `tests/`, and DSH integration
in `validation/dsh/`. Historical evidence lives in `reports/`; preserve completed run artifacts.

## Build, Test, and Development Commands

Use `uv sync --frozen --extra dev --extra deepagents` to install dependencies and `uv run pytest`
to run the full suite, including Node contract tests. `experiments/run_real_v0_1.py` defaults to
zero-call preflight. Paid runs require explicit scoped budget authorization and fresh output paths.
For this project, Ark calls must use the Agent Plan `/api/plan/v3` endpoint.

## Coding Style & Naming Conventions

No language-specific formatter or linter is configured. For Markdown, use one blank line between sections, wrap lines near 100 characters where practical, and use sentence-style headings. Prefer descriptive, lowercase filenames with hyphens (for example, `architecture-overview.md`). Follow the formatting conventions of any framework or language introduced later.

## Testing Guidelines

Put behavior tests in `tests/`. Use deterministic fake adapters and mocked judge responses for
network-free tests; never make paid calls from tests. Run `uv run pytest` before every pull request.

## Commit & Pull Request Guidelines

Use short, imperative commit subjects (for example, `Add routing benchmark`) and add body details when the reason for the change is not obvious. Pull requests should include a clear summary, scope of changes, verification performed, and links to related issues or specifications.

## Security & Configuration Tips

Do not commit secrets, credentials, or environment-specific configuration. Add a `.gitignore` when generated files or dependencies appear.
