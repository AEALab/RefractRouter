# Stage 三路线零调用预检第三版（2026-09-25）

本目录记录完成 DSH 宿主模型能力核对后的冻结协议，没有启动真实模型调用。

- 协议 SHA-256：`b8137dd763df71d64d14521afad3e5e3cd5be1f90a107a44a83b2cafffcec78b`
- 顺序 SHA-256：`8c32e5a1d155f9e27fb9fe2965f6389f91903ebef5d453dfff51af5f27622a0c`
- Static Flash 补丁：`c7f811b452e31ea932d224a3ad8db9e646713d17f14ca40aaf2be4afcd90e5a5`
- Static Pro 补丁：`da8cb0b7ff4f4e920e8630add43f74e5f74a7d33ccfe47bd42409cfc87438e76`
- Stage 补丁：`997585949611acf67a9bd8334a82fba5eaffc6cb9106eaa8afbc4bc565cc533f`
- 执行任务：72 次；独立研究盲评：36 次
- 最大执行调用：1440 次；含盲评最大调用：1476 次
- production AFP 理论上界：47244.9024
- evaluation AFP 理论上界：1459.8144
- 总 AFP 理论上界：48704.7168

当前 DSH 模型目录显示 Ark `deepseek-v4-pro` 支持 `low`、`high`、`max`，而
`deepseek-v4.1-flash` 只显示提供方默认。为了保持三路线推理参数一致，冻结协议统一使用
提供方默认。检查过程没有保存对用户当前规划路由设置的临时改动。

三条路线全部经 `refractagent/planning` 进入同一 DSH Agent 循环：两个基线使用 Static，
Stage 使用 Flash 与 Pro。补丁禁用委派，HTTP 自动重试为 0。每次调用的输入上限为
65536 token、输出上限为 8192 token，规划上下文上限同步设为 73728。

完整任务指纹、交错顺序与调用包络见 [preflight.json](preflight.json)。真实批次仍须使用新的
输出目录，并由用户确认本协议指纹及 production／evaluation AFP 双预算。
