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
output tokens per judge call, the estimates are:

| Ledger | Estimate | Proposed ceiling |
|---|---:|---:|
| Production | 160.16 AFP | 200 AFP |
| Evaluation | 46 AFP | 60 AFP |
| Total | 206.16 AFP | 260 AFP |

Before paid execution, the DSH profile must expose provider route `ark-plan`, resolve all four model
names, store the credential under `CODEX_ARK_API_KEY`, keep Agent Plan overage disabled, and set the
plugin manifest and AFP ceilings. The paid switch remains disabled until those facts and the final
ceilings are explicitly approved.

The DSH profile sets `maxRetries: 0`. The runner rejects ceilings below the preflight estimates and
reserves one estimated call before every production or judge invocation. The account-level Agent
Plan overage switch remains the final hard stop if actual token usage exceeds the estimate.

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
