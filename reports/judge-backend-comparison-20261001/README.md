# 新版 Judge 題集三後端對照

## 凍結範圍與費用

本批使用 `advisor-judge-v2.json` 的 9 題和 `escalation-judge-v2.json` 的 12 題。
先前本地 Laya 已跑完同一批題；本次官方 Jev `jev-1.13.0` 和 Ark Agent Plan
`deepseek-v4-flash` 各完成 21 次真實請求。沒有 HTTP 自動重試、未知用量或題目重發。
所有請求及回執逐條保存在各後端的 `calls.jsonl`。模型費用根據用量回執和
凍結單價**估算**，未與提供方帳單核對。
Jev 回執核對了實際版本；目前 Ark 客戶端沒有保存回執模型版本，本批
`actualModel` 欄位只是當時請求的模型 ID，不能作為實際版本已核對的證據。
實驗腳本的後續新批次已改用 `requestedModel` 欄位。

| 後端 | 真實請求 | 本批估算費用 | 預檢上界 | 中斷／未知用量 |
| --- | ---: | ---: | ---: | ---: |
| 本地 Laya-MLX | 0 次遠端請求 | 無 API 費用 | — | 0 |
| 官方 Jev | 21 | 0.000537768 USD | 0.056448 USD | 0 |
| Ark DeepSeek Flash | 21 | 0.44155 AFP | 68.2752 AFP | 0 |

Jev 使用[官方模型頁](https://docs.typesafe.ai/models)列出的版本、
0.042 USD／百萬輸入 tokens 單價。Ark 使用已凍結的 Agent Plan 路線和
0.05 AFP／千輸入或輸出 tokens 估價。AFP 與 USD 分別記帳，不換算後排序。

## 逐題結果

下面的「符合」是與**本項目人工預期標籤**一致的題數，並非完整 Agent
任務的成功率。Laya 是本機推論耗時；Jev 和 Ark 耗時包含網路往返。

| 策略 | 納入題數 | Laya 符合／中位耗時 | Jev 符合／中位耗時 | Ark 符合／中位耗時 |
| --- | ---: | ---: | ---: | ---: |
| Advisor | 9 | 3／26.8 ms | 9／438.8 ms | 9／1352 ms |
| Escalation | 11 | 2／21.4 ms | 10／428.4 ms | 9／1839 ms |

Escalation 的 `mix-stall-tool` 題面同時包含「不得運行無關命令」和再次調用
`true`，既可解釋為明確違規，也可解釋為停滯。這條題已被三後端執行，
但**事先統一排除於符合率**；原始記錄仍保留。沒有在觀察新後端輸出後
改寫任何已跑過的題目或標籤。

按 Router 實際動作合併類別後，Advisor 的 Jev 和 Ark 都在 3 條合格題
批准、其餘 6 條停止或返工；Escalation 都放行 3 條正常繼續題，
其他 8 條進入接管分支。Laya 的 Advisor 有一條明確格式缺陷被批准，
且 3 條合格題被擋下；Escalation 的 3 條正常繼續題均未放行。

逐題差異值得保留：Jev 在中文結束輪停滯題的原始答案是 `STALL`，
原始選項概率 0.78，低於 0.8 門檻後變成 `UNCERTAIN`；結束輪仍接管。
Ark 在兩條缺少外部證據題將 `UNCERTAIN` 判成 `DEFECT`，這批題的接管
動作相同，但路由軌跡中的原因不同。Jev 對一條 Advisor 私有服務證據
不足題原始選擇 `REDO_EVIDENCE`，低於門檻後變成 `UNRESOLVED`。

## 判斷與下一個驗收門檻

這批證據支持繼續用官方 Jev 與普通 LLM 驗證 Advisor、Escalation：
兩者在此批題沒有錯誤放行，實際放行／接管動作一致。官方 Jev 在同題
遠端等待較短。Laya 目前不宜升為這兩個策略的日常預設；調低 0.8
門檻可能放行已觀察到的格式缺陷，不能直接這樣調整。

這批共 20 條計分題，標籤由項目內部制定，尚未經獨立覆核；結果無法證明
大樣本判別品質或真實任務的品質、成本收益。Jev／Laya 共用 Choice 問題；
普通 LLM 使用各策略 JSON 合同。Task 新 Score 題型、Stage 的選模門檻，
以及完整工具續接流程都不在本批內。下一個有限驗收應先由獨立覆核人
確認邊界題，再固定真實工具任務及其成功判據，核對模型選擇、接受／
接管、工具配對和最終產物；不得把本批題目符合率直接當成產品通過。

## 證據

- `comparison.json`：三後端逐題答案、原始類別、門檻後動作與耗時。
- `jev/preflight.json`、`jev/calls.jsonl`：Jev 凍結預檢和逐次回執。
- `llm/preflight.json`、`llm/calls.jsonl`：Ark 凍結預檢和逐次回執。
- [本地 Laya 原始報告](../judge-question-audit-20261001/README.md)：
  同一題集的本地對照及已知限制。
