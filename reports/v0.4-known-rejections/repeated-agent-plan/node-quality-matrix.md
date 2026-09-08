# Node quality matrix

Independent semantic scores capped by contract checks. * marks the selected model.
Full outputs, checks, rationale, telemetry and exclusions are in the JSON matrix.

## probe / report_001 / repeat 1

| Node | deepseek-v4-flash | minimax-m3 | deepseek-v4-pro |
|---|---:|---:|---:|
| parse_requirements | 80 | 95 * | 89 |
| build_outline | 100.0 * | 94 | 98 |
| extract_evidence | 91 | 94 * | 87 |
| synthesize_analysis | 73 | 81 * | 76 |
| write_report | 75 | 81 | 86 * |
| render_html | 100.0 * | 93 | 98 |
| verify_report | 87 * | 51 | 71 |

## probe / report_001 / repeat 2

| Node | deepseek-v4-flash | minimax-m3 | deepseek-v4-pro |
|---|---:|---:|---:|
| parse_requirements | 93 | 94 * | 80 |
| build_outline | 64 | 82 | 94 * |
| extract_evidence | 89 | 93 * | 93 |
| synthesize_analysis | 79 | 84 * | 84 |
| write_report | 85 | 87 | 93 * |
| render_html | 89 | 97 * | 96 |
| verify_report | 90 * | 37 | 70 |

## probe / report_001 / repeat 3

| Node | deepseek-v4-flash | minimax-m3 | deepseek-v4-pro |
|---|---:|---:|---:|
| parse_requirements | 93 * | 93 | 88 |
| build_outline | 72 | 94 * | 94 |
| extract_evidence | 91 | 92 | 94 * |
| synthesize_analysis | 73 | 82 * | 78 |
| write_report | 77 | 86 * | 84 |
| render_html | 85 | 92 * | 92 |
| verify_report | 93 | 68 | 100.0 * |

