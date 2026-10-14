# Composite · 组合

Composite 将 Task 的任务级初选，与 Stage 的后续轨迹判断组合。
它使用自己的模型池与 Judge 设置，不创建 DAG。

<figure class="doc-diagram"><img src="/strategy-composite.svg" alt="Composite 先 Task 初选常用模型，再按 Stage 规则临时切换到接管模型"/><figcaption>常用模型是任务默认档位；接管模型既是临时升级目标，也是 Task 不确定时的备援。</figcaption></figure>

## Task 与 Stage 的交接

1. Task 在任务开始从池中选定常用模型；单候选跳过 Judge。
2. 第一次执行直接使用常用模型，不紧接着追加 Stage Judge。
3. 后续消费新增工具证据，必要时临时切换到指定接管模型。
4. 保持期结束且没有新困难时恢复 Task 选出的常用模型。

指定接管模型也作为 Task 正常不确定时的备援。如果初选已是接管模型，继续使用它，
跳过没有实际切换意义的判断；轨迹明确说明两者相同。

## 两种逐轮模式

| 模式 | 行为 |
| --- | --- |
| 规则 | 默认窗口 3、阈值 0.5、保持 2；新增可信重复失败触发接管 |
| 规则＋Jev／Laya | 实验协作；配置判别间隔、批次上限及降回确认 |

协作模式默认隔两次执行判别，每任务最多四批，降回需要两次明确支持。
判别额度耗尽时记录冻结或保守接管原因，不继续无限追加 Judge。
本地未就绪、推论超时或进程故障按各自停止规则处理。

## 必要设置

独立模型池、Task Judge、指定接管模型、Stage 模式与参数。
接管模型必须满足能力、数据域、历史和预算要求；其角色名不证明更强。

## 费用与轨迹

Task 一次判别与逐轮执行分别计账；纯规则 Stage 不增加 Judge。
只预留本轮选中执行模型的费用，接管余额不足明确停止，不静默降档。
轨迹包含初选、证据、保持、恢复和任何实验 Judge 的原始结果。

### 真实案例

composite-01 任务：先由 Task 阶段的 Judge `glm-5.3-flash` 分类并选出常用模型
（`task-llm-judge` → `composite-task-selected`），执行轮次交回 Stage 规则判断；
工具回执 `ambiguous` 时触发临时接管判断（`composite-ambiguous-base`），由
`deepseek-v4-flash` 接续执行。共 3 次受管调用（1 判别 + 2 执行），费用 1.408 AFP，
首字 3.21 秒，总延迟 7.66 秒。
