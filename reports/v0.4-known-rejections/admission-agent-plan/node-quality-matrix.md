# Node quality matrix

Independent semantic scores capped by contract checks. * marks the selected model.
Full outputs, checks, rationale, telemetry and exclusions are in the JSON matrix.

## probe / report_001 / repeat 1

| Node | deepseek-v4-flash | minimax-m3 | deepseek-v4-pro |
|---|---:|---:|---:|
| parse_requirements | 80 | 92 * | 82 |
| build_outline | 65 | 92 | 95 * |
| extract_evidence | 88 | 100.0 * | 100.0 |
| synthesize_analysis | 84 | 82 | 85 * |
| write_report | 88 | 86 | 95 * |
| render_html | 95 | 100.0 * | 96 |
| verify_report | 92 * | 58 | 90 |

