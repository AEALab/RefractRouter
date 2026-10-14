# Escalation · 升级

先由起始模型执行，Judge 检查未交付候选；需要接管时丢弃候选，由指定模型继续原生 Agent 循环。
每任务最多一次接管，接管后锁定该模型，不再调用 Judge。

<figure class="doc-diagram"><img src="/strategy-escalation.svg" alt="Escalation 四种判别与接管路径"/><figcaption>PROCEED 放行；DEFECT、最终轮 STALL 和 UNCERTAIN 立即接管；工具过程 STALL 连续两次后接管。</figcaption></figure>

## 四种判别与动作

| 判别／情况 | 行为 |
| --- | --- |
| PROCEED：合格或正常工具探索 | 放行文本与工具调用，清零连续停滞 |
| DEFECT：明确违反任务或与已有证据矛盾 | 立即丢弃，由接管模型生成 |
| STALL：工具过程疑似停滞 | 默认连续两次后接管；首次可继续 |
| STALL：已经准备结束 | 立即接管，不等待不存在的下一轮 |
| UNCERTAIN／本地已知超容量 | 使用合格接管模型，不换 Judge 后端 |
| 接管已发生 | 使用接管模型并标记“接管后未追加审核” |

正常搜索、合理测试失败、正确澄清和如实说明权限限制不直接判为缺陷或停滞。
认证、传输、未知用量或进程崩溃属于故障，停止调用，不借换模型重试。

## 必要设置

起始模型与接管模型、各自推理等级、独立 Judge、停滞次数与审核期限。
起始与接管配置完全相同不能形成有效接管，预检阻止新版配置启用。

官方 Jev、轻量 LLM 与本地 Laya 使用独立于 Task 的回复判别合同。
选择官方 Jev 后，在渠道设置里核对 OpenRouter 和信任策略；本地当前仍标实验。

## 系统设置示范

打开 **规划路由 → 正在编辑的策略：Escalation**，分别登记起始与接管角色。

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/strategy-escalation-settings.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/strategy-escalation-settings.png" alt="实际 Escalation 设置上半区：DeepSeek Flash 起始模型及数据域"/></a><figcaption>2026-10-14 实际界面：起始角色使用 Flash（Low），数据域与信任策略随角色保存。</figcaption></figure>

<figure class="doc-screenshot"><a href="/screenshots/dsh-20261014/strategy-escalation-judge.png" target="_blank" rel="noopener"><img src="/screenshots/dsh-20261014/strategy-escalation-judge.png" alt="实际 Escalation 设置下半区：V4.1 接管模型、High 推理等级与官方 Jev"/></a><figcaption>同一卡片向下滚动：接管角色使用 V4.1 Flash（High）；接管后固定执行，不追加 Judge。</figcaption></figure>

这里的两个角色有不同的实际模型与参数。Judge 下拉框负责回复判别，接管模型下拉框负责
后续生成，两者不能互换。Jev 获选概率低于动作门槛时，正常不确定按接管规则处理，
认证或传输故障则停止，不借更换模型重试。

适用场景是先尝试低成本答案，只有候选出现明确缺陷或停滞才接管。例如候选声称测试已通过，
但已接受的工具证据显示相同测试失败，应判缺陷并丢弃；候选里尚未放行的工具也不会执行。
接管模型继续原请求与已接受历史，任务内不再降回起始模型。

## 输出与历史

起始候选的正文、推理块和工具调用全部缓冲。
丢弃候选不进入正常历史，其中工具不会执行；接管使用原请求及已接受历史。
接管后的输出允许流式交付，已经释放的文字不能被后来判别悄悄替换。

## 费用与轨迹

接管前保护“起始执行＋一次 Judge＋可能的接管”路径；真正发生的调用分别结算。
未派发额度释放，未知用量保留。接管后每轮只预留一次执行，不追加审核费用。
轨迹显示原始判别、证据、停滞计数、接管原因、接受／丢弃、真实模型及等待时间。
正常不确定也会接管，因此需观察不必要接管带来的费用与延迟。

### 真实案例

escalation-01 任务：起始模型 `deepseek-v4-flash` 生成候选（`escalation-initial`），
任务要求只回复 `ESCALATION_01_OK`，不调用工具，也不添加其他文字。
Judge `glm-5.3-flash` 检查未交付候选后判定 PROCEED 放行（`escalation-proceed`），
未触发接管。共 2 次受管调用（1 执行 + 1 判别），费用 1.170 AFP，首字 2.33 秒，
总延迟 4.75 秒。同批次 24 项全部 PROCEED 放行；DEFECT／STALL 接管路径由确定性夹具验证
（v2 批次曾因 Judge 虚构证据 ID 被严格合同拒绝，修正后 v3 全通过）。
这是[历史 LLM Judge 配置](../planning.md#六策略真实运行案例)；截图中的官方 Jev 是另一个后端示范。
