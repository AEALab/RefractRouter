# DSH 连接阻断原因与处理

2026 年 9 月 8 日通过同机、不同执行权限的对照检查，确认此次连接阻断来自普通沙箱的
外部网络限制。排障请求没有携带密钥，也没有访问模型生成接口。

## 证据

| 检查 | 普通沙箱 | 扩展权限 |
| --- | --- | --- |
| Ark 域名解析 | Python 返回 `gaierror`；Node 返回 `ENOTFOUND` | 成功 |
| 公网 IP TCP 连接 | Python 返回 `Operation not permitted`；Node 返回 `EPERM` | HTTPS 检查包含了连接验证 |
| Ark 无密钥 HEAD 请求 | Node `fetch failed`，底层为 `getaddrinfo ENOTFOUND` | HTTP 401 |

`localhost` 在普通沙箱中仍能解析，外部对照域名也解析失败。直接连接数字 IP
仍被权限拒绝，排除了“只需替换 Ark 域名解析结果即可解决”的解释。
环境代理变量未设置，系统代理配置为空。

扩展权限下的 401 表示 DNS、TCP/TLS 和 HTTP 已可达。因为检查没有携带密钥，
不能用这个 401 判断已配置密钥是否有效。

DSH 的本地适配层把包含 `connection` 等文字的异常统一映射为 `TRANSPORT`，
而 SDK 将底层网络错误包装为 `APIConnectionError`。因此原始日志中的
`Connection error.` 本身不足以识别权限、DNS 或服务端故障；本轮补充检查才完成定位。
详见[诊断结果](diagnosis.json)和[本地源码快照](local-source-index.json)。

## 两个伴随问题

此前扩展权限申请被自动审批以超时原因拒绝，没有给出安全风险判定。
本轮无密钥连通性检查及原授权任务启动都已成功放行；审批服务此前为何超时，
没有内部证据可下结论。

普通沙箱首次启动 DSH 还遇到文件监听 `EMFILE`。隔离配置使用 Chokidar 官方支持的
`CHOKIDAR_USEPOLLING=1` 后，帮助命令启动成功。这只解决启动时的监听问题，
不会改变沙箱网络权限。

## 执行处理

沿用已经确认的同一次恢复授权，通过扩展权限在全新隔离目录继续 DSH 原生 `resume`。
原始失败目录完整保留，没有修改 DSH 或依赖源码，没有改动密钥、提示、模型或实验代码。
本轮付费恢复结果另记于[恢复执行记录](../v0.5-k3-resume-admission-2/README.md)。

以后遇到这类泛化连接错误，应先用不带凭据的 DNS、TCP 和 HTTP 检查确定失败层次，
再决定是否需要扩展权限。返回 401 只用于证明连接可达，真实模型可用性仍以原生调用证据为准。
