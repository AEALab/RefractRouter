# MoA 输出评审定向补审（moa-output-01-retry）

研究负责人授权的显式例外：对 moa-output-01 中 status 不是 reviewed 的评审调用做定向补审，输入、策略与评审者完全不变。

- 原失败调用原样保留在每条记录的 targeted_review.replaced_failed_calls；
- 补审成功的新行替换进 primary/escalation，并用同一 aggregate 重算共识；
- 再次失败的调用保持原记录不动，如实保留 pending。
