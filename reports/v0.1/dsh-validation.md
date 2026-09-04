# DSH Validation Summary

- Date: 2026-09-05 (Asia/Shanghai)
- DSH version: `0.1.1-rc.2`
- Execution: real `dsh --profile headless` session in a disposable workspace
- Validator status: **pass**
- Validator exit code: `0`
- Validation issues: none
- Source-trace issues: none
- Code tree SHA-256: `c5d6c9ae709d6cacc1b44649f7ec67f203ee3933bb045185cfd1d006b43f7d81`
- Raw evidence SHA-256: `3dcf898b3880526c602c57a0c823a4b74b67c88f53f9644c194c499c8b31ce0a`

## Independently recomputed oracle result

| Metric | Value |
|---|---:|
| Quality delta | 0.000000 |
| Cost reduction | 74.952199% |
| Latency ratio | 2.308226x |
| Gate | **No-go** |

## Artifact hashes

| Artifact | SHA-256 |
|---|---|
| `baseline-table.md` | `c2e7b26a339709f80adbf8db52b7c0f1110b944d352e00a66a02cd033c7e8d42` |
| `pareto-front.md` | `49e6874fe5bbc5e0292bebd848dc2df3a3270d663cf1452b06cc042d6ea7fe07` |
| `oracle-gap.md` | `6b9556e34f2ab097ecbb933ea1c9e1900ff8be19029018afe861cbf91168aed8` |
| `experiment-summary.json` | `5d84fa0c11837d6b76b2178130b66970716bdcbbc374e47bd42ec14052c65cf5` |
| `run-record.json` | `14e7f16ffd13d09ac7178cacda55cc8db530016bb1aae95b039a6cae5a037f84` |
| `report_001.html` | `cd1b83730dfdc65dba41faf5040d5fddc04ab0181b0a70e5f50cb19834f34ccc` |

The validator evidence was read directly after the DSH session. Its code hash matched the current
implementation, and all six artifact hashes matched an independent local canonical run. The raw
session used a disposable path, so this summary records stable verification facts without treating
that temporary path as a durable evidence location.

This verifies orchestration, reproducibility, artifact integrity, and source trace for the fake
adapter experiment. It does not validate real-model quality, latency, or cost.
