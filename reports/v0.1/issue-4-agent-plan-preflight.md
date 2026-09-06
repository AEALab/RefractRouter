# Issue #4 Agent Plan preflight

Prepared on 2026-09-06. This note freezes the no-cost inputs for the one-task paid dry run; it is
not evidence that any real model was called.

## Provider boundary

Volcengine documents Agent Plan text models for supported AI tools and warns against using the
personal-plan endpoint as a general API. DeepSeek Harness is a supported tool and exposes Agent
Plan through `openai-completions` or `openai-responses` providers. RefractRouter therefore sends
model requests through the hosting DSH `llm` service. The Python runner receives model output and
telemetry over a bounded stdio bridge; `CODEX_ARK_API_KEY` remains owned by DSH.

Official references:

- [Agent Plan AFP deduction rules](https://www.volcengine.com/docs/82379/2516283?lang=zh)
- [Agent Plan packages, models, and usage limits](https://www.volcengine.com/docs/82379/2366394?lang=zh)
- [Agent Plan with DeepSeek Harness](https://www.volcengine.com/docs/82379/2637928?lang=zh)
- [Agent Plan with Codex](https://www.volcengine.com/docs/82379/2556054?lang=zh)

## Frozen model pool

AFP for text models is `(input tokens × input coefficient + output tokens × output coefficient) /
10,000`. The manifest stores the equivalent AFP per 1,000 tokens.

| Role | Model | AFP coefficient | AFP / 1k input | AFP / 1k output |
|---|---|---:|---:|---:|
| Candidate: cheap | `deepseek-v4-flash` | 0.5 | 0.05 | 0.05 |
| Candidate: mid | `minimax-m3` | 2.5 | 0.25 | 0.25 |
| Candidate: strong | `deepseek-v4-pro` | 5.5 | 0.55 | 0.55 |
| Independent judge | `kimi-k3` | 10 | 1.00 | 1.00 |

`kimi-k3` is available on Medium, Large, and Max plans. The benchmark uses its explicit model name,
not the promotional Auto route whose model mix can vary by time of day.

## Call and budget plan

The dry run contains 56 production calls and 5 judge calls. With the existing conservative
assumptions of 4,000 input and 1,200 output tokens per production call, and 8,000 input and 1,200
output tokens per judge call, the estimates are shown below. The manifest enforces 1,200 as the
request output cap for every candidate and judge model, so the output assumption is also a hard
per-call bound.

| Ledger | Estimate | Proposed ceiling |
|---|---:|---:|
| Production | 160.16 AFP | 200 AFP |
| Evaluation | 46 AFP | 60 AFP |
| Total | 206.16 AFP | 260 AFP |

A native DSH tool call also uses the outer agent before and after tool execution. That usage is not
part of the benchmark production or evaluation ledger. The execution profile pins the outer agent to
`ark-plan/deepseek-v4-flash` and reserves a separate 5 AFP operational allowance. The complete
approval ceiling is therefore 265 AFP.

Before paid execution, the DSH profile must expose provider route `ark-plan`, resolve all four model
names, store the credential under `CODEX_ARK_API_KEY`, keep Agent Plan overage disabled, and set the
plugin manifest and AFP ceilings. The paid switch remains disabled until those facts and the final
ceilings are explicitly approved.

Both the DSH provider and the runner set `maxRetries: 0`. The plugin verifies the effective provider
policy before launching a paid subprocess. It also carries the runner's 120-second per-model timeout
over the stdio bridge, in addition to the whole-run deadline. The runner rejects ceilings below the
preflight estimates and reserves one estimated call before every production or judge invocation.
The account-level Agent Plan overage switch remains the final hard stop if actual token usage exceeds
the estimate.

## Zero-cost verification

The local preflight completed with `status=pass`, `issues=[]`, 61 planned calls, zero retries, and no
model invocation. It detected the credential reference without recording its value. The generated
`preflight.json` SHA-256 was
`6c6840d4ed60ede24b7c8a3d63a4b7efe13588209575423b7dd7dcefaaf75e71`; the manifest SHA-256 was
`9347a5d1ea4a91e989c530cbfed51cc3a4b2b21047e63b428c325c5eeb781edf`.

The Python suite passed 52 tests, the Node DSH contract suite passed 10 tests, the `0.2.0` package
dry run contained only the expected five files, and an isolated DSH profile passed install,
configuration override, removal, reinstall, and boot with `paid_calls=0`. The workstation's default
`headless` profile did not compose successfully and no `ark-plan` route could be verified there, so
provider configuration remains a required deployment step before paid execution.

A disposable DSH home was then created from the reviewed plugin. It boots successfully with the
official `openai-responses` Agent Plan endpoint, all four model declarations, the AFP plugin limits,
and `ark-plan/deepseek-v4-flash` as its outer agent. Exact runtime route resolution still requires a
DSH tool turn, which consumes AFP and is intentionally deferred to the approved paid execution.

## First execution attempt and runtime guard correction

The approved DSH turn reached `ark-plan/deepseek-v4-flash`, used 11,631 input and 130 output tokens
for the outer agent (about 0.58805 AFP), and called `refractrouter_validate` exactly once. The tool
had not returned final evidence after more than ten minutes, so the run was stopped. The bridge did
not persist per-call progress, so local evidence cannot identify which benchmark request was active
at that point. No benchmark output beyond `preflight.json` was produced; any provider-side AFP
consumed by that incomplete run is therefore not yet known from local telemetry.

Inspection of the pinned DSH runtime showed that an omitted provider retry policy resolves to five
retries at the agent failed-step layer, while direct `ctx.llm.stream()` calls remain single-attempt.
It also showed that the runner's 120-second timeout had not crossed the stdio bridge. Plugin 0.2.1
closes both deployment gaps: paid execution fails before spawn unless the effective provider policy
is normal mode with zero retries, and every bridge request now carries a bounded timeout that aborts
its DSH stream. A fresh paid attempt remains conditional on passing the corrected zero-cost checks
and accounting for the earlier attempt against the approved total ceiling.

The correction passed all 52 Python tests, 11 Node contract tests, the five-file `0.2.1` package
check, and a clean DSH `0.1.1-rc.2` install/override/remove/reinstall/boot lifecycle with zero paid
calls.

A corrected retry/timeout run was also stopped after about four minutes because no final artifact was
yet visible. Since artifacts are written only after all 61 planned calls, their absence was not proof
of per-call timeouts. A minimal direct DSH probe subsequently succeeded on
`deepseek-v4-flash` in 2,394 ms with 93 input and 27 output tokens, proving the endpoint, credential,
model route, streaming seam, and zero-retry provider policy were healthy. The exact first benchmark
request was then reconstructed locally with 294 system characters, 587 user characters, a 1,200-token
cap, and a 120-second deadline; it completed through the live DSH route in 4,609 ms with a
1,004-character JSON result.

The diagnosis also found an independent budget-to-request-cap mismatch: the AFP estimate assumed
1,200 output tokens while the manifest allowed 8,192. The manifest now caps requests at 1,200 tokens,
and paid execution rejects any output estimate below the selected manifest's maximum request cap.
The corrected zero-cost preflight retained the 206.16 AFP estimate and produced manifest SHA-256
`b100b2deef173dd301d11ce9f48785958b1f4f3981cfab82b6ee4c97621cba97` and preflight SHA-256
`869c3cf12e9bdf840cf8aab67d8cfcf0f4d1c8a35838cca2e093dce9fd777885`. The correction passed 53
Python tests and all 11 Node contract tests.

## Hard-timeout and progress correction

Before a subsequent full attempt, the Agent Plan console showed 5.809 AFP of near-five-hour usage,
matching the increase from the recorded weekly and monthly baselines. The attempt used only the
`ark-plan` provider at `https://ark.cn-beijing.volces.com/api/plan/v3`, with Agent Plan overage
disabled. It passed preflight at 15:15:55 local time but produced no request-level artifacts.

After 1 hour 12 minutes, a process inspection showed the Python runner sleeping with 0.72 seconds of
CPU time. Neither it nor the DSH parent held a TCP connection. The Python bridge was blocked waiting
for a response line while the plugin was blocked inside the DSH stream iterator, proving that the
provider stream did not settle when its supplied abort signal expired. The run was terminated; its
provider-side AFP after the 5.809 baseline is unknown until the Agent Plan console is refreshed.

Plugin 0.2.2 makes the timeout local and deterministic by racing every iterator read against the
request signal and detaching iterator cleanup on abort. It also writes a prompt-free
`bridge-progress.ndjson` start/finish record for every request, including the selected provider,
model, status, latency, and usage. A run can now identify the active request and completed count
without waiting for all benchmark artifacts.
