# Interrupted live scoring check

The user authorized the three-repeat validation within 2505 AFP on 2026-09-06.
Execution used merged commit `28cd8ac` through DSH and the Agent Plan-only endpoint.
The console's listed pay-as-you-go overage switches were disabled before dispatch.

The run was stopped after 41 completed requests and 11 saved matrix cells. Pro's extraction output
contains multiple **distinct** facts for each source, with correct identities. The v0.2 check rejected
any repeated source ID, incorrectly treating distinct claims as duplicated evidence and assigning
zero quality before semantic evaluation. Its candidate prompt did not prohibit multiple facts per
source. Continuing this run would produce biased node selection.

The fix deduplicates `(source_id, normalized claim)` while counting unique source IDs independently.
Semantic support still requires the independent judge. Different facts from the same source remain
eligible; repeating the same fact does not improve coverage or quality. Node contract checks advance
to v0.3; the semantic rubric remains v0.2.

Original preflight, progress and incremental node records are preserved byte-for-byte. This is a
partial run, with no completed benchmark or final matrix. Known production is 17.282 AFP and known
node evaluation is 29.144 AFP. One interrupted Kimi request lacks final usage; reserve 16.192 AFP
instead of claiming it was free. The one outer Flash call used an estimated 0.5926 AFP.
`interruption.json` records these values and raw hashes. Account-wide usage is not included.

The recovery remains within the approved total of 2505 AFP. Reallocate 20 AFP of production reserve
to evaluation (1180 production / 1320 evaluation / 5 outer). The fresh run uses ceilings of
1160 production / 1270 evaluation after retaining prior costs and the unsettled request reserve.
Combined maximum admitted envelopes plus prior recorded/reserved costs and the full outer allowance
are 2497.618 AFP. No additional spending authorization is requested.
