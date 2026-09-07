# Node quality matrix

Independent semantic scores capped by contract checks. * marks the selected model.
Full outputs, checks, rationale, telemetry and exclusions are in the JSON matrix.

## probe / report_001 / repeat 1

| Node | deepseek-v4-flash | minimax-m3 | deepseek-v4-pro |
|---|---:|---:|---:|
| parse_requirements | 93 | 93 | 93 |
| build_outline | 81 | 84 | 95 |
| extract_evidence | 93 | 95 | 100.0 |
| synthesize_analysis | 0.0 (ineligible) | 86 | 78 |
| write_report | 83 | 86 | 92 |
| render_html | 93 | 98 | 92 |
| verify_report | 72 | 83 | 90 |

## probe / report_001 / repeat 2

| Node | deepseek-v4-flash | minimax-m3 | deepseek-v4-pro |
|---|---:|---:|---:|
| parse_requirements | 90 | 93 * | 83 |
| build_outline | 100.0 * | 100.0 | 86 |
| extract_evidence | 88 | 100.0 * | 87 |
| synthesize_analysis | 62 | 80 * | 77 |
| write_report | 84 | 84 | 85 * |
| render_html | 93 | 96 * | 94 |
| verify_report | 76 | 54 | 83 * |

## probe / report_001 / repeat 3

| Node | deepseek-v4-flash | minimax-m3 | deepseek-v4-pro |
|---|---:|---:|---:|
| parse_requirements | 98 * | 82 | 82 |
| build_outline | 94 | 100.0 * | 93 |
| extract_evidence | 100.0 * | 93 | 87 |
| synthesize_analysis | 67 | 88 * | 84 |
| write_report | 85 | 89 | 90 * |
| render_html | 93 * | 90 | 89 |
| verify_report | 61 | 89 * | 78 |

