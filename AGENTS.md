# Repository Guidelines

## Project Structure & Module Organization

This repository is currently documentation-only. `README.md` is the root project README and the sole tracked file. As implementation work begins, place source code in purpose-specific top-level directories (for example, `src/` and `tests/`) and keep static assets under a directory such as `assets/`.

## Build, Test, and Development Commands

No build, test, or development commands are configured yet. For repository maintenance, use `git status`, `git diff`, and `git log` to inspect changes before committing. Update this section as soon as package, build, or test tooling is added.

## Coding Style & Naming Conventions

No language-specific formatter or linter is configured. For Markdown, use one blank line between sections, wrap lines near 100 characters where practical, and use sentence-style headings. Prefer descriptive, lowercase filenames with hyphens (for example, `architecture-overview.md`). Follow the formatting conventions of any framework or language introduced later.

## Testing Guidelines

There are currently no tests or testing frameworks. When tests are introduced, put them in `tests/`, mirror the production directory layout, and name files after the behavior under test. Run the full test suite before every pull request and document the command here.

## Commit & Pull Request Guidelines

The history contains only the initial commit, `first commit`, so no repository-specific commit convention has been established. Use short, imperative commit subjects (for example, `Add routing benchmark`) and add body details when the reason for the change is not obvious. Pull requests should include a clear summary, scope of changes, verification performed, and links to related issues or specifications.

## Security & Configuration Tips

Do not commit secrets, credentials, or environment-specific configuration. Add a `.gitignore` when generated files or dependencies appear.
