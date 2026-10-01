# Judge 與 DSH 原生工具閉環有限驗收

## 範圍與停止規則

本批在 DSH `0.1.5-rc.3` 的標準 Base URL 適配器中運行。執行候選由本地
確定性模型夾具產生，DSH 真正執行 `refract_local_echo` 工具；Advisor 和
Escalation 的審核請求送到 Ark Agent Plan `deepseek-v4-flash`。Router 保留
候選、決策、工具續接和費用記錄，沒有自行執行宿主工具或建立 DAG。

每條流程預先保護至多兩次遠端 Judge 調用、每次 65,536 輸入 tokens 與
1,024 輸出 tokens、最多 **6.656 AFP**；四條合計上界 **26.624 AFP**。
提供方 HTTP 自動重試為零，失敗批次沒有原路徑重發。

## 四條固定流程

| 流程 | 結果 | 真實 Judge 調用 | 估算 AFP | 可核對行為 |
| --- | --- | ---: | ---: | --- |
| Advisor 正常 | 通過 | 1 | 0.03085 | DSH 執行一次工具，最終候選獲批 |
| Advisor 錯誤候選返工 | 通過 | 2 | 0.06670 | 錯誤候選丟棄；返工調用工具；第二次審核通過 |
| Escalation 正常 | 通過 | 2 | 0.05550 | 工具探索及最後答覆均放行 |
| Escalation 明確缺陷 | 通過 | 1 | 0.02145 | 高效候選丟棄；接管模型調用 DSH 工具並交付 |

四條成功流程的真實 Judge 費用合計 **0.17450 AFP**。執行模型是本地夾具，
沒有執行 API 費用；本表不能用來估計完整真實模型任務的單次成本。
費用根據用量回執及凍結 AFP 價格估算，沒有與帳戶帳單核對。

### 保留的失敗與修正

1. 首次 `advisor-normal-v2` 將 DSH 依賴指向錯誤目錄，在模型派發前退出，
   **0 次遠端調用、0 AFP**。其預檢、錯誤輸出和摘要仍保留。
2. `advisor-normal-v3` 的 DSH 工具流程實際通過，摘要腳本誤讀運行中的
   內存結構而報錯。從已持久化的任務記錄離線補出摘要，**沒有重發**；
   真實 Judge 調用及 0.03085 AFP 保留。
3. `advisor-redo-v4` 的候選聲稱已執行工具，歷史卻沒有工具事件。Ark Judge
   回答 `UNRESOLVED`，Router 安全停止；該批已結算 **0.01880 AFP**。
   實際請求顯示原審核提示未區分「必需工具未執行」與「一般外部事實缺證據」。
   本次補明規則：用戶明確要求工具調用，而已接受歷史與可信事件均缺少它，
   候選卻聲稱完成時應 `REDO`。新批 `advisor-redo-v5` 隨後通過。

計入失敗但用量已確認的調用，本輪全部 Ark Judge 估算費用為 **0.19330 AFP**。
每個批次的 `preflight.json`、`dispatch.started`、持久運行記錄、DSH 輸出和
`summary.json` 均按原路徑保存，未覆蓋失敗證據。

## 官方 Jev 對相同工具上下文的事後重放

從四條完成流程抽取六份原始 Judge 請求；已確認只有合成任務文本，沒有
本機絕對路徑。固定 `jev-1.13.0` 和原有 `choice-v2` 問題、0.8 門檻，
對這六份請求做一次事後判別。沒有重執行工具，也沒有改變當時 Router 的決策。
預檢上界為 **0.016128 USD**；六次實際估算 **0.000202230 USD**，
按[官方模型單價](https://docs.typesafe.ai/models)及回執輸入量計算。

| 判別 | Ark 當時動作 | Jev 原始 Choice | Jev 經 0.8 門檻 |
| --- | --- | --- | --- |
| Advisor 正常結束 | APPROVE | APPROVE，0.99 | APPROVE |
| Advisor 錯誤候選 | REDO | REDO_EVIDENCE，0.70 | UNRESOLVED |
| Advisor 返工復審 | APPROVE | APPROVE，0.38 | UNRESOLVED |
| Escalation 正常工具探索 | PROCEED | PROCEED，0.75 | UNCERTAIN |
| Escalation 正常最終答覆 | PROCEED | PROCEED，0.99 | PROCEED |
| Escalation 明確缺陷 | DEFECT | DEFECT，1.00 | DEFECT |

Jev 原始首選與這六條人工預期一致；依現有門檻映射後為 **3／6**。
三條保守回退未造成錯誤放行，但會使 Advisor 返工或復審停止，或讓正常
工具探索進入強模型接管。Jev 中位遠端判別耗時約 **401 ms**。
不能用這六條已觀察題直接調低門檻；另需獨立校準題和留出題，檢查降低
門檻是否放行明確缺陷。目前 Jev 重放只驗證判別後端，**不是 Jev 已接入
Router 的實際調用路徑**。

同六份輸入另以固定 revision 的本地 Laya-MLX 離線重放，六份均未觸發
容量拒絕，原始分類僅 **1／6** 符合預期，經 0.8 門檻後 **0／6**；
暖機後中位推論約 **41.6 ms**，冷載入約 **992 ms**，沒有 API 費用。
其中錯誤候選的原始首選為 `APPROVE`，目前門檻將它擋為 `UNRESOLVED`。
這與前批題集的本地弱點一致，進一步支持保持實驗標識。

## 標籤敏感性與適用邊界

前批 12 條 Escalation 題的一條「無關工具」案例同時可歸為停滯與明確違規，
原報告已將它排除符合率。另三條「缺少外部證據但候選作出猜測」在現有
`UNCERTAIN`／`DEFECT` 合同邊界上仍有語義歧義。若作為敏感性分析把四條
全部排除，前批 Escalation 標籤符合數變為 Laya **0／8**、Jev **7／8**、
Ark **8／8**。這是**事後敏感性分析**，不能取代凍結的主報告或當作
新的盲測成績；題目標籤仍待獨立覆核。

本批四條 DSH 工具流程是有界功能驗收，不證明真實任務品質或模型成本收益。
Codex、Hermes 的本次新 Judge 合同未重跑；兩端既有標準工具接線證據見
[先前產品報告](../advisor-composite-product-acceptance-20260929/README.md)。
圖片／影片審核、Task 新 Score 題型和 Stage 判別門檻也不在本批內。

## 原始證據

- `advisor-normal-v3/`、`advisor-redo-v5/`、`escalation-normal-v4/`、
  `escalation-defect-v4/`：四條通過流程。
- `advisor-normal-v2/`、`advisor-redo-v4/`：兩條失敗路徑及費用證據。
- `jev-replay-v1/preflight.json`、`jev-replay-v1/calls.jsonl`：Jev 事後重放。
- `laya-replay-v1.json`：同六份輸入的本地權重事後重放。
- [前批三後端題集對照](../judge-backend-comparison-20261001/README.md)：
  固定小題的原始結果、門檻及歧義說明。
