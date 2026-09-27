# Escalation 升级策略

## 产品语义

Escalation 从起始模型开始，将尚未交付的正文、推理块和工具调用全部缓冲。Judge 只检查
当前候选是否可以放行；它不重新选择模型，也不执行宿主工具。需要升级时，候选及其中的
工具调用都会被丢弃，指定接管模型使用原始请求和已接受历史继续 DSH 原生 Agent 循环。

每个任务最多接管一次。接管后固定使用强模型，不再调用 Judge，并在轨迹中标记
“接管后未追加审核”。新用户轮次重置状态；工具续接、追加指导和上下文压缩延续当前状态。

| 判别 | 工具过程 | 准备结束任务 |
| --- | --- | --- |
| `PROCEED` | 放行，清零连续停滞 | 放行 |
| `DEFECT` | 立即丢弃并接管 | 立即丢弃并接管 |
| `STALL` | 连续达到门槛后接管，默认两次 | 立即接管 |
| `UNCERTAIN` | 立即接管 | 立即接管 |

认证、传输、用量未知、本地进程崩溃、证据写入失败和非法 Judge 输出都会停止任务。
这些故障不属于模型能力信号，也不会触发接管或自动更换 Judge 后端。

## 判别合同

`escalation-decision-v1` 的输入包括任务和已接受历史、结构化工具证据、当前候选及结束原因。
用户正文、工具参数和候选内容都是待审核材料，不能覆盖系统判别规则。

轻量 LLM 必须返回且只返回以下字段：

```json
{
  "verdict": "PROCEED|DEFECT|STALL|UNCERTAIN",
  "confidence": 0.95,
  "evidenceIds": [],
  "reason": "简短依据"
}
```

Python 严格检查枚举、数值、字段集合和证据引用。候选工具调用 ID 不是已接受证据 ID；
`toolEvidence` 为空时必须返回空数组。置信度低于配置门槛时统一按 `UNCERTAIN` 处理。

本地 Laya-MLX 使用单个 Choice 问题，不要求生成自由文字理由。实际 tokenizer 在派发前检查
完整任务、历史、候选和选项；超出容量时直接接管，不截断。Task 和 Escalation 共用常驻进程，
各自保留问题模板与结果规则。

## 配置与预算

`planningRouting v4` 为 Escalation 保存独立设置：

```json
{
  "schemaVersion": "refractagent-planning-v4",
  "defaultStrategy": "escalation",
  "escalation": {
    "initial": "initial-model",
    "takeover": "takeover-model",
    "judge": {"type": "llm", "modelId": "judge-model"},
    "stallConfirmations": 2,
    "threshold": 0.8,
    "judgeTimeoutMs": 30000,
    "maxJudgeInputBytes": 65536,
    "maxExecutionOutputTokens": 8192,
    "maxJudgeOutputTokens": 1024
  }
}
```

起始与接管模型必须不同。三个角色分别从 DSH 模型目录选择推理等级、数据域及信任策略；
价格、上下文和输出容量由系统资料补齐。旧配置只在用户明确迁移时用 efficient、capable、
classifier 预填，不改变默认策略。

未接管时，每轮在起始模型派发前保护“本次起始执行、一次 Judge、可能的一次接管”所需的
调用名额和各计费单位额度。AFP 与 CNY 分账。实际调用才进入预留和结算，未发生的 Judge 或
接管不会计成消费。接管后只保护一次强模型调用。取消释放尚未派发额度；未知用量保留在途
预留并停止。

## 当前验收结论

确定性测试覆盖放行、缺陷、两次停滞、最终轮停滞、无法判断、容量、非法输出、取消、迟到回执、
预算和 replay。真实 Judge 使用 24 条中英混合冻结案例：

- `deepseek-v4-flash` 关闭思考后匹配 20/24；明确缺陷 6/6 未放行，合格 6/6 放行，
  实际使用 0.52185 AFP，达到本批次有限日常使用门槛。
- 固定 revision 的 `laya-multilingual-mlx` 匹配 5/24，合格 0/6 放行；暖机后平均约 24 ms。
  它的安全回退会将低确定性结果交给强模型，但当前区分力不足，只作为实验后端。
- `glm-5.3-flash` 在当前 Ark Agent Plan 路线下无法关闭思考；默认思考在首次案例中占用
  1023/1024 输出 token 并产生空正文，因此没有通过 1024 token Judge 包络验收。

这份结果只证明固定案例上的回复审核行为，不证明 Escalation 比 Static 更省钱或质量更高。
图片和影片审核仍未验收，不能根据文本结果宣称支持。
