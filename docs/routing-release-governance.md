# 版本治理与有限试用

对应 [W10 / #211](https://github.com/AEALab/RefractRouter/issues/211)，承接
[完整计划](whole-task-routing-roadmap-20261029.md)和
[W09 的停止结论](whole-task-development-study.md)。核心自 0.16.34 提供本机管理命令和
可选 Gateway v3。原 Gateway v1 / v2、DSH 默认配置和六种策略的选择规则保持原样。

## 当前结论与启用边界

W09 没有取得可以推荐新路线的独立质量证据，Task、Stage 尚未分别合格，
因此本轮不启动真实 Composite 比较，也不更改产品默认值。构造测试通过仅证明门槛可工作。
省钱且质量有缺口的研究结果不能作为产品资格；不能为展示六策略而强制推荐 Composite。

资格材料须由维护者独立审定，记录来源、工具、宿主、交付标准及完整费用审核的 SHA-256，
声明来源独立、答案隔离、研究评分费另列，关键回退为零。逐题配对数据必须有完整已知费用，
在预先分半的两半都省钱，整体至少省 20%，质量差的单侧 95% 下界不得低于 -3 个百分点。
样本不足、未知判断或费用不全均不能通过。计算复用 W09 的保守置信界。

Composite 另外校验实际内嵌的 Task 与每一种可能初始模型对应的 Stage 配置，
不能借用顶层同名策略的另一组参数。各组件须先单独合格，再以同一组独立题目和费用记录
比较 Composite 对两者的增量；组件候选的质量、费用须逐题等于增量比较中的基线，
共同强基线和两半归属也须一致。对两者都保持质量且整体和两半均有正的增量节省才通过。
新采集的组件结果必须成为新的组件证据，不能只修改增量表格。

审核来源哈希用于固定材料、追查版本，不能验证材料真伪或自动证明语义正确。
本机管理者属于可信边界，拥有写权限的人仍须承担证据审定责任；没有在线自动训练或池修改。
当前资格表只接受单一费用单位；模型 AFP 与非模型 Jev 的 CNY 混合时也拒绝用一列数字掩盖。

## 冻结内容

新 `routing-release-v2` 保存既有 Gateway v2 的完整配置、schema、模型池、价格与计价单位、
provider 地址、非敏感请求选项、凭据环境变量名、认证环境变量名、精确版本声明，
以及实际 Python 源码和资源的 SHA-256。不会读取或保存环境变量中的凭据值。
改变配置、价格、实现或版本即改变资格上下文。`publicationId` 区分人工重新核对后的发布，
新发布不会覆盖旧版本、旧任务或未知预留。影子选择沿用原逻辑，不额外生成比较答卷。

版本文件形状如下。`models` 按配置中的模型 ID 索引，`providers` 必须完整覆盖配置。
精确值须来自真实部署验收，不能把此示意中的夹具值用于真实部署。

```json
{
  "providers": {"fixture": "fixture-provider-v1"},
  "models": {"small": "small-v1", "large": "large-v1"},
  "outputSemantics": {
    "fixture": {
      "parameter": "max_completion_tokens",
      "scope": "answer-and-reasoning-total",
      "sourceSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
  }
}
```

核心 0.16.35 已统一[原生回答、思考和全部输出预算](planning-native-output-budget.md)。
新入口要求模型 `outputBudget` 与版本材料的语义、上游参数一致；回答专用参数保护整个
共享上下文，已知全部输出参数按原生容量保护，不再保留临时 8192 门槛。
未知语义仍不能取得新发布资格；大上限本身不再当作未知，不降低上限来让预检通过。
旧 v1 快照与组件按原规则只读校验，资格记录和费用保持；旧活动试用/默认配置的新任务
须明确重新冻结，不能静默停止旧试用后切换到其他路线。

运行中核对 Chat 回执 `model`、`system_fingerprint` 与冻结值；二者是 provider 声明，
不是权重或价格的密码学证明。缺失、不符或用量未知则保留预留，停止当前执行和该版本
后续新任务试用，标为待复核。实际观测写入任务费用记录及发布事件。
Jev / 本地判别器仍采用各自已有合同；没有因此获得新的真实评审资格。

## 本机管理流程

`refractrouter-release` 不调用模型，也不提供远程发布管理接口。
先准备已验收的 Gateway v2 配置和版本材料，然后显式采用已有配置作为回滚基线：

```bash
refractrouter-release freeze --config /绝对路径/base.json \
  --versions /绝对路径/versions.json --name 基线版本 --output /绝对路径/baseline.json
refractrouter-release init --registry /绝对路径/releases \
  --snapshot /绝对路径/baseline.json --snapshot-sha256 实际文件摘要 \
  --actor 维护者 --gateway-config-output /绝对路径/governed.json
```

命令输出的 `fileSha256` 是原始文件摘要，`releaseSha256` 是规范化发布摘要，两者不要混用。
`freeze` 固定材料并输出 `qualified: false`；已有基线不被重新包装为新研究收益。
初始化采用独立目录，已有目录、丢失数据库或重复初始化均不重置历史。

独立评估通过后再登记新的快照与证据，随后有限显式试用：

```bash
refractrouter-release register --registry /绝对路径/releases \
  --snapshot /绝对路径/candidate.json --snapshot-sha256 实际文件摘要 \
  --evidence /绝对路径/evidence.json --evidence-sha256 实际证据文件摘要 --actor 维护者
refractrouter-release trial --registry /绝对路径/releases --release 发布摘要 \
  --max-tasks 10 --expires 2026-11-01T00:00:00+08:00 --actor 维护者 --explicit-trial
refractrouter-gateway --config /绝对路径/governed.json \
  --runs-dir /绝对路径/governed-runs --preflight
```

证据 schema 为 `routing-release-evidence-v1`，正式字段和反例见
`release_governance.py`、`tests/test_release_governance.py`。
构造验收材料只能放在隔离测试目录；不得将测试夹具的 `kind` 当作真实证据来源。
每次最多 100 个新任务，必须有未来到期时间；次数与到期均不因重启、取消或停止而退款。
试用耗尽后新任务回到原基线，没有无限期自动晋升命令。入站认证必须与基线一致。

v3 仅暴露 `refract/release` 作为冻结配置入口，并不新增第七种策略。
沿用 Chat Completions / Responses 文本与 function 子集，由接入方执行工具。
同一服务中的新任务按试用分配一次，任务内固定发布版本；原有策略仍可按其冻结规则切换模型。

## 停止、回滚与重启

```bash
refractrouter-release stop --registry /绝对路径/releases --actor 维护者 --reason 结束试用
refractrouter-release rollback --registry /绝对路径/releases --actor 维护者 --reason 回到原基线
refractrouter-release invalidate --registry /绝对路径/releases --release 发布摘要 \
  --actor 维护者 --reason provider版本漂移
refractrouter-release history --registry /绝对路径/releases
refractrouter-release inspect --registry /绝对路径/releases --release 发布摘要
```

回滚只影响新任务，在途任务保留原快照并完成费用结算；停止不释放未知用量，不撤销已花费用。
单机发布库只允许一个派发进程。执行根目录与随机标记固定，换空目录不能清除历史。
持久任务所有者及请求摘要阻止同任务重复派发；重启后旧任务只允许查询，不自动恢复或重发。
旧任务遗留工具响应不能由新进程继续执行，应先核对原账本，再由接入方明确建立新任务。
新任务意味着新的费用责任，不能作为故障请求的自动重试。

接入方应提供稳定的 `metadata.refract_session` 与 `metadata.refract_task`。
匿名请求通过完整历史和已知工具 call ID 绑定版本、校验前缀，最终答复后结束任务。
没有稳定任务身份的两次匿名新请求无法识别为同一任务，不保证任意 Agent 跨请求幂等。
显式任务沿用现有结束/结果合同；费用与历史按访问域隔离。

此入口在上游完整回执、身份校验后才向客户端释放文本，SSE 标注为 buffered-release，
不能把客户端首字当成上游实时首 token。旧 v1 / v2 的流式行为不变。
新任务不可派发时 `/readyz` 返回 503，模型列表为空；历史结果仍可通过原结果接口查询，
查询不要求旧 provider 凭据可用。`/healthz` 只证明服务进程存活。

## 只读监控

```bash
refractrouter-release monitor --registry /绝对路径/releases
refractrouter-release monitor --registry /绝对路径/releases \
  --labels /绝对路径/independent-labels.json --labels-sha256 实际文件摘要
```

监控复用原逐调用账本和结果日志，不复制预算或写回资格：

- 完整交付：只接受绑定候选、评分规则、独立来源和原反馈事件的裁定；没有标签、
  未结束、缺失原记录均为 `UNKNOWN`。不将完成 HTTP 传输推定为完整交付。
- 误升级：Advisor / Escalation 复用既有审计；其他模型切换须独立关联前后调用与原决策。
  未裁定为未知，不当作零误升级。
- 返工：仅统计已派发的 `redo`；预留或派发前取消不算执行。
- 预测误差：仅比较同实际候选、同费用单位、同请求范围且完整已知的经验全费用预测。
  过期预测、缓存或费用不全均为未知，不比较单调用价与整任务金额。
- 费用异常：保留未知、未结算、价格身份不符和超预留；CNY / AFP 与参考估值分别列出，
  不相加，不宣称 provider 实际扣减已确认。

原记录或执行回执缺失时，`feeSummaryComplete: false`，汇总金额置为 `null`，
另列可读记录的小计；不能把不可读的未知预留当成零。较早正文的 PASS 也不能越过
后续工具候选，只有最后接受的候选正常终止并有独立裁定时才报告完整交付。

独立标签及升级裁定由可信维护者提供；哈希和事件绑定不替代人工语义审查。
监控不在线训练，不静默变更模型池，不因出现好结果自动恢复待复核版本。

## 验收范围

源码行为回归、完整 Python 套件、TypeScript 类型/构建/契约及最终 wheel / tgz 分开验收。
`scripts/validate_governed_gateway_install.py` 从源码目录外的已安装 wheel 经实际 HTTP
执行 Responses 工具续接、私有思考恢复、中文 emoji SSE、缓存/思考用量、有限试用、
回滚后的版本绑定、身份漂移、未知预留、重启不重发及待复核状态查询。
上游完全是本机固定夹具；其构造正例不证明实际模型兼容、真实策略收益或开放代码任务质量。
安装验收的 DSH headless 模拟入口不等于用户当前网页或设置已升级。

本轮不建设团队集中服务，不重复实现父子共享预算；
[#144](https://github.com/AEALab/RefractRouter/issues/144) 继续负责该能力。
所有治理和监控输出明确 `managed-agent-only`、`parentChildSharedBudgetEnforced: false`。
外层 Agent、子 Agent 或其他独立请求的费用不因此受强制团队总额度约束。
历史已安装文本任务 provider 验收缺口仍由
[#219](https://github.com/AEALab/RefractRouter/issues/219) 单独跟踪。
