# 任务结果、反馈与当前任务投影合同

关联 [#203](https://github.com/AEALab/RefractRouter/issues/203)，承接
[#201](https://github.com/AEALab/RefractRouter/issues/201) 的 W02。
本文是既有 Python 业务职责内的实施 ADR，不增加实现语言或宿主工具循环。

## 权威数据与范围

新增 `task-result-v1` 结果视图、`task-outcome-event-v1` 追加事件及
`current-task-projection-v1` 任务投影。逐调用财务账本继续是金额权威；结果日志只保存
调用 ID、候选版本、内容哈希、来源及反馈引用，读取和复用不再次收费。
原配置摘要、各次判别/执行/返工/接管、预留、实际计费状态、计价基础、时间及输入摘要
均可从结果视图追到原始记录。订阅参考估值不冒充现金实扣，未知用量不显示为零消费。

覆盖范围仅为 `managed-agent-only`。宿主外层和 Router 未管理的子 Agent 消费未知，
不得称为完整团队成本。任务类别尚无可靠标签时为 `unknown`；模型 revision 未配置时
标为 `not-pinned`，不能仅凭模型别名声称版本已冻结。
核心接受宿主提供的可选 `parentIdentity`，只记录关系，不合并父子预算。
未提供父身份时明确为 `not-provided`，不从提示、路径或会话名称推断。

真实 `session/agent/turn` 决定任务身份；没有任务身份的标准请求仍独立建账。
Gateway 对访问域与会话采用无歧义编码，既有结果所有者不可覆盖；旧身份碰撞必须拒绝。
升级时检查旧显式身份的原任务文件、运行状态、结果映射及工具续接引用；任一仍存在就
拒绝自动建新预算或重新派发，不安全地迁移时先核对历史，再由调用方显式指定新任务 ID。
标准工具续接继续按已交付 call ID 和已接受历史核对，不按相同提示合并任务。
每个宿主请求及每次模型调用各有 ID；同一请求中的多个判别/执行调用保留各自费用。

## 候选与验收

候选由调用 ID 加精确可交付内容哈希绑定。哈希覆盖正文、原生工具调用和结束状态，
不包含私有思考 replay。修复和返工必须产生新候选身份；正文碰巧相同也不继承旧反馈。

`accepted`、`needs_revision`、`rejected`、`unknown` 分别用于四类来源：

| 来源 | 含义 |
|---|---|
| `user` | 用户接受或要求修改；不等于客观正确 |
| `hidden-evaluation` | 独立隐藏验收；公共反馈接口不能提交此来源 |
| `tool` | 确定性工具要求检查；不代表任务整体正确 |
| `model-review` | 候选评审；选模和进度判别不伪装成正确性评审 |

缺少反馈或当前有效反馈互相矛盾时，该来源汇总为 `unknown`。
反馈保存作者、来源、UTC 时间、`criteriaVersion` 和 `supersedes`；修改意见须显式
替代同作者、同来源、同候选及同验收版本的旧反馈。不同版本/来源保留并列记录。
同事件 ID 的相同重放幂等，矛盾重放拒绝；反馈不会修改策略状态、重新派发或改写费用。

`routerDisposition` 表示核心选择、丢弃或尚未选择；事件中的 `delivery` 是这一内部处置。
它不表示客户端已收妥。未得到客户端的明确收妥证据时，`transportDelivery` 为 `unknown`，
尤其不能把缓冲输出、断线或取消当作成功交付。

## 当前任务投影

新任务第一次普通执行从最后一条直接用户输入建立初始要求；旧对话仍作为有角色和来源的
背景保留。后续直接用户要求追加为指导，初始要求保持。带宿主消息 ID 的矛盾正文拒绝；
无消息 ID 的内容去重只用于指导列表，不用于权限、任务归并或费用复用。

Task 判别不再将所有角色正文拼成一个任务；Stage hybrid 不再把第一条历史 user 当成当前
任务。助手输出标为 `assistant-claim`，工具正文标为 `tool-text`；只有宿主确认的工具状态
属于工具事实。插件环境和技能目录不进入任务正文；标为 `compaction`/`summary` 的宿主
摘要仅作背景，不能成为新要求。压缩专用调用不建立或替换普通任务投影，也不重新分类。
接入方须正确标注摘要来源；未标注且伪装成直接 user 的材料无法由 Router 可靠辨认。
缺少当前要求或超出判别容量时显式报告未知/容量不足，不静默截去要求后声称完整判别。

## 持久化、异常与兼容

本机 SQLite 使用 WAL、完整同步及事务；同任务事件和链头同事务提交。
初始化通过文件锁协调，已有数据库损坏、缺表或丢失时拒绝自动重建历史。
读取采用一致的读快照，不占写锁。批量同步原子提交，避免逐个事件反复读取整条链。
哈希链检测意外损坏，不是防本机管理员篡改的数字签名。

先保存原逐调用财务证据，再同步派生结果事件。同步失败停止派发并保留原费用/未知预留；
重启后可重放已经落盘的记录补齐派生引用，不能恢复模型派发。
已取消的迟到有效回执只补费用，不放行候选。重复回执的既有拒绝规则保持。
历史记录只读取和标为 `legacy-unknown`，不补造过去的验收结论，不改历史原始文件。

## 查询、反馈、导出与删除

默认视图仅含必要身份、摘要及引用，不返回提示、候选正文、工具原文、私有思考或隐藏答案。
原财务证据仍按原本地证据策略保留，不能将删除反馈元数据称为彻底删除输入材料。
目录/数据库采用私有权限；本机 CLI 和 DSH worker 属于当前 OS 用户的信任域。

核心操作为 `outcome`、`outcome-feedback`、`outcome-export`、`outcome-delete`，
均须提供 `runId` 与完全匹配的 `identity`。读取已停止/重启任务不重新执行。
反馈仅接受固定字段及公共 `user` 来源，接入层绑定作者，不能冒充隐藏评审。
删除必须任务已结束且无待结算流程，并提供最近的 `expectedHead`；只删除这一任务的
候选/反馈事件元数据，保留删除墓碑、财务原证及所有费用。删除后不能自动同步恢复。
其他任务/访问域保持；进行中任务、未知在途结算以及过期确认拒绝删除。
新开的 CLI/worker 未加载某任务不表示原进程已退出；原证仍为 `running` 时禁止删除，
即使查询显示待核对，也不能据此放行。崩溃后未有持久化终态的记录须先核对，不能自动清除。

本机示例：将以下结构保存为 `query.json`，使用实际身份和哈希替换示例值。

```json
{"op":"outcome-export","runId":"64位任务哈希","identity":{"session":"会话ID","agent":"代理ID","turn":1}}
```

```bash
refractagent outcome --runs-dir /绝对路径/runs --request-file query.json --output result.json
```

导出新建权限为 `0600` 的文件，不覆盖已有文件。`outcome-feedback` 附带：

```json
{"eventId":"user-feedback-1","actor":"local-user","candidateId":"调用ID","candidateSha256":"64位内容哈希","status":"needs_revision","criteriaVersion":"manual-v1","reasonCode":"missing-evidence","supersedes":null}
```

Gateway 在 Chat Completions 和 Responses 的流式/非流式 HTTP 响应头提供
`X-RefractRouter-Outcome`，模型消息正文不添加结果合同。以该 run ID 调用
`POST /v1/refract/outcomes`，请求体为 `{"operation":"outcome","runId":"..."}`。
反馈、导出和删除使用对应 operation。反馈体省略 `actor`，由 Gateway 固定为
`gateway-user`；不能自报其他来源。使用原 Gateway Bearer 认证和访问域；当前单一服务
token 下的调用者共享该域，这不是逐成员 RBAC。

DSH 通过 Python worker 同样的操作读取，`PlanningController.outcome` 绑定当前宿主
会话与 Agent；仅传 turn、run ID 和操作数据，不在 TypeScript 实现汇总或记账。
已有 `models/list` 宿主桥接接受 `api: task-outcome`，`provider` 为操作 JSON。
这是结果查询接口，不扩大模型协议或增加工具执行。

## 验收与后续

零调用回归覆盖跨任务历史、指导去重、摘要、容量、并发初始化、并发追加、数据库损坏、
来源隔离、冲突反馈、候选修订、原子回滚、成功/取消/迟到回执、未知预留、重启、历史兼容、
私有导出、范围删除、Gateway 四种响应组合、认证，以及 DSH 真实 worker 集成。
完整测试、独立审查、CI 和合并证据记录在 PR 及 #203。
这些检查只证明实现边界，不证明整任务路由质量或省钱收益；后续策略研究由 #205–#211 验证。
