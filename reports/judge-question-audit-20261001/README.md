# Judge 題型與宿主協議留出題核對

## 範圍

本批只使用已下載的 `aac6fef/laya-multilingual-mlx` 固定 revision
`f2b4faf51023039425946074e2cf1361d2db11d5`，沒有 API 費用、網路呼叫或權重下載。
本次不是舊 24 題的重算，也不是官方 Jev 比較或完整 Agent 任務驗收。
新版案例先經 `experiments/judge_case_audit.py` 檢查工具回合與證據身份，再推論。

| 用途 | 新題數 | 符合人工預期 | 冷啟動 | 單題平均推論 | 重要觀察 |
| --- | ---: | ---: | ---: | ---: | --- |
| Advisor | 9 | 3 | 533 ms | 33.9 ms | 3 條合格案例原始首選均為 APPROVE，但低於 0.8；一條未修正的格式缺陷被正式 APPROVE。 |
| Escalation | 12 | 2 | 869 ms | 27.9 ms | 3 條正常繼續案例均未獲正式 PROCEED；另有一條證據不足案例被正式判為 DEFECT。 |

上述平均數只包含本機推論；冷啟動另列。這些數字是小型人工留出題的
**標籤符合數**，不能解釋為真實任務正確率、路由收益或跨模型優劣。
兩個新題集均未按舊批次的六條／類驗收門檻設計，所以報告的
`dailyUseAccepted` 為 `null`，不可把 `null` 當成通過。

## 判斷

這份本地權重在新版協議題仍未展現可靠的批准與升級判別。
尤其一條明確格式缺陷遭放行，**不能透過調低門檻直接推為日常審核路線**。
Advisor、Escalation 的本地選項保持實驗狀態；產品預設與已完成的普通 LLM
有限驗收不因本批改動。

本批沒有官方 Jev 新題結果，也沒有在 DSH、Codex 或 Hermes 中執行新題的
完整工具循環。要比較後端，須先凍結相同的新案例、題目合同、版本、
派發額度與評價方式，並分開報告原始選擇、門檻後動作及下游任務結果。

## 原始證據

- `advisor-laya-v2.json`：9 條逐題原始 Choice、概率、動作、用量與耗時。
- `escalation-laya-v2.json`：12 條逐題原始 Choice、概率、動作、用量與耗時。
- `../../data/benchmarks/advisor-judge-v2.json` 與
  `../../data/benchmarks/escalation-judge-v2.json`：本批固定題面與標籤。
