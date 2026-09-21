# RefractRouter HTTP 服务

RefractRouter `0.8.0` 提供最小 HTTP 服务，使 DSH 插件可以连接本机或团队部署的
Router URL。服务仍由 Python 核心执行规划、选模、模拟、证据保存与失败判定；插件只负责
传输请求和展示结果。

## 启动

仅供本机使用时运行：

```bash
refractagent serve --host 127.0.0.1 --port 8787
```

健康检查为 `GET /healthz`，任务接口为 `POST /v1/run`。任务响应使用
`application/x-ndjson`，依次发送核心生成的进度事件和最终结果。

本阶段 HTTP v1 只允许 `preflight` 和 `demo`，服务端始终关闭付费执行。DSH 的模型目录
快照可以随请求传入并由 Python 编译；DSH 宿主工具回调和真实模型调用尚不经过 HTTP v1。

## 认证与网络边界

非回环地址必须配置 Bearer token：

```bash
export REFRACTROUTER_SERVICE_TOKEN='由部署环境注入的随机值'
refractagent serve \
  --host 0.0.0.0 \
  --port 8787 \
  --auth-token-env REFRACTROUTER_SERVICE_TOKEN
```

服务端只读取环境变量，不接受命令行明文 token。插件设置同样只保存 DSH 凭证引用。
插件拒绝使用非回环 HTTP URL；团队部署必须在 Router 前配置 TLS，并填写 HTTPS URL。

服务端的费用、时限和输出上限是硬上限。客户端可以请求更小的值，不能放大服务端上限。

## DSH 设置

在“设置 → 插件 → 插件配置 → RefractAgent”中选择：

- “本地 Python 核心”：保持既有行为，由插件启动已安装核心；
- “远程 Router URL”：填写服务根地址，例如 `http://127.0.0.1:8787`；
- “凭证引用”：需要认证时填写 DSH 已配置的凭证名称，不填写 token 本身。

选择远程连接后，插件不会再启动本机 Python 子进程。连接失败、认证失败或协议不匹配会
立即结束“思考”，并以路线不可用或执行失败的稳定错误结束任务。

## 当前边界

- 不开放 v4 真实付费执行；
- 不通过远程接口传递 DSH 原生工具回调；
- 不在 URL、查询参数或插件设置中保存密钥；
- 团队级成员、项目台账、幂等与重启恢复仍是后续服务化工作。
