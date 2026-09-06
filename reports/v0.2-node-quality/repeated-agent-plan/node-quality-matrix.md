# Node quality matrix

Independent semantic scores capped by contract checks. * marks the selected model.
Full outputs, checks, rationale, telemetry and exclusions are in the JSON matrix.

## probe / report_001 / repeat 1

| Node | deepseek-v4-flash | minimax-m3 | deepseek-v4-pro |
|---|---:|---:|---:|
| parse_requirements | 93 | 94 * | 91 |
| build_outline | 93 | 94 * | 93 |
| extract_evidence | 87 | 93 * | 93 |
| synthesize_analysis | 79 | 83 * | 78 |
| write_report | 96 * | 0.0 (ineligible) | 89 |
| render_html | 90 | 94 * | 94 |
| verify_report | 88 | 91 | 93 * |

## probe / report_001 / repeat 2

| Node | deepseek-v4-flash | minimax-m3 | deepseek-v4-pro |
|---|---:|---:|---:|
| parse_requirements | 94 | 100.0 | 93 |
| build_outline | 94 | 89 | 85 |
| extract_evidence | 97 | 97 | 95 |
| synthesize_analysis | 73 | 80 | 81 |
| write_report | 86 | 0.0 (ineligible) | 90 |
| render_html | 89 | 94 | 94 |
| verify_report | 100.0 | 56 | 100.0 |

## probe / report_001 / repeat 3

| Node | deepseek-v4-flash | minimax-m3 | deepseek-v4-pro |
|---|---:|---:|---:|
| parse_requirements | 93 | 91 | 94 |
| build_outline | 100.0 | 88 | 87 |
| extract_evidence | 89 | 96 | 95 |
| synthesize_analysis | 89 | 84 | 84 |
| write_report | 89 | 0.0 (ineligible) | 87 |
| render_html | 83 | 96 | 94 |
| verify_report | 93 | 60 | 83 |

