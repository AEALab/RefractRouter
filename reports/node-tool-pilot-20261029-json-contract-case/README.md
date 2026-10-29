# 完整返回但 JSON 交付合同不通过的案例

样本：`comparison-release-dependencies-node-as-tool-explicit-verification-r1`。
三个模型请求（含一次 check 专家）全部完整返回并正常结算，费用 1.085800 AFP，
任务耗时 218.652 秒。原始响应状态为 completed，最终 finish_reason 为 stop，
实际输出上限为 384000，没有发生长度截断。

最终答案的 JSON 字符串包含未转义换行。按预先冻结的解码合同，主判据为 **fail**，
错误为 `Invalid control character at: line 2 column 318 (char 319)`。提供方原始 output_text 与宿主交付逐字一致，
不能把这个格式问题归因于宿主改写文本。

## 只读副本诊断

为了区分编码问题与字段事实错误，本记录在副本上使用 `json.loads(strict=False)`，
再调用同一字段检查器；诊断结果为 `fail`。
这不修改原始输出、summary.json、冻结主判据或后续执行，也不把该样本改记为通过。
副本诊断详情见 diagnostic.json，原始文本为 original-output.txt。

格式不通过与算术不通过必须分开解释。成本或耗时下降不能直接当作可接受质量下的收益，
也不能把研究 JSON 包装的失败直接推广成真实业务正文全部错误。
未来如要使用确定性规范化或更强输出约束，应另行冻结验证规则并保留原始及处理后证据。

原始文本 SHA-256：`3984766a208577843348f114afac98ff37de201f02cffe192516772342306ba9`。
完整样本矩阵继续执行，未因该已结算格式错误停止整批。

副本的字段值诊断为 pass，冻结来源覆盖仍为 fail（technical_finish、critical_path）。
两种性质分开保留；来源覆盖规则的解释边界见 [规则回读](source-coverage-review.md)。
