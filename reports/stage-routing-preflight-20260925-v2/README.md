# Stage 三路线零调用预检第二版（2026-09-25）

本目录只记录推理档位完成宿主能力核对前的零模型调用预检，没有启动真实效果实验。
核对后冻结为双方共同支持的「提供方默认」，后续预检写入
[第三版目录](../stage-routing-preflight-20260925-v3/README.md)；本目录保留为历史证据。

- 协议 SHA-256：`3f4ac1125dc1a676353abc4d18de8ccd0caf9f91d244cc1f4e46241993a1a870`
- 顺序 SHA-256：`8c32e5a1d155f9e27fb9fe2965f6389f91903ebef5d453dfff51af5f27622a0c`
- Static Flash 补丁：`c7f811b452e31ea932d224a3ad8db9e646713d17f14ca40aaf2be4afcd90e5a5`
- Static Pro 补丁：`da8cb0b7ff4f4e920e8630add43f74e5f74a7d33ccfe47bd42409cfc87438e76`
- Stage 补丁：`997585949611acf67a9bd8334a82fba5eaffc6cb9106eaa8afbc4bc565cc533f`
- 执行任务：72 次；独立研究盲评：36 次
- 最大执行调用：1440 次；含盲评最大调用：1476 次
- production AFP 理论上界：47244.9024
- evaluation AFP 理论上界：1459.8144
- 总 AFP 理论上界：48704.7168

三条路线全部经 `refractagent/planning` 进入同一 DSH Agent 循环：两个基线使用 Static，
Stage 使用高效 Flash 与强执行 Pro。这样三路线共用相同的调用次数、任务期限、原生工具、
账本和首字等待采集。补丁禁用委派工具，并将 HTTP 自动重试设为 0。

上界按每次 65536 输入 token 与 8192 输出 token 计算。模型的规划上下文上限同步收窄为
73728，防止实际请求突破预算包络。真实批次仍需先修复并验收 headless profile 的历史失效
`link:` 安装，核对两个模型共同推理等级，然后由用户确认协议指纹及 AFP 双预算。

完整任务指纹、交错顺序与调用包络见 [preflight.json](preflight.json)。使用 `--prepare`
建立真实批次目录时，运行器会在该新目录生成 `patches/` 和 `workspaces/`，本预检目录不复制派生产物。
