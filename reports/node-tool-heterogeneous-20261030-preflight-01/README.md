# 首次零调用演练诊断

真实模型调用0，真实AFP0。四个DSH组合完成后，Python DAG演练记录缺少`nodes`初始化，
导致`KeyError: nodes`；冻结件和已生成的模拟证据原样保留。
此目录没有最终预检通过结论，源码修正后使用新目录，不覆盖本次产物。
当前实现已变化，本冻结件不再通过源码绑定校验；最终结果见[第三次预检](../node-tool-heterogeneous-20261030-preflight-03/README.md)。
