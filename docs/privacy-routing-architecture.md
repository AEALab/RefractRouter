# 隐私约束优先的本地-云混合路由：研究章程与配置 schema

> 建立日期：2026-09-17。状态：M1 草案，待评审冻结。主线跟踪
> [Issue #87](https://github.com/AEALab/RefractRouter/issues/87)，顶层方案见
> [Wiki 页 14](https://github.com/AEALab/RefractRouter/wiki/14-隐私约束优先的本地-云混合路由研究方案)。
> M1 只交付章程与配置合同，不包含模型调用和实现代码。

## 一、研究章程

1. 定位：为小型团队统一路由模型调用。敏感任务（数据不想外传、有保密或信创要求）
   优先在本地部署的特定模型上运行；在用户可接受的质量标准下最小化云端费用，
   再追求最短总体执行时间。
2. 隐私是放置硬约束而不是目标权重：S1 与 unknown 节点只允许本地候选；
   省成本、均衡、质量优先三种模式都不得把敏感节点送出本地。
3. 分级对象是节点的完整输入视图：原始任务、引用材料与全部上游交接字段，
   任一成分命中即整节点 S1；拆分后逐节点重新分级。
4. 全链路敏感面：分类器、规划器、独立评审只要接触 S1 内容就必须本地运行，
   不得成为旁路泄漏点。
5. 实验方法：实验与开发阶段用指定云端公开模型标记 simulated-local 模拟本地模型；
   路由、约束、记账、评审全部真实生效，只有物理位置是模拟的。结论分层报告，
   P4 再换真实本地端点（Ollama / vLLM）复验。
6. 负结果约束：#53 已证明自动 DAG 相对直接回答多耗 60.13% 时间、34.34% AFP。
   拆分必须逐任务论证收益并扣除规划与评审开销，单节点直答始终是合法路线。
7. 付费边界：新方向付费实验不自动继承 Issue #32 的 AFP 授权，每批先冻结协议再申请；
   M1/M2 保持零模型调用。

## 二、词汇表

| 术语 | 含义 |
| --- | --- |
| d(m) | 候选模型 m 的部署域，取 local、cloud 或 simulated-local |
| Π(n) | 节点 n 的隐私分级，取 S1、S2、S3 或 unknown |
| S1 | 命中确定性规则或分类器判定为敏感；仅本地候选 |
| S2 | 中度敏感；v0 不启用脱敏，同样仅本地，后续评估占位符脱敏后的云端路径 |
| S3 | 公开内容；不受部署域约束 |
| unknown | 分类失败、超时或超限等 fail-safe 状态；仅本地候选 |
| simulated-local | 云端公开模型模拟本地模型；路由与约束同 local，运行记录保留部署标签 |
| θ | 自适应质量门槛，由 probe 反馈与独立评审校准，不是静态配置 |
| 外流率 | S1 输入进入 cloud 候选的比例，由运行记录与 model_routes 审计 |

## 三、复用资产

| 现有资产 | 新方向中的角色 |
| --- | --- |
| text-task-plan-v2 DAG 规划与节点契约 | 拆分决策载体；契约新增节点敏感面声明 |
| node-routing-profile-v2 分层选模 | 候选过滤处增加部署域约束 |
| providerConfig 与策略表 | 模型池与三模式配置；新增 deployment 与 privacy 合同 |
| 预算记账与逐调用账本 | 本地按边际成本（0 或申报摊销价）与云端共用账本单位 |
| 独立评审与质量协议 | 质量门槛证据；评审结果回流为 probe 信号 |
| limits（relaxBudget / relaxContext） | 部署层开关；语义不变，隐私约束不受其影响 |
| DSH 插件宿主适配 | 配置界面与本地/云端标识展示，不重复实现路由业务 |

职责边界沿用 AGENTS.md：隐私分级、放置约束求解、费用与时延记账属于 Python 核心；
TypeScript 只处理配置类型、凭证解析、宿主调用边界与结果展示，不得跨层复制业务逻辑。

## 四、配置合同草案（providerConfig v2）

新增字段要求提升 schemaVersion 到 refractagent-providers-v2；v1 内容在 v2 下保持合法
（不写 privacy 字段时行为与现状一致）。字段编译与候选过滤的实现在 M2 落地，
M1 只冻结以下语义。

### 4.1 deployment 字段

provider 行与模型行都可以声明 deployment，取值固定为 local、cloud、simulated-local。

- provider 行声明后，其下模型默认继承；模型行可以显式覆盖。
- 覆盖方向约束：provider 声明 local 时，模型不得覆盖为 cloud；cloud 的 provider
  可通过模型行标记 simulated-local 模拟本地候选。
- local 指真实本地端点（OpenAI 兼容服务，Ollama / vLLM 等）。
- simulated-local 按 local 参与所有路由与放置约束；运行记录保存 deployment 标签，
  全部结论按 simulated-local / real-local 分层报告，不得混称。
- cloud 候选只参与不受约束节点；接触 S1 内容的角色不得选择 cloud 候选。

### 4.2 privacy 字段

| 字段 | 类型 | 默认 | 语义 |
| --- | --- | --- | --- |
| privacy.sensitiveTerms | 字符串数组 | 空 | 团队自定义敏感词表（信创/合规词），命中即 S1 |
| privacy.classifier.enabled | 布尔 | false | 本地分类器开关；关闭时只用确定性规则 |
| privacy.classifier.modelId | 字符串或空 | null | 分类器绑定的模型 ID，必须引用 deployment 为 local 或 simulated-local 的模型行 |
| privacy.maxPromptBytes | 整数 | 1048576 | 节点输入视图字节上限；超限按 unknown 留在本地 |

确定性规则是第一道且零成本：私钥、常见凭证、Token、邮箱、电话、本地绝对路径的
内置正则，加 sensitiveTerms 自定义表。命中即 S1。分类器是第二道，输出
public / sensitive / unknown 与一句理由；分类失败、超时或超限一律 unknown。

标签映射在 v0 固定，不开放配置：S1 仅本地；S2 仅本地（脱敏未启用，不评估云端）；
S3 不受约束；unknown 仅本地。无本地候选时明确失败并记录，不降级放行。

### 4.3 放置约束与角色隔离

- Π(n) 为 S1 或 unknown 时，候选白名单只保留 d(m) ∈ {local, simulated-local}；
  S3 按「质量门槛 → 云端费用最低 → 时延最短」词典序选择。
- 分类器、规划器、独立评审接触 S1 输入时，其调用同样只允许本地与模拟本地候选；
  即使 S1 节点只消费上游摘要，评审看到输出也按接触处理。
- limits 的 relaxBudget / relaxContext 可以放开预算与上下文限制，但不得影响部署域约束。

### 4.4 记账与报告

本地候选边际成本记 0（自有算力）或团队声明的摊销价；订阅型本地服务按声明价。
simulated-local 按声明价格记账并打标 simulated-local。运行记录与 model_routes
新增隐私分级、分级理由与 deployment 标签，供外流率审计与回放。

## 五、完整示例

下方示例声明一个云端候选、一个模拟本地候选、一个评审模型和一个本地分类器。

```json
{
  "schemaVersion": "refractagent-providers-v2",
  "billingUnit": "USD",
  "qualityMin": 80,
  "privacy": {
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

示例说明：local-work 继承 fake-local 的 simulated-local；judge 与 classifier 都部署在
模拟本地端点上。S1 节点只能选 local-work；S3 节点在预算约束下优先 cloud-strong。
评审与分类器接触 S1 内容时同样只走模拟本地候选。

## 六、验收与里程碑边界

M1 评审清单：

- 章程七条与词汇表无歧义，与 Wiki 页 14 一致；
- schema 字段语义完整：deployment、privacy 各字段、标签映射、角色隔离；
- 示例配置是合法 JSON；
- 无新增实现代码，零模型调用；业务逻辑未进入 TypeScript。

后续里程碑：M2 在 Python 实现 P0（分级器、放置约束、模拟本地标记）与零调用单测，
TypeScript 仅新增配置界面与本地/云端标识展示；M3-M6 依次验证分级器、约束路由对照、
probe 回路与真实本地端点，见 Wiki 页 14 与 Issue #87。

## 七、关联文档

- [Wiki 页 14：研究方案](https://github.com/AEALab/RefractRouter/wiki/14-隐私约束优先的本地-云混合路由研究方案)
- [Issue #87：研究主线](https://github.com/AEALab/RefractRouter/issues/87)
- [架构与职责边界](architecture.md)、[自定义 providers 与 models](provider-configuration.md)
