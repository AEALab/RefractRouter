# 隐私感知的节点放置：可选约束与配置 schema

> 建立日期：2026-09-17。状态：草案，待评审冻结。跟踪
> [Issue #87](https://github.com/AEALab/RefractRouter/issues/87)，顶层说明见
> [Wiki 页 14](https://github.com/AEALab/RefractRouter/wiki/14-隐私感知的节点放置与本地模型约束)。
> 本文档只交付配置合同与约束语义，不包含实现代码和模型调用。

## 一、定位：主线内的一个可选约束

RefractRouter 的研究主线不变，仍是**任务分解感知的模型路由**：按任务内容判断是否拆分、
如何拆成 DAG 节点，在用户可接受的质量下最小化模型调用总费用，其次缩短端到端时间。
隐私感知放置是这条主线内新增的一个**可选节点级约束**，默认关闭。

它与既有费用目标同向而非对立。把特定模型声明为本地部署（边际成本记 0 或团队申报的
摊销价）后，敏感节点优先落到这些零成本候选上，既满足数据不出域，也直接降低总费用。
因此这是在原有目标函数上增加一个候选过滤维度，不是把隐私变成新的首要目标。

启用与关闭的行为边界：

- **未配置 privacy 字段（默认）**：路由行为与现状完全一致，只按质量门槛、费用、
  时延选模；deployment 标签仍可声明，仅用于记账与展示。
- **启用 privacy 后**：分级命中的节点在选模时收窄候选集到本地部署模型；
  其余节点仍按原目标排序。

## 二、目标函数与约束的关系

输入：任务 T；模型池 M，候选 m 带质量、成本、时延预测与部署域 d(m)；
可选的隐私分级策略 Π。

决策仍是三步：是否拆分与如何拆分（含单节点直答）；每个节点的类型、难度与风险估计；
为每个节点联合选择模型与推理档位。

目标保持原主线定义，词典序不做加权折算：质量预测满足门槛 θ；在此之上最小化
调用总费用；再最小化端到端时延。启用隐私约束时，它作用在**候选过滤**这一层：
被判定为敏感的节点，其候选集先收窄为本地部署模型，再在收窄后的集合内按同一目标排序。

这意味着：隐私约束不改变目标函数，只改变每个节点的可行候选集。关闭时可行集就是全集。

失败语义保守：启用后若分级失败、超时或输入超限，该节点按未知处理并留在本地候选；
若此时没有任何本地候选可用，明确失败并记录，不静默放行到云端。

## 三、与三模式的关系

省成本、均衡、质量优先三种模式保留原语义，决定门槛与候选排序偏好。
隐私约束启用后对三种模式一致生效，任何模式都不会把敏感节点送出本地。
关闭时三种模式行为与现状相同。

## 四、词汇表

| 术语 | 含义 |
| --- | --- |
| d(m) | 候选模型 m 的部署域，取 local、cloud 或 simulated-local |
| Π(n) | 节点 n 的隐私分级，取 S1、S2、S3 或 unknown；仅在启用时计算 |
| S1 | 命中确定性规则或分类器判定为敏感；收窄到本地候选 |
| S2 | 中度敏感；v0 不启用脱敏，同样收窄到本地候选 |
| S3 | 公开内容；候选集不收窄 |
| unknown | 分级失败、超时或超限的 fail-safe 状态；收窄到本地候选 |
| simulated-local | 云端公开模型模拟本地模型；参与约束同 local，运行记录保留真实部署标签 |
| θ | 质量门槛，后续由 probe 反馈与独立评审校准 |
| 外流率 | 启用约束后，敏感输入进入 cloud 候选的比例，由运行记录与 model_routes 审计 |

## 五、复用资产

| 现有资产 | 在本约束中的角色 |
| --- | --- |
| text-task-plan-v2 DAG 规划与节点契约 | 拆分决策载体；启用时契约承载节点敏感面声明 |
| node-routing-profile-v2 分层选模 | 候选过滤处增加可选的部署域收窄 |
| providerConfig 与策略表 | 模型池与三模式配置；新增 deployment 与可选 privacy 合同 |
| 预算记账与逐调用账本 | 本地按边际成本（0 或申报摊销价）与云端共用账本单位 |
| 独立评审与质量协议 | 质量门槛证据；评审结果后续回流为 probe 信号 |
| limits（relaxBudget / relaxContext） | 部署层开关；语义不变，启用的隐私约束不受其放宽 |
| DSH 插件宿主适配 | 配置界面与本地/云端标识展示，不重复实现路由业务 |

职责边界沿用 AGENTS.md：分级、候选过滤、费用与时延记账属于 Python 核心；
TypeScript 只处理配置类型、凭证解析、宿主调用边界与结果展示，不得跨层复制业务逻辑。

## 六、配置合同草案

新增字段提升 schemaVersion 到 refractagent-providers-v2。v1 配置在 v2 下保持合法：
不写 privacy 字段时路由行为与现状一致。字段编译与候选过滤的实现在后续里程碑落地，
本文档只冻结语义。

### 6.1 deployment 字段（独立于 privacy）

provider 行与模型行都可以声明 deployment，取值 local、cloud、simulated-local，
默认 cloud。该字段独立可用：即使不启用 privacy，也可用于成本口径与运行记录标注。
该字段编译进 providerConfig 的应用模型规格（`ApplicationModelSpec`），不写入
`schemas.ModelSpec`，也不写入 `data/model-manifests/` 下的模型清单：清单参与 K3 历史
基线的冻结配置摘要与恢复校验，新增字段会使已登记的成功基线无法恢复。

- provider 行声明后其下模型默认继承；模型行可以显式覆盖。
- 覆盖方向约束：provider 声明 local 时，模型不得覆盖为 cloud；cloud 的 provider
  可通过模型行标记 simulated-local 作为模拟本地候选。
- local 指真实本地端点（OpenAI 兼容服务，Ollama / vLLM 等）。
- simulated-local 在约束求解与记账中按 local 处理，边际成本一律记 0（口径见 6.4）；
  运行记录保存真实标签，结论按 simulated-local 与 real-local 分层报告，不得混称。

### 6.2 privacy 字段（可选，默认关闭）

| 字段 | 类型 | 默认 | 语义 |
| --- | --- | --- | --- |
| privacy | 对象或缺省 | 缺省 | 整个字段缺省时约束关闭，路由行为与现状一致 |
| privacy.enabled | 布尔 | false | 显式开关；写了 privacy 但未置 true 时仍然关闭 |
| privacy.sensitiveTerms | 字符串数组 | 空 | 团队自定义敏感词表（信创、合规词），命中即 S1 |
| privacy.classifier.enabled | 布尔 | false | 本地分类器开关；关闭时只用确定性规则 |
| privacy.classifier.modelId | 字符串或空 | null | 分类器绑定的模型 ID，必须引用 deployment 为 local 或 simulated-local 的模型行 |
| privacy.maxPromptBytes | 整数 | 1048576 | 节点输入视图字节上限；超限按 unknown 收窄到本地 |

启用后分级分两道。确定性规则是第一道且零成本：私钥、常见凭证、Token、邮箱、电话、
本地绝对路径的内置正则，加 sensitiveTerms 自定义表，命中即 S1。分类器是第二道，
输出 public / sensitive / unknown 与一句理由；分类失败、超时或超限一律 unknown。

分级对象是节点的完整输入视图：原始任务、引用材料与全部上游交接字段，任一成分命中
即整节点 S1。拆分会改变节点的信息含量，因此拆分后逐节点重新分级。

标签映射在 v0 固定，不开放配置：S1 与 S2 收窄到本地候选；S3 不收窄；unknown 收窄到
本地候选。无可用本地候选时明确失败并记录。

### 6.3 候选过滤与角色隔离

- Π(n) 为 S1、S2 或 unknown 时，候选白名单只保留 d(m) ∈ {local, simulated-local}，
  再在其中按「质量门槛 → 费用最低 → 时延最短」选择；S3 在全集上按同一顺序选择。
- 分类器、规划器、独立评审接触敏感输入时，其调用同样只允许本地与模拟本地候选。
  评审能看到节点输出，因此按接触处理。
- limits 的 relaxBudget / relaxContext 放开预算与上下文限制，但不放宽已启用的部署域约束。

### 6.4 记账与报告

本地候选与 simulated-local 在求解与记账中一律按边际成本 0 计：前者是自持算力，落地后
不再产生按次费用；后者的物理位置在实验阶段是模拟的，按 0 计得到的是「假设已本地化」
的口径。申报价不丢弃，保留在该模型声明的 declared_pricing 里（含 cachedInputPer1k），
供敏感性分析与实跑成本重算使用。

由此产生两个不得混用的数字，报告必须同时给出：

- 研究口径：按假设本地部署求解与记账，本地与 simulated-local 记 0。主指标
  AFP per accepted task 与路线比较一律用这个口径。
- 实跑口径：当次实验真实消耗。用 declared_pricing 与实际 token 重算，作为实验
  成本与账户账单的留痕；它与研究口径的差额就是本地化假设带来的节省额。

结论必须标注「simulated-local 假设」：0 成本来自部署假设，不是当次运行的真实账单；
真实本地端点的时延、吞吐与质量特性尚未量化，切换真实端点后两个口径都要重测。
运行记录与 model_routes 在启用时新增分级、分级理由与 deployment 标签，供外流率审计
与回放；关闭时仅记录 deployment 标签。

## 七、完整示例

下方示例启用约束，声明一个云端候选、一个模拟本地候选、一个评审模型和一个本地分类器。
删除 privacy 字段即可退回默认行为。

```json
{
  "schemaVersion": "refractagent-providers-v2",
  "billingUnit": "USD",
  "qualityMin": 80,
  "privacy": {
    "enabled": true,
    "sensitiveTerms": ["合同金额", "客户名单"],
    "classifier": {"enabled": true, "modelId": "classifier"},
    "maxPromptBytes": 1048576
  },
  "providers": [
    {
      "id": "ark",
      "type": "ark-agent-plan",
      "credentialEnv": "CODEX_ARK_API_KEY",
      "deployment": "cloud"
    },
    {
      "id": "fake-local",
      "type": "openai-compatible",
      "baseUrl": "https://simulated-local.example/v1",
      "credentialEnv": "SIM_LOCAL_KEY",
      "deployment": "simulated-local"
    }
  ],
  "models": [
    {
      "id": "cloud-strong",
      "provider": "ark",
      "model": "CLOUD_STRONG_MODEL",
      "role": "candidate",
      "contextWindow": 131072,
      "maxOutputTokens": 8192,
      "pricing": {"unit": "USD", "inputPer1k": 0.01, "outputPer1k": 0.02},
      "routing": {"quality": 92, "latencyMs": 8000}
    },
    {
      "id": "local-work",
      "provider": "fake-local",
      "model": "LOCAL_WORK_MODEL",
      "role": "candidate",
      "contextWindow": 32768,
      "maxOutputTokens": 4096,
      "pricing": {"unit": "USD", "inputPer1k": 0, "outputPer1k": 0},
      "routing": {"quality": 82, "latencyMs": 30000}
    },
    {
      "id": "judge",
      "provider": "fake-local",
      "model": "LOCAL_JUDGE_MODEL",
      "role": "judge",
      "pricing": {"unit": "USD", "inputPer1k": 0, "outputPer1k": 0}
    },
    {
      "id": "classifier",
      "provider": "fake-local",
      "model": "LOCAL_CLASSIFIER_MODEL",
      "role": "candidate",
      "pricing": {"unit": "USD", "inputPer1k": 0, "outputPer1k": 0}
    }
  ]
}
```

local-work 继承 fake-local 的 simulated-local。敏感节点只能选 local-work；公开节点在
质量门槛下按费用与时延在全集中选择，通常落到 cloud-strong。评审与分类器接触敏感内容时
同样只走模拟本地候选。

## 八、实验方法：模拟本地模型

开发与实验阶段用指定云端公开模型标记 simulated-local 模拟本地模型。分级、候选过滤、
角色隔离、运行期守门与质量评审全部真实生效，只有物理位置与按次费用是假设的。这样在
没有本地算力时也能验证机制与收益假设；切换真实本地端点只改 provider 配置，路由代码
不变。

计价按 6.4 的双口径执行：求解与主指标用「本地记 0」的研究口径，实跑成本用
declared_pricing 另算。结论必须分层报告，simulated-local 与 real-local 不得混称；
模拟本地的时延与成本特性与真实本地存在偏差，须在真实端点阶段量化。

## 九、优先级：主线在前

本约束的实验价值依赖主线先把基线立住：

1. 判断「敏感节点改用本地模型」是否可接受，前提是先有 Issue #52 的质量门槛与评审协议；
2. Issue #76 把主指标定为 AFP per accepted task。约束启用后费用下降有多少来自本地
   零成本、多少来自主线的拆分与选模，必须先有关闭组基线才能分开归因；
3. Issue #53 的负结果（自动 DAG 多耗 60.13% 时间、34.34% AFP）尚未被推翻。
   在拆分收益未证实前扩张隐私实验，会把两类不确定性混在一起。

排期：主线 #52 → #53 → #76 / #72 → #54 先行；本约束的验证在其后。
零调用的配置与机制实现（下表 A1、A2）不消耗预算也不依赖质量门槛，可与主线并行推进。

| 编号 | 交付 | 调用 | 依赖 |
| --- | --- | --- | --- |
| A1 | 约束定位与本文档冻结；deployment 与可选 privacy schema（已完成） | 零调用 | 无 |
| A2 | 分级器 + 候选过滤 + 模拟本地标记；关闭路径回归（已完成，见 6.4 双口径） | 零调用 | 无 |
| A3 | 分级器验证（构造 + 脱敏真实样本标注集；已完成） | 分级器本地调用 | A2 |
| A4 | 开关对照（关闭基线 / all-local / all-cloud / 启用 / 直答） | 付费，另获批 | #52、#53、#76、A3 |
| A5 | probe 回路 + OpenViking 记忆接入 | 离线回放优先 | A4 |
| A6 | 真实本地端点（Ollama / vLLM）替换模拟 | 本地 + 付费 | A4 |

## 十、验证边界

#53 已证明自动 DAG 相对直接回答曾多耗 60.13% 时间、34.34% AFP。拆分收益必须逐任务
论证并扣除规划与评审开销，单节点直答始终是合法路线。这条约束对启用与关闭隐私约束的
两种情况同样成立。

付费实验不自动继承 Issue #32 的 AFP 授权，每批先冻结协议再申请预算。配置与约束语义的
验证保持零模型调用。A4 是唯一的付费对照批次。

对照实验需要同时覆盖关闭与启用两种配置：关闭时验证路由结果与现状一致；启用时比较
质量、费用、时延变化与外流率，确认约束带来的代价可量化。

## 十·五、分级器验证结果（A3）

A3 以零网络、零付费调用完成确定性第一道的验证。标注集冻结在
data/privacy-classifier/ 目录：constructed-samples-v1.json（构造样本 58 条）与
desensitized-real-samples-v1.json（脱敏真实样本 15 条，全部敏感值替换为保留占位符，
原始真实值不进入仓库）。验证入口为 experiments/validate_privacy_classifier.py，
冻结证据在 reports/privacy-classifier-v1/validation-01/。

严格门禁（只统计非 known_issue 样本）：S1 与 S3 的精确率、召回率均为 100%，
70 条干净样本零误判、零漏报。验证驱动的两处规则修复：

- credential-assignment 增加 JSON 引号键名支持，"api_key":"value" 形态不再漏报；
- 新增 credential-assignment-zh，覆盖「密码 / 口令 / 密钥」中文键名赋值。

已文档化的保守代价（known_issue，不进入严格门禁，代价由 A4 开关对照量化）：

- phone-cn 对形态相同的订单流水号误报；宁松勿漏，误报代价是本地改派而非外流；
- 自定义敏感词按子串命中，保守误报；语义边界留待分类器第二道；
- 含空格的秘密值暂不捕获（召回缺口），后续评估值字符集扩展；
- S2 在 v0 不产出；第二道 ML 分类器只验证了调用合同与 fail-safe（本地替身），
  真实模型质量留待 A6 真实本地端点验证。

## 十一、关联文档

- [Issue #87](https://github.com/AEALab/RefractRouter/issues/87)：本约束的跟踪 Issue
- 主线 [Issue #50](https://github.com/AEALab/RefractRouter/issues/50)；
  前置 [#52](https://github.com/AEALab/RefractRouter/issues/52)、
  [#53](https://github.com/AEALab/RefractRouter/issues/53)、
  [#76](https://github.com/AEALab/RefractRouter/issues/76)
- [Wiki 页 14：隐私感知的节点放置与本地模型约束](https://github.com/AEALab/RefractRouter/wiki/14-隐私感知的节点放置与本地模型约束)
- [架构与职责边界](architecture.md)、[自定义 providers 与 models](provider-configuration.md)
