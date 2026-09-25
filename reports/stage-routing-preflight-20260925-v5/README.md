# Stage 三路线零调用预检 v5（2026-09-25）

本目录是 `stage-v3` 的零调用预检，不包含付费模型执行。

- Stage 规则版本：`stage-v3`
- 协议 SHA-256：`b8137dd763df71d64d14521afad3e5e3cd5be1f90a107a44a83b2cafffcec78b`
- 运行顺序 SHA-256：`8c32e5a1d155f9e27fb9fe2965f6389f91903ebef5d453dfff51af5f27622a0c`
- Static Flash 补丁：`0b6b0c36f82143f3372b68515a43731e0fd39eda28ef660b4022e1caa1fca017`
- Static Pro 补丁：`43078fe37c6e2bdc122e35291c03af4557a8f3a79aa0b6998f1c6e21d61d566b`
- Stage 补丁：`f211a05897945c23aadf1a08710df9543c1d50417662be13b3728d2397dcf053`

理论上界保持不变：production 47244.9024 AFP、evaluation 1459.8144 AFP、合计
48704.7168 AFP。72 次效果实验仍未取得授权，也没有执行。

v5 相对 v4 的变化是把 Stage 规则版本写入预检证据。协议、任务、运行顺序、模型补丁和费用
包络没有变化。完整结构见 [preflight.json](preflight.json)。
