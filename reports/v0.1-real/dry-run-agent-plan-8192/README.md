# Agent Plan dry-run admission passed

Issue #19's live validation ran from clean merged commit `f69e0d2` on 2026-09-06 through the native
DSH `refractrouter_validate` tool. The user approved one additional run with a 495 AFP allowance:
400 production, 90 evaluation, and 5 for the outer DSH agent. All listed Plan overage switches were
disabled before dispatch.

## Acceptance result

DSH returned `status=pass`, `mode=paid`, `issues=[]`; the experiment exited 0 and the benchmark
summary has `status=complete`. All 61 planned benchmark calls completed: 56 production and 5
independent `kimi-k3` evaluations. Every request used the dedicated
`https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions` endpoint, completed in one attempt,
and recorded a provider request ID and `finish_reason=stop`.

All five strategies have 100% success and judge coverage. The failure taxonomy is empty. Independent
local source-trace checks found no issues in any final report. All 20 artifact hash checks in the DSH
evidence and experiment index match. The original 14 raw evidence files passed a credential-value
scan with zero hits.

The largest observed output was 2,430 tokens, above the previous 1,200-token cap and below the new
8,192-token cap. No output was truncated. This verifies the correction under this single live task;
it is not a guarantee that every future task will fit.

## Usage and costs

| Model | Calls | Estimated AFP from request usage |
|---|---:|---:|
| `deepseek-v4-flash` | 23 | 1.96670 |
| `minimax-m3` | 17 | 9.19425 |
| `deepseek-v4-pro` | 16 | 19.28300 |
| `kimi-k3` | 5 | 17.15300 |

Production cost was **30.44395 AFP**, evaluation cost **17.153 AFP**, and benchmark total
**47.59695 AFP**. Telemetry recorded 83,888 input tokens, 44,436 output tokens, 6,942 cached-input
tokens (included in input), and zero reasoning tokens. Request latencies ranged from 1,790 to
22,683 ms.

The two outer DSH model turns are recorded separately in `outer-agent-usage.json`. Their disjoint
input/cache/output usage yields an estimated 1.1972 AFP at the frozen Flash rate, below the 5 AFP
allowance. Combined benchmark and outer-agent telemetry estimate: **48.79415 AFP**, below 495 AFP.
This directory contains experiment-specific usage only, not account-wide billing statistics.

## Routing outcome and interpretation

| Strategy | Judge-composed score | Per-strategy production AFP | Critical-path ms |
|---|---:|---:|---:|
| `weak-all` | 100 | 0.50640 | 49,527 |
| `strong-all` | 86 | 8.77525 | 83,907 |
| `node-type-rule` | 93 | 3.03530 | 43,055 |
| `task-oracle` | 100 | 0.50640 | 49,527 |
| `node-oracle` | 84 | 0.50680 | 41,082 |

The fixed routing-benefit gate returns **No-go**: node-oracle's score is 16 points lower at nearly
identical cost (0.078989% higher). Its latency ratio is 0.829487, so latency, reliability and judge
coverage pass, while both benefit paths fail.

Both oracles selected **Flash for all seven nodes**. Task-oracle reuses the selected single-model
report; node-oracle performs a fresh composed run. Their outputs and judge assessments differ, so
the score gap cannot be attributed to different model assignments. The node-oracle judge penalized
unsupported claims and shallow analysis. This is one task with one repeat; the reported p95 is only
that single observation, and the scores are not human-audited research conclusions.

The dry-run admission gate is therefore passed, while this one-task routing-benefit gate is No-go.
Issue #19 can close as verified. Issue #5's truncation blocker is removed; its separate pilot budget
and execution still need to be addressed. No pilot was executed under this dry-run authorization.

## Artifacts

- `dsh-evidence.json`: invocation, environment, input/code hashes, exit status and artifact hashes.
- `benchmark-summary.json`: scores, costs, coverage, failure taxonomy and routing gate.
- `model-progress.ndjson`: prompt-free start/finish telemetry for all 61 requests.
- `evidence-index.json`: original artifact and selected strategy record hashes.
- `runs/report_001/repeat-1/`: final outputs, node telemetry and judge evaluations for five strategies.
- `outer-agent-usage.json`: only the two outer model usage events, without prompts or account data.

Original generated files are preserved byte-for-byte. This README and the outer-agent usage summary
are supplemental; they are not claimed as members of the original experiment hash index.
