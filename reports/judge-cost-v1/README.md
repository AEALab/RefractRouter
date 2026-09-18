# 評審成本治理收尾報告：本地 MoA 是否可取代雙重 Ark judge

日期：2026-09-18。範圍：以 reports/judge-cost-v1/replay-01/ 的 107 個已封存判例，
重播本地 CLI MoA（候選 A）的逐 criterion 裁決，對照 Ark 兩次封存裁決，並按
reports/judge-cost-v1/replay-01/thresholds.json 的凍結門檻判定是否可替換。
本報告只做判定一致性，不構成真人審查，也不證明用戶可接受性。

## 凍結門檻

verdict 一致率不低於 92.5234%；criterion 一致率不低於 95.0935%；「Ark 判 fail、
候選判 pass」不得超過 3.7383%。候選輸出無法解析或 CLI 失敗記 pending，
留在分母，不得剔除。未達門檻即不替換，保留現行 kimi-k3 judge。

## 結果

- 判例 107 個；Ark 自身兩次 judge 相互矛盾的 8 例單列，不計入主判定。
- 全部 107 例的 MoA 共識結果：pending 56 個、pass 45 個、fail 6 個。
- 45 個案例存在評審者不可用（多半是 claude CLI 五小時 session 額度用盡），
  54 個案例完整跑完，其 verdict 一致率 45/54＝83.33%，criterion 一致率
  184/216＝85.19%，風險方向（Ark fail、候選 pass）0 例。

## 即使補跑也過不了門檻的證明

45 個缺失案例即使全部補齊且逐例完全一致，在 pending 留在分母的凍結口徑下，
verdict 上限 (45＋45)/(54＋45)＝90.91%＜92.5234%，criterion 上限
(184＋180)/(216＋180)＝91.92%＜95.0935%。因此「不替換」的結論對缺失數據
是穩健的，不需要等 claude 額度重置後重跑。

## 判定

keep：不替換。線上 delivery-judge 與離線 research-judge 都保留現行 kimi-k3，
計為已知成本上限。省下的 72.9% 帳面 AFP（見 substitution-projection.json 的
106.8012 AFP 情景）屬於本地 CLI 帳本外，不能抵銷 83.33% 的一致率與其餘風險。

## 額外發現

- 本地 CLI 額度是硬約束：claude-opus 有 47 次因 session limit 在 4 秒內失敗
  （resets 8:10pm Asia/Shanghai）。
- 延遲不適合線上 45 秒交付閘門：ds/deepseek-v4-pro p90 109.9 秒、最長 462.6 秒，
  claude-opus p90 52.3 秒；僅可考慮離線研究評審位置。
- 輸出格式脆弱：strict 解析下有 6 次近義改寫 criterion（可修補）、1 次重複 JSON
  鍵（不可修復）與計數不符，全部記 pending。
- 升級層仍含 Ark 模型：4 例升級、7 個 criterion 觸發 ark/kimi-k3，產生本工具
  帳本之外的 Ark 用量；要使本地 MoA 真正零 AFP 必須連升級層一起治理。
- 牆鐘成本：222 次本地 CLI 調用，並行 3 個案 × 2 評審，總牆鐘約 112.8 分鐘。

## 產物

- moa-local-01/records.json：107 例逐例記錄（含 prompt 與回應哈希、退出碼、耗時）。
- moa-local-01/summary.json：一致性、門檻檢查與 decision＝keep。
- substitution-projection.json：both→cheap 121.1862 AFP（省 69.3%）、
  both→local-cli-moa 106.8012 AFP（省 72.9%）的純算術投影。

## 對下一階段的意義

可接受質量的前提下優先省 AFP 的方向不變，但「本地 MoA 頂替 judge」這條路在本批
判例上被凍結門檻否定；下一階段不應再擴大本地重播實驗。剩餘的低成本候選是
cheap 模型直接頂替 judge（候選 B，約 7 AFP／107 例，需明確放行），或導入與
質量門檻對齊的便宜評審，這些歸入下一階段規劃，不在本輪繼續。

"## 候选 B（cheap judge）小对照（2026-09-18，用户明确放行）\n\n同一份冻结判例与门槛，改用单一 cheap 评审（ark/deepseek-v4-flash，thinking=high，\n零重试，协议与估算上限见 cheap-judge-01/cheap-judge-protocol.json）。\n\n- 107 例重判完成：verdict 一致率 87.88%（门槛 92.5234%）、criterion 一致率\n  89.90%（门槛 95.0935%）、风险方向（Ark fail、候选 pass）4/107＝3.7383%，\n  刚好压过上限 3.7383%。结果不达标，按冻结规则 keep，不替换 kimi-k3 judge。\n- 成本：107 次调用，按封存 token 与 0.05 AFP/1k 估算约 7.19 AFP（记录内估算，\n  实际扣费以 Ark 侧为准）。\n- 两个候选都试过之后的一致性排序：Ark 同仪器重复取样 92.5%（参考下限） >\n  cheap judge 87.9% > 本地 MoA 83.3%。cheap 更便宜但目前无法达到替换门槛；\n  离现有 kimi-k3 只差 4.6 个百分点，属于后续可再校准的方向。\n"