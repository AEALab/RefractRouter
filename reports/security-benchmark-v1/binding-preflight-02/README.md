# #112 真实绑定与零调用预算冻结

- 协议摘要：`8a1c3ecad58f7189c7f3ec21c4943d5e4773d2db3794c7d6cb06a86e0b95389b`
- 绑定摘要：`40ecaf7d80b1fc6ab4a108f86610860bd4ccd64a2506f0383434f62534a92942`
- 生产调用：28；评审调用：20；合计：48
- 本次授权调用上限：48；协议硬上限：64
- 已知绑定执行用量：7.452000 AFP
- 未知执行用量角色：local-judge, local-worker, trusted-strong
- 原厂公开参考价未解析角色：external-cheap, external-strong
- AFP 是实际执行路线的订阅资源单位；现金成本与原厂公开价格等价量均保持 `null`。
- 自动 HTTP 重试、节点回退与恢复调用均为 0。
- 真实模型调用：0；付费执行授权：否；实时执行就绪：否。

## 阻断条件

- BINDING_MISSING：当前 DSH 目录没有独立于生产模型的真实本地评审模型。
- BINDING_MISSING：当前 DSH 目录没有已验证的真实本地执行模型、推理引擎与模型制品摘要。
- TRUST_POLICY_INCOMPLETE：glm-5.3 只有开发期 DSH 声明，尚无可提交的生产信任、驻留与审计证明。
- MODEL_VERSION_UNRESOLVED：glm-5.3 是文档模型名，尚未确认是否可固定到不可变版本。
- PAID_EXECUTION_UNAUTHORIZED：开发批次尚未取得明确调用与预算授权。
