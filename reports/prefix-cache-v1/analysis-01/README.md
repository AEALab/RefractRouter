# 前缀缓存开发诊断

冻结摘要：`1041103ba252978bad1574f029729d1629b6b6487d4cf9196934ee438abc61c9`。原始产物摘要核对通过。

实际 44 次调用，账本 44 条；按冻结价格计算 105.54515 AFP，未知用量仍预留 0.00000 AFP。

输入 66989，输出 158597，已报告缓存 6144 token；0 次已结算调用没有可确认的缓存字段。

## 接口探针

| 模型 | 布局 | 阶段 | 结束状态 | 缓存 token | 输入 / 输出 | 请求秒数 | AFP |
|---|---|---|---|---:|---:|---:|---:|
| deepseek-v4-flash | legacy | 首次并发 0 | length | 0 | 1431 / 8192 | 169.524 | 0.48115 |
| deepseek-v4-flash | legacy | 首次并发 1 | length | 0 | 1431 / 8192 | 82.979 | 0.48115 |
| deepseek-v4-flash | legacy | 首次顺序 2 | stop | 0 | 1376 / 2544 | 46.288 | 0.19600 |
| deepseek-v4-flash | legacy | 重复前缀 3 | length | 0 | 1376 / 8192 | 164.557 | 0.47840 |
| deepseek-v4-flash | stable-v1 | 首次并发 0 | stop | 0 | 1431 / 7740 | 147.204 | 0.45855 |
| deepseek-v4-flash | stable-v1 | 首次并发 1 | stop | 0 | 1431 / 5398 | 58.981 | 0.34145 |
| deepseek-v4-flash | stable-v1 | 首次顺序 2 | stop | 0 | 1376 / 6006 | 44.934 | 0.36910 |
| deepseek-v4-flash | stable-v1 | 重复前缀 3 | stop | 0 | 1376 / 2998 | 56.405 | 0.21870 |
| minimax-m3 | stable-v1 | 首次并发 0 | stop | 0 | 1438 / 2600 | 14.854 | 1.00950 |
| minimax-m3 | stable-v1 | 首次并发 1 | stop | 0 | 1438 / 1706 | 12.230 | 0.78600 |
| minimax-m3 | stable-v1 | 首次顺序 2 | stop | 0 | 1378 / 1714 | 11.406 | 0.77300 |
| minimax-m3 | stable-v1 | 重复前缀 3 | stop | 0 | 1378 / 1716 | 8.812 | 0.77350 |
| minimax-m3 | legacy | 首次并发 0 | stop | 0 | 1437 / 2191 | 11.798 | 0.90700 |
| minimax-m3 | legacy | 首次并发 1 | stop | 0 | 1437 / 2112 | 9.915 | 0.88725 |
| minimax-m3 | legacy | 首次顺序 2 | stop | 0 | 1377 / 1847 | 14.859 | 0.80600 |
| minimax-m3 | legacy | 重复前缀 3 | stop | 0 | 1377 / 1871 | 9.026 | 0.81200 |
| deepseek-v4-pro | legacy | 首次并发 0 | stop | 0 | 1431 / 7537 | 158.231 | 4.93240 |
| deepseek-v4-pro | legacy | 首次并发 1 | stop | 0 | 1431 / 4954 | 104.594 | 3.51175 |
| deepseek-v4-pro | legacy | 首次顺序 2 | stop | 0 | 1376 / 4733 | 97.444 | 3.35995 |
| deepseek-v4-pro | legacy | 重复前缀 3 | stop | 0 | 1376 / 4512 | 99.445 | 3.23840 |
| deepseek-v4-pro | stable-v1 | 首次并发 0 | stop | 1024 | 1431 / 6955 | 144.715 | 4.61230 |
| deepseek-v4-pro | stable-v1 | 首次并发 1 | stop | 0 | 1431 / 6509 | 137.831 | 4.36700 |
| deepseek-v4-pro | stable-v1 | 首次顺序 2 | stop | 0 | 1376 / 3257 | 61.816 | 2.54815 |
| deepseek-v4-pro | stable-v1 | 重复前缀 3 | stop | 1024 | 1376 / 3098 | 62.179 | 2.46070 |
| evaluation-kimi-k3 | stable-v1 | 首次并发 0 | stop | 0 | 1346 / 1909 | 61.452 | 3.25500 |
| evaluation-kimi-k3 | stable-v1 | 首次并发 1 | stop | 0 | 1346 / 3165 | 102.691 | 4.51100 |
| evaluation-kimi-k3 | stable-v1 | 首次顺序 2 | stop | 0 | 1297 / 3268 | 105.280 | 4.56500 |
| evaluation-kimi-k3 | stable-v1 | 重复前缀 3 | stop | 0 | 1297 / 2419 | 83.358 | 3.71600 |
| evaluation-kimi-k3 | legacy | 首次并发 0 | stop | 0 | 1345 / 1500 | 49.471 | 2.84500 |
| evaluation-kimi-k3 | legacy | 首次并发 1 | stop | 0 | 1345 / 4416 | 149.722 | 5.76100 |
| evaluation-kimi-k3 | legacy | 首次顺序 2 | stop | 0 | 1296 / 1244 | 40.468 | 2.54000 |
| evaluation-kimi-k3 | legacy | 重复前缀 3 | stop | 0 | 1296 / 2324 | 71.706 | 3.62000 |

## 应用对照

| 路线 | 状态 | 端到端秒数 | 生产 AFP | 评审 AFP | 总 AFP | 调用数 |
|---|---|---:|---:|---:|---:|---:|
| direct-legacy | completed | 101.268 | 2.85450 | 3.24500 | 6.09950 | 2 |
| direct-stable-v1 | completed | 101.352 | 2.55695 | 3.88000 | 6.43695 | 2 |
| same-dag-stable-v1 | completed | 142.598 | 7.29135 | 3.12800 | 10.41935 | 4 |
| same-dag-legacy | completed | 189.631 | 9.98195 | 2.98500 | 12.96695 | 4 |

## 解释边界

所有冷状态未确认；不能清空服务端缓存，且跨布局/之前请求的污染不能排除。
首次并发与首次顺序使用不同开发任务子集，不能直接作并发性能对照。
每应用路线只有一次；记录随机性、输出长度及模型服务负载共同影响的观测，不能证明稳定提速。
探针不是质量验收；应用保留原模型评审，但仍缺独立真人复核，不能声称得到 Pareto 解。
TTFT 全部未知；缓存 token 不等于 AFP 折扣，AFP 是 token 与冻结系数计算值，并未核对账号控制台逐笔扣减。
冻结固定图无规划调用；自动规划与选择性材料精简收益仍待另做消融。
