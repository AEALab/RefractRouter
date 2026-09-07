# Implementation language and ownership

The approved language boundary is Python + TypeScript
([issue #28](https://github.com/AEALab/RefractRouter/issues/28)).

| Layer | Language and source | Responsibilities |
|---|---|---|
| Router and experiments | Python: `src/refractrouter/`, `experiments/`, Python scripts and runners | Task DAGs, node execution and model assignment, routing strategies, scoring and evaluation, datasets, model adapters, cost and critical-path latency, experimental decisions |
| DSH integration | TypeScript: `validation/dsh/plugin/src/` | Plugin entry, configuration and tool types, native host services, subprocess and credential boundaries, structured tool results |
| DSH contracts | TypeScript: `validation/dsh/plugin/tests/` | Host service fixtures, entry and package compatibility, zero-cost Python preflight, budget, endpoint, and process safeguards |

Markdown, JSON and YAML remain documentation and data formats. JavaScript emitted by the TypeScript
compiler is a runtime artifact. Do not introduce handwritten JavaScript implementation or migrate
Router business logic into the plugin.

## Execution boundary

The application supplies a frozen task DAG. Python runs it through DeepAgents and LangGraph, assigns
models and evaluates outputs. The DSH tool validates host inputs and deployment limits, starts the
fixed Python runner using DSH native subprocess and sandbox services, and projects the returned
Python evidence. TypeScript validates the shape of the fields it exposes; Python owns scoring,
artifact hash verification, budget accounting, and Go / No-go decisions. The deployment ceilings
in TypeScript restrict what the host may request; Python enforces the experiment's call ledger.

AFP requests retain provider `ark-plan` and the exact `/api/plan/v3` endpoint. The plugin resolves
credentials only for an enabled paid operation with both explicit budgets. Generic DSH LLM bridge
messages carry prompts and telemetry; the bridge does not choose a model or evaluate quality.

## Source, build and distribution

The plugin's `src/index.ts` is compiled to `dist/index.js`; `main` and `exports` name that generated
entry. `dist/*.d.ts` describes the public types. Both source and test compiler configurations use
`strict: true` and refuse emission on errors. The small structural host interfaces in `contracts.ts`
describe the DSH 0.1.1-rc.2 service surface consumed by this bundle; they are not an implementation of
DSH. Native compatibility is checked by booting an isolated profile, in addition to typed fakes.

`package-lock.json` pins TypeScript and Node type declarations as development dependencies. Build
with `npm ci --prefix validation/dsh/plugin` followed by
`npm run --prefix validation/dsh/plugin build`. DSH continues to use pnpm 10.15.0 for profile
installation; npm manages the bundle's locked development toolchain.

The private package contains only generated `dist/`, `package.json`, `cordis.patch.yml`, `README.md`
and `CHANGELOG.md`. Tests compile separately to ignored `.test-dist/` and execute against `dist/`.
Neither generated directory is committed. `npm pack` runs the build via `prepack`; installing a local
checkout requires an explicit build first. The tarball has no runtime dependencies or install-time
compilation, and still requires the matching Python checkout at execution time.

## Architecture review rule

Before adding another implementation language or duplicating business decisions across the layers,
record a proposed exception in an architecture issue or ADR and obtain maintainer approval before
merging. The review must identify the owning layer, why Python or TypeScript cannot meet the need,
alternatives, dependency and distribution costs, data contracts, test coverage, and migration or
rollback strategy. If duplication is proposed, specify the authoritative implementation and how
behavioral drift will be prevented. Routine changes inside the existing ownership boundary do not
require a new architecture approval.

## Verification

CI installs the locked Python and TypeScript dependencies, type checks and builds the plugin, and
runs `uv run pytest`, which includes the compiled TypeScript contracts. The compatibility matrix
boots DSH 0.1.1-rc.2 on Node 22.19.0 and latest Node 22, exercises install/override/remove/reinstall,
and checks both checkout and packaged distribution. These checks make no model calls. Completed
experiment artifacts under `reports/` are preserved as historical evidence.
