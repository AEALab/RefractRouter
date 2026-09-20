# RefractAgent v4 配置合同

`refractagent-providers-v4` 是自动路由入口的配置版本。它不改变 v1–v3 的历史语义，
也不会自动改写旧配置。完整示例见
[v4 配置示例](../data/schema/refractagent-providers-v4-example.json)。

## 路由目标

v4 使用单一 `objective`，不再接受 `qualityMin` 与 `strategies`：

```json
{
  "qualityMin": 80,
  "primary": "cost",
  "secondary": "latency",
  "dagMode": "auto"
}
```

`qualityMin` 是硬门槛；当前只支持费用优先、时延次优。`dagMode` 可取 `auto`、
`never` 或研究用途的 `force`。DSH 对 v4 只公开 `auto` 模型；v1–v3 继续公开三个历史入口。

## 模型职责与安全

每个模型使用可多选的 `roles`，取值为 `planner`、`worker`、`judge`、`classifier`。
配置至少要有一个 planner、worker 和 judge。部署域必须显式声明，Python 核心负责最终安全、
角色和路由校验；TypeScript 插件只做结构检查和配置透传。

`simulated-local` 仍表示云端调用。真实敏感数据只有在其信任策略允许敏感数据、启用审计，
并且显式设置 `acknowledgeExternalTransmission: true` 时才通过 v4 编译。配置快照会同时记录
该确认、求解使用的模拟边际成本以及模型声明的云端价格。v3 的拒绝规则保持不变。

## 显式迁移

迁移命令不会覆盖来源文件，也不会根据模型名称推断职责：

```bash
refractagent migrate-config-v4 \
  --input providers-v3.json \
  --output providers-v4.json \
  --planner-model-id local-planner
```

迁移规则为 `candidate` → `worker`、`judge` → `judge`，指定的 planner 与
`security.classifier.modelId` 分别追加对应职责。输出会经过 Python 核心完整校验。

## 当前开发边界

配置编译、显式迁移、DSH 单一入口合同和安全约束下的零调用 direct-or-DAG 估算已经实现；
估算合同与审计字段见 [v4 两级自动路由选择器](automatic-routing-v4.md)。运行期逐阶段重新分级、
实际账本回填、预测误差校准和结构化设置表单仍在 Issue #116 的后续实施切片完成。v4 已允许
`preflight` 与 `demo` 通过真实 Python/DSH 入口验证配置、职责池和直接路线，`live` 仍在凭证解析
及模型调用前 fail closed；在完整自动选路接入前，不应作为生产付费执行配置发布。
