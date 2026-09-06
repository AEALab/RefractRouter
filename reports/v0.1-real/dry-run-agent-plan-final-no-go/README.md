# Final Agent Plan paid dry-run result

This directory preserves the final issue #4 run from merged commit `b9d3bc8`. The run used the
OpenAI-compatible Chat Completions endpoint under the dedicated Agent Plan base URL
`https://ark.cn-beijing.volces.com/api/plan/v3`. The manifest rejects the ordinary Ark `/api/v3`
route, all four models used `thinking: {"type": "disabled"}`, and retries were disabled.

## Outcome

The DSH plugin returned `status=fail`, `mode=paid`, with `benchmark-incomplete` and
`plugin-runner-exit:1`. The experiment itself exited normally and emitted a complete evidence set;
the wrapper returned non-zero because the benchmark summary was incomplete. This is a consistent
**No-go** result and blocks the issue #5 pilot.

All 42 dispatched HTTP requests succeeded in one attempt and recorded provider request IDs:

| Model | Requests |
|---|---:|
| `deepseek-v4-flash` | 17 |
| `minimax-m3` | 12 |
| `deepseek-v4-pro` | 12 |
| `kimi-k3` judge | 1 |

The calls used 34,480 input tokens, 30,401 output tokens, 2,044 cached-input tokens, and zero
reasoning tokens. Request latency ranged from 3,310 to 20,579 ms. The benchmark ledger recorded
15.28745 AFP for production and 2.86 AFP for evaluation, for 18.14745 AFP total. After the run, the
Agent Plan console showed 59.906 AFP in the near-five-hour window, an increase of 19.354 AFP from the
40.552 pre-run reading; this includes the outer DSH agent in addition to the benchmark ledger.

## Completeness failures

Only `node-oracle` produced a final report and reached the independent judge. Its generated HTML was
truncated during `render_html`, so deterministic HTML validity and source trace failed. The judge
still completed and produced a 58.0 final score, but the failed source trace forced evidence accuracy
to zero.

The other four strategies did not produce final reports:

- `node-type-rule` returned invalid JSON at `build_outline`.
- `strong-all`, `task-oracle`, and `weak-all` returned invalid JSON at `write_report`.
- Those failures caused 12 downstream `upstream-failure` nodes and four
  `judge:missing-final-output` records.

The aggregate taxonomy is one `invalid-html`, four `invalid-json`, twelve `upstream-failure`, and
four `judge:missing-final-output`. Judge coverage was therefore incomplete, all five strategy runs
had a zero success rate, and the oracle gate correctly returned `No-go`.

## Evidence integrity

`dsh-evidence.json` records the frozen dataset, manifest, corpus, code, environment, command, exit
status, and artifact hashes. `evidence-index.json` adds hashes for each strategy run. Key hashes are:

| Artifact | SHA-256 |
|---|---|
| `preflight.json` | `b241d92693f166ad1180af5dff0fdd6c8958606245f3ffacd3bf5fe0c8f02b74` |
| `benchmark-summary.json` | `bb6286eb87d61d627f508e5e8c067e8b48185dfff0c66da468b8d9afff571ad5` |
| `model-progress.ndjson` | `2710cfe8ce434b8986976bb4b483cf4c3daf50a77298a777344ec9564d1135d4` |
| `evidence-index.json` | `30e46881c692656e2779e44fff4995044950d90f80766f69a0d2eef32e8b92aa` |

A credential-value scan covered all 14 raw evidence files before they were copied into the
repository and found zero matches. No additional paid retry is authorized or justified after this
terminal No-go result.
