# 宿主只读事实与最终字段校验

关联 [#204](https://github.com/AEALab/RefractRouter/issues/204)、
[总计划 W03](https://github.com/AEALab/RefractRouter/issues/201)，前置合同见
[任务结果与当前任务投影](task-result-contract.md)。本入口属于宿主工具，Python 负责提取与
核验；标准模型 Gateway 不执行工具，不进入内部工具循环，不修改路由阈值或模型预算。

## 能力与未知边界

`readonly-local-facts-v1` 首版提供两个查询面：

| 入口 | 可证明内容 | 不可证明内容 |
|---|---|---|
| `refract_source_excerpt` | 固定可见文件中精确的原文、字符及 UTF-8 字节区间 | 原文陈述为真、语义解释正确 |
| `refract_python_structure` | 指定 Python 词法函数中的 if 条件、分支/return 原文和明确表达式结构 | 运行时类型、路径可达、动态派发、最终返回对象 |

字符区间按 Python Unicode 码点计数；字节区间按原始 UTF-8 计数，均左闭右开。
不规范化 CRLF、组合字符或 emoji；不在多字节字符中间截取。不执行被分析代码、导入其模块、
调用 `eval`，也不执行仓库测试。AST 解析器版本进入快照及事实身份，语法不支持时未知。
词法嵌套函数/类的 return 不混进外层，同名符号需提供精确定义行消除歧义。
带星号展开的 tuple 可证明语法节点是 `Tuple`，不能据此证明运行时长度；
`finally`、生成器和异步函数中的 return 也只表示词法表达式。

源码变化、解析失败、可见范围不足、符号歧义、非法边界及容量不足均不生成肯定事实。
返回 `unknown` 或 `denied` 和明确原因码，不截掉来源后继续宣布完整证明。
事实 ID 绑定工具/解析器版本、固定快照、路径、原文件哈希、范围及内容，模型不能自报事实库。
历史研究中的精确原文和结构边界被提取为宿主中立实现；未引入依赖研究数据的解释器，
也没有把手工定位片段称为自动发现缺陷。

## 固定可见清单

宿主清单使用 `readonly-facts-host-v1`，由宿主在任务开始前固定，并以原始字节 SHA-256 锁定。
模型参数不能传入 root、清单路径、哈希或文件列表。清单没有自动扫描全仓库的模式。

```json
{
  "schemaVersion": "readonly-facts-host-v1",
  "root": ".",
  "files": {"src/example.py": "此处填写64位小写原始字节SHA-256"}
}
```

`root` 必须在宿主实际工作区内。`files` 是明确批准的可见源码，值为原始文件字节哈希。
宿主负责排除隐藏测试、参考补丁和评审答案；评测环境须把这些材料放在独立评估范围，
不能因位于同一个仓库就加入清单。文件名本身不足以可靠识别隐藏材料。
清单及固定哈希属于宿主配置，不放进模型可修改的提示或工具参数。
只读打开使用目录描述符及 `O_NOFOLLOW`，拒绝文件和中间目录链接；已锚定的根目录
不会在路径被替换为链接后改读外部目录。读取每个文件都核对原哈希。

可选 `visibleRanges` 对每个清单文件明确列出可见字节区间，例如
`{"src/example.py":[[0,120]]}`；使用时必须覆盖所有清单条目。
来源摘录必须完整处于一个允许区间。结构查询要求整个被选函数可见，
不能用可见的一小段 return 假定周围条件完整。工具不会把解析器内部结构作为动态执行结论。

当前限制为最多 1000 个清单文件、单文件 4 MiB、Python AST 输入 512 KiB/50000 节点、
单次最多 256 条事实/约 48 KB 事实正文、单实例最多 4096 个事实、
单候选正文 256 KiB、最多 64 个声明、宿主请求 1 MiB、宿主响应 128 KiB。
限制只针对本地工具处理能力，不改变模型原生输出上限。

## 最终答案字段绑定

工具原文不是整题评分。模型可在实际最终 JSON 答复中声明：

```json
{
  "answer": {"arity": 2},
  "structuralAssertions": [
    {"factId": "实际工具返回的事实ID", "field": "fixedTupleArity", "answerPointer": "/answer/arity"}
  ]
}
```

宿主从实际已接受候选取得 `content`、`toolCalls`、`finishReason` 和真实调用 ID，
使用与 `task-result-v1` 一致的候选哈希。只有最终 `stop` 文本且无待执行工具调用才能校验。
公共 Python 库和 CLI 共用严格解码与声明检查，不能另传一份正文未声明的断言绕过约束。
声明必须定位 `/answer` 或其子字段，不能用旁路证明字段替代最终答案。
只核对 `source`、`astKind`、`expressionSource`、`fixedTupleArity`、`hasStarred`、
`conditionSource` 等支持字段；没有可确定值或未支持字段时未知。
JSON 重复键、非法数值、不可编码 Unicode 和不明确 JSON pointer 不得形成肯定结论。

宿主实际工具回执记录任务身份、快照和返回的事实 ID。重建时重读固定来源并逐项核对，
当前验证只使用当前任务回执允许的事实；其他任务的实例缓存不构成验收依据。
回执是宿主信任域内的记录，不是对不可信客户端签发的认证令牌。
宿主必须自行保管回执，不能从模型最终答复接收一份自报回执。
重建不调用模型，也不重记模型费用。源码或范围发生变化时不复用旧通过。

`allBoundFieldsSupported` 仅表示本次声明的字段得到支持；
`answerCoverage=selected-fields-only`，未绑定部分仍未知。
`wholeTaskQualityProven` 和 `unboundTextSemanticsChecked` 始终为 `false`。
这不是整题放行器，不会据此替换答卷、改变模型、追加审核调用或自动计为质量合格。
普通文本或未提交声明仍可正常交付，校验结果明确保留未知。

## 宿主入口

Python 宿主可调用 `ReadonlyFacts`，或使用有界 CLI：

```bash
/可信安装目录/bin/python -I -B -m refractrouter.agent_cli fact-tool --manifest /绝对路径/facts-manifest.json \
  --manifest-sha256 清单原始字节SHA256 --workspace-root /绝对路径/工作区 --request-stdin
```

查询请求为 `{"op":"query","identity":{"session":"s","agent":"a","turn":1},
"operation":"python-structure","arguments":{"path":"src/example.py","symbol":"f","definitionLine":null}}`。
`source-excerpt` 的 arguments 为 `path/start/end/unit`，unit 为 `char` 或 `utf8-byte`。
查询返回的 `modelText` 是唯一应交给模型的正文；`receipt` 留在宿主。
核验请求为 `op=verify`，附相同 identity、真实 candidateId、实际规范候选及宿主 receipts；
Python 从实际候选中读取声明，不接收模型另交一份替代答卷。

标准 function 客户端把 `tool_schemas()` 作为模型工具定义，收到原生调用后由客户端执行 CLI
或同一 Python 库，再将 `modelText` 作为 tool result 续接。Router 始终只透传模型协议。
最终由客户端提供真实交付候选进行字段核验；只验证了此模拟往返，不宣称任意 Agent 已接通。

DSH 显式配置并重新加载插件后启用，默认关闭：

```json
{"factTools":{"enabled":true,"manifestPath":"/宿主配置/facts-manifest.json","manifestSha256":"清单SHA256"}}
```

插件登记两个原生工具，通过只读沙箱调用已安装 Python 核心；子进程不注入模型凭据。
Python 模块入口使用 `-I -B` 隔离模块搜索并禁写字节码，不导入待分析仓库中的同名
`json.py` 或用户 site 配置；其他宿主须提供同等隔离，不能依赖待分析仓库的 `PYTHONPATH`。
缺少完整沙箱或工具注册能力时拒绝启用/执行，不绕过权限。
DSH 会话/Agent/turn 来自真实宿主事件，清单配置在任务内冻结，禁用后不继续读取。
Planning 模型入口在核心已结算并接受候选后，用宿主回执核验实际候选，报告放在
`refractPlanning.factVerification` 中；后续模型历史转换不会把报告、回执或索引塞回提示。
报告只用于观测，不修改核心的交付选择；自定义其他模型入口没有自动最终校验时仍属未验收。

规范候选按 DSH 原生 `BlockAssembler` 的首次出现顺序建立，结束块正文覆盖增量；
部分文本仅有结束块或仅有增量时也保留。核心结算和最终事实校验共享同一规范候选。
协议回归数据由已安装的 `@deepseek-ai/dsh-llm@0.1.5-rc.3` 直接生成，记录模块哈希；
生成脚本为 `validation/dsh/plugin/scripts/freeze-host-assembly.ts`。

## 用量、时间与验证

`visibleUtf8Bytes` 是精确 `modelText` 字节数。没有宿主的可靠 token 测量时，
`addedInputTokens=null` 并标明未知，不用字节/字符估算冒充真实 token。
后续评测还须记录上游实际总输入用量，包含工具 schema、工具正文和历史重传，才能比较完整费用。
Python 报告提取/核验时间，DSH 另记录含进程启动及 IPC 的 `hostWallMs`；
本地 CPU 和等待不称为免费生产审核。工具本身模型调用为零。

回归包含范围/身份隔离、文件漂移、链接、Unicode/emoji/CRLF、非法字节区间、同名与嵌套
作用域、解析失败、容量、伪造事实、候选修订、回执重建及解析前守门。
指定旧例使用官方固定提交的原始源码，与既有可见材料逐字节相同：

- [Sphinx LaTeX 源码](https://github.com/sphinx-doc/sphinx/blob/f1061c012e214f16fd8790dec3c283d787e3daa8/sphinx/writers/latex.py)：
  保留 triple 的三条不同格式原文，不统一改写标点。
- [SymPy 单位系统源码](https://github.com/sympy/sympy/blob/514579c655bf22e2af14f0743376ae1d7befe345/sympy/physics/units/unitsystem.py)：
  证明完整 return 的 tuple/星号语法，展开长度保留未知。

夹具带来源哈希和原许可证，仅作已暴露旧例回归，不进入新的独立留出。
DSH/标准 function 使用真实工具实现和模拟模型完成往返；安装脚本另验实际 wheel 中的
CLI，源码、构建、安装包和用户现装插件分开记录。用户现装插件不会因此自动升级。
本包不声称恢复自然语言整题质量，收益仍由 #210 的独立同条件实验决定。
首版路径保护在 Linux/macOS 验证；其他平台未验收，不以注册成功冒充工具运行兼容。
