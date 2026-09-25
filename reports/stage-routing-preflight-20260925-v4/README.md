# Stage 三路线零调用预检第四版（2026-09-25）

本目录记录修正实验设置隔离与模型真实容量后的冻结协议，没有启动真实模型调用。

- 协议 SHA-256：`b8137dd763df71d64d14521afad3e5e3cd5be1f90a107a44a83b2cafffcec78b`
- 顺序 SHA-256：`8c32e5a1d155f9e27fb9fe2965f6389f91903ebef5d453dfff51af5f27622a0c`
- Static Flash 补丁：`0b6b0c36f82143f3372b68515a43731e0fd39eda28ef660b4022e1caa1fca017`
- Static Pro 补丁：`43078fe37c6e2bdc122e35291c03af4557a8f3a79aa0b6998f1c6e21d61d566b`
- Stage 补丁：`f211a05897945c23aadf1a08710df9543c1d50417662be13b3728d2397dcf053`
- 执行任务：72 次；独立研究盲评：36 次
- 最大执行调用：1440 次；含盲评最大调用：1476 次
- production AFP 理论上界：47244.9024
- evaluation AFP 理论上界：1459.8144
- 总 AFP 理论上界：48704.7168

每个工作区使用独立的 `.refractagent/settings.yaml`，避免用户全局规划路由设置覆盖冻结配置。
模型 `contextWindow` 使用 Ark 官方目录中的 1,024,000 token；实验仍将每次输入和输出包络
分别冻结为 65,536 与 8,192 token。三条路线均禁用委派，HTTP 自动重试为 0。

完整任务指纹、交错顺序与调用包络见 [preflight.json](preflight.json)。72 次付费实验尚未授权，
不得使用本目录直接执行或覆盖历史记录。
