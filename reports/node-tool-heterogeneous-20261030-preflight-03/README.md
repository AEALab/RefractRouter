# 六臂异构选模最终零调用预检

状态：通过工程预检；真实模型调用 **0**，真实AFP **0**。本目录不证明任务质量收益。
协议摘要：`00546aa89a857a225e899c36f197c0b5b3d2e911eec65ac3b8fa6629eeffa5f8`。

## 已完成

- Python研究profile独立绑定主模型与专家；专家不改变主循环选模状态，继续共用父账本。
- 18个构造任务及私有参考冻结：6开发、12候选留出、6个相关来源族。
- 字段、类型、集合、替代支持来源及正文语义三态规则冻结；独立材料/输出审查待完成。
- 72个提示开发与216个比较个案逐项静态检查，新增资格探测2项与共享规划36项。
- 真实DSH宿主四组合演练：direct各1次，node各7次（3专家）；同图DAG两臂各3节点，规划序列化1次。
- 23份实际客户端序列化正文由本地夹具截获并归档；温度0、完整384000输出、思考及top_p未被研究改写。
- 模型与父账本审计通过；未发现实际环境凭证值进入新证据。
- 最终`uv run pytest` **2171项通过**，严格TypeScript检查通过。

调用模型清单：L=`deepseek-v4-flash`，H=`deepseek-v4-pro`，统一`/api/plan/v3`。
官方2026-10-30输入/输出每千token系数为L **0.05 AFP**、H **0.55 AFP**；
两者登记上下文1024000、完整输出384000。本轮实际物理版本及账号可用性尚未探测。

## 待批准范围与预算

最多 **974次**：资格2、开发72、direct两臂各36、node两臂各252、DAG执行两臂各144、共享规划36。
完整容量、保守输入包络全部耗尽的极端上界 **145454.0796 AFP**，取整可为145455 AFP。
冻结件列出的运行硬上限建议为 **6000 AFP**，不是实际消费预测，也不保证极端情况下整批完成。
不能为了压低该理论上界减小模型输出。较小硬上限只能通过完整预留、结算释放余额推进。
本轮没有付费批准，也没有付费执行模式，不承接历史286 AFP授权。

## 证据与复现

- [协议及源码哈希](frozen.json)
- [预检结果](rehearsal/preflight.json)
- [逐请求与账本审计](../node-tool-heterogeneous-20261030-verification/audit.json)
- [完整测试日志](../node-tool-heterogeneous-20261030-verification/pytest.log)
- [TypeScript日志](../node-tool-heterogeneous-20261030-verification/typecheck.log)
- [详细研究方案](../../docs/node-tool-heterogeneous-study.md)
- [宿主编排与Router边界](../../docs/host-orchestration-and-model-routing.md)

源码没有变化时，可在仓库根目录校验冻结件。新演练必须使用新的输出目录：

```bash
uv run python experiments/preflight_heterogeneous_study.py \
  --output-dir reports/新的预检目录 --rehearse \
  --dsh-node-modules /已安装DSH目录/node_modules
```

模拟图是工程夹具，真实共享图将在后续已授权规划调用后绑定；开发赢家也尚未产生。
主模型委派、工具权限和子任务生命周期属于宿主；本研究没有更改标准模型API或Codex配置。
