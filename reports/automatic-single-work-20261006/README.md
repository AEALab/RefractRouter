# 自动路由单项工作判别有限验收

## 验收范围

使用用户原有 DSH `web` profile、新版插件 0.29.16、已安装 Python 核心 0.15.19，
对一条受限工具任务进行真实调用：先用 Bash 执行 `printf 7`，再只依据标准输出回答数字。
未修改用户的 provider、凭证、会话或单任务预算。Jev 使用现有 OpenRouter 路线。

本项验证 DSH 自动路由。Codex 标准模型接口不进入 DAG，未将 DSH 的结果推称为
Codex 自动拆分验收；Hermes 不属于当前验收范围。

## 新旧运行记录

| 项目 | 旧合同 v1 | 新合同 v2 |
| --- | ---: | ---: |
| Jev 结果 | `UNKNOWN` | `SINGLE` |
| 最终路线 | 进入规划，规划器返回单节点 | 直接执行，不派发 planner |
| 规划实际费用 | 4.1850 AFP | 0 AFP |
| 受管模型已知合计 | 23.5908 AFP | 19.3563 AFP |
| Jev 已结算 | 0.00016745 CNY | 0.00020485 CNY |
| Router 墙钟耗时 | 13.197 秒 | 9.461 秒 |
| 工具及结果 | Bash 确认执行，回答 `7` | Bash 确认执行，回答 `7` |
| 最终审核 | 通过 | 通过 |

新版 Jev 三项原始 `Noul` 值分别为：前步依赖 `0.19`、可独立拆分 `0.08`、
单项工作 `0.87`。Router 的单项判定规则合成强度为 `0.81`；这是三项信号的保守组合值，
不是 Jev 的 Choice confidence，也不是任务成功率。

两次记录分别位于本机 `.refractagent/runs/20261005T154256Z-dab87508873a/` 和
`.refractagent/runs/20261005T163802Z-46a4aa100310/`，其中 `summary.json`、
`result.json` 和调用账本保留原样。新版运行确认 `route_comparison` 为空，规划费用为零；
宿主回执含 `bash` 调用及正常退出状态。UI 截图另保留在本机临时验收文件中。

这只是同一任务的前后观测，不能把 4.2345 AFP 与 3.736 秒差额解释为普遍收益。
Jev 第三问略增加了现金判别费用，AFP 与 CNY 分账，没有做货币折算。

## 无网络验证

- `uv run --no-sync pytest -q`：1603 通过；另外 5 个插件子测试通过。
- `npm run --prefix validation/dsh/plugin typecheck`：通过。
- `npm run --prefix validation/dsh/plugin build`：通过。
- 构建后 `npm run --prefix validation/dsh/plugin test:contracts`：188 通过。

测试覆盖三问互相矛盾时保持 `UNKNOWN`、旧合同证据读取、单项工具任务跳过规划、
工具权限未开时仍阻断，以及最终审核仍执行。完整测试需要本机回环端口；沙箱禁止
绑定回环时出现的权限错误不属于产品行为失败，允许本机端口后完整通过。
