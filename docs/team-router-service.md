# 团队 Router 持久服务

RefractRouter `0.9.0` 在原有同步 HTTP v1 之外提供持久任务协议
`refractagent-http-v2`。它面向单台团队管理机器，使用静态成员 token、项目访问控制和
SQLite WAL 保存任务状态与事件。v2 当前仍只运行 `preflight` 和 `demo`，不会执行付费模型调用。

## 服务配置

团队配置不保存 token，只保存环境变量引用。相对路径以配置文件所在目录为准：

```json
{
  "schemaVersion": "refractrouter-service-v1",
  "statePath": "state/router.sqlite3",
  "projects": [
    {
      "id": "research",
      "runsDir": "runs/research",
      "maxConcurrentTasks": 2,
      "productionBudget": 40,
      "evaluationBudget": 80,
      "timeoutMs": 300000,
      "maxOutputTokens": 128000
    }
  ],
  "members": [
    {
      "id": "alice",
      "role": "member",
      "tokenEnv": "ROUTER_ALICE_TOKEN",
      "projects": ["research"]
    },
    {
      "id": "maintainer",
      "role": "maintainer",
      "tokenEnv": "ROUTER_MAINTAINER_TOKEN",
      "projects": ["research"]
    }
  ]
}
```

启动前由部署环境注入随机 token：

```bash
export ROUTER_ALICE_TOKEN='由部署环境注入的随机值'
export ROUTER_MAINTAINER_TOKEN='另一个随机值'
refractagent serve \
  --host 127.0.0.1 \
  --port 8787 \
  --service-config ./router-team.json
```

非回环监听仍应在服务前配置 TLS。`member` 只能读取自己提交的任务；`maintainer` 可以读取
获准项目中的全部任务。两种角色都不能访问未授权项目。

## HTTP v2

所有 v2 请求使用成员 Bearer token。提交任务还必须提供 `Idempotency-Key`：

```text
POST /v2/tasks
GET  /v2/tasks/{taskId}
GET  /v2/tasks/{taskId}/events?after=0&follow=true
POST /v2/tasks/{taskId}/cancel
GET  /v2/tasks?projectId=research&limit=50
GET  /v2/projects
```

提交信封示例：

```json
{
  "protocol": "refractagent-http-v2",
  "projectId": "research",
  "request": {
    "task": "只进行模拟",
    "strategy": "balanced",
    "template": "single"
  },
  "execution": {
    "mode": "demo"
  }
}
```

同一成员、项目和幂等键再次提交相同请求时返回原任务；请求内容不同则返回 `409`。
事件以单任务单调递增的 `sequence` 保存，客户端断线后可从最后序号继续读取。

## 状态与恢复

任务状态为 `queued`、`running`、`cancel_requested`、`completed`、`failed`、`cancelled`
或 `recovery_required`。取消只停止后续派发，已经发生的工作不会被改写为免费。

服务启动时，数据库中未结束的任务统一转为 `recovery_required`。服务不会自动重放这些任务；
维护者应先检查原运行证据和费用状态，再决定是否以新的幂等键提交新任务。

SQLite 保存任务元数据、请求哈希、状态和事件。核心运行产物仍写入各项目的 `runsDir`，数据库
只保存对应 `run_id` 索引。当前不提供 OIDC、分布式调度、多区域部署或运营后台。

## DSH 插件接入

DSH 插件 `0.22.0` 在设置页使用已有 Router 凭证引用读取 `/v2/projects`，只允许选择当前成员
可访问的项目。浏览器只收到项目 ID、并发上限和协议检查结果，token 始终留在宿主侧。

任务提交后，插件保留任务 ID 与幂等键，并从持久事件的最后序号续读。连接恢复不会新建任务；
DSH 取消信号会调用取消接口。若任务因服务重启进入 `recovery_required`，界面显示待人工核对，
不会把它当成零成本重新执行。仅当提交前确认服务没有 v2 时，插件才使用 HTTP v1。
