# Refract Agent（析衡）

> 析构知难，衡派选优 — Refract the task, spend every token where it matters.

RefractRouter 是一个面向**任务分解感知的异构 LLM 路由**研究项目。它研究的问题是：当复杂任务被表示为 DAG 后，如何在质量、成本和延迟之间为每个节点选择合适的模型，而不是只在整个请求层面选择一个模型。

## 当前状态

v0.1 已进入可运行原型阶段。当前实现包含：

- 固定 7 节点报告生成 DAG 与离线 fake model adapter。
- `weak-all`、`strong-all`、`node-type-rule`、`task-oracle`、`node-oracle` 基线策略。
- DeepAgents 0.7 宿主运行时与 LangGraph 执行底座。
- 确定性评分、HTML 输出、baseline 表、Pareto 表和 oracle gap 报告。
- DSH 外层验证边界说明。

当前 dry run 使用 fake model，不调用真实 API，也不包含任何密钥。

## Quick Start

```bash
uv sync --extra dev --extra deepagents
uv run pytest
uv run refractrouter run \
  --task data/tasks/report_001.json \
  --strategy strong-all \
  --output reports/v0.1/report_001-cli.html
uv run python experiments/run_v0_1.py
```

命令说明：

- `uv sync --extra dev --extra deepagents`：安装测试依赖与 DeepAgents/LangGraph。
- `uv run pytest`：运行完整测试套件。
- `uv run refractrouter run ...`：执行一次 canonical task 并输出 standalone HTML。
- `uv run python experiments/run_v0_1.py`：运行五个策略并生成实验报告。

## v0.1 Scope

固定工作域为一般文书办公中的深度调研报告生成：

```text
parse_requirements
  -> build_outline
  -> extract_evidence
  -> synthesize_analysis
  -> write_report
  -> render_html
  -> verify_report
```

Canonical task 是 `data/tasks/report_001.json`，主题为“2026 年企业 LLM Agent 平台选型”。输入使用 `data/source_packs/report_001/` 下的固定 source pack，输出必须是可离线打开的 standalone HTML。

## Architecture Boundary

### DeepAgents / LangGraph

`DeepAgentsGraphExecutor` 使用 DeepAgents 0.7 作为宿主运行时，并通过一个确定性工具调用执行固定 DAG。v0.1 不启用 DeepAgents 的自动规划、动态拆解或自主 sub-agent 生成；图结构和节点顺序由 `TaskDAG` 冻结。

### RefractRouter Core

核心代码位于 `src/refractrouter/`，负责：

- Task DAG schema 与模型注册表。
- 节点执行、上下文传递、拓扑排序。
- 路由策略、节点评分、任务评分。
- 成本与关键路径延迟统计。

### DSH

DeepSeek Harness 只作为外层验证环境，负责启动、校验和证据捕获；不参与模型选择，也不替换 DeepAgents/LangGraph 主执行循环。边界定义见 `validation/dsh/README.md`。

## Current Dry Run

最新 fake-model 结果见 `reports/v0.1/baseline-table.md`：

| Strategy | Task score | Cost (USD) | Critical path (ms) |
|---|---:|---:|---:|
| `weak-all` | 79.762 | 0.001349 | 10155 |
| `strong-all` | 100.000 | 0.016764 | 3441 |
| `node-type-rule` | 83.333 | 0.006469 | 6799 |
| `task-oracle` | 100.000 | 0.016764 | 3441 |
| `node-oracle` | 100.000 | 0.004141 | 8721 |

解读：

- `node-oracle` 与 `task-oracle` 达到相同 100 分。
- `node-oracle` 成本降低 75.30%。
- `node-oracle` 关键路径延迟为 `task-oracle` 的 2.53 倍。
- 按 v0.1 的三目标 Go/No-Go 规则，本轮为 **No-go**：质量-成本优势明确，但未满足延迟不超过 120% 的条件。

完整分析见 `reports/v0.1/oracle-gap.md` 和 `reports/v0.1/pareto-front.md`。

## Repository Layout

```text
src/refractrouter/       Core executor, routing, scoring, metrics, and CLI
tests/                   Unit tests
data/schema/             Task DAG and run-record JSON schemas
data/tasks/              Canonical task definitions
data/source_packs/       Frozen source packs
experiments/             v0.1 experiment runner
validation/dsh/          DSH boundary and runner contract
reports/v0.1/            Generated baseline, Pareto, oracle gap, and run records
```

## Roadmap

1. 扩展到 10-task pilot，并按 `task_id` 做训练 / 测试切分。
2. 引入 OpenAI-compatible real model adapter，模型 ID、版本和价格表在 M0 冻结。
3. 增加独立 judge model 与确定性 HTML/source trace 校验。
4. 接入 DSH 外层 runner，固化环境、依赖与 source-pack hash。
5. 生成 20-task final benchmark 与完整 Go/No-Go 报告。

## Wiki

研究档案、文献笔记、会议纪要和架构讨论位于 [RefractRouter Wiki](https://github.com/AEALab/RefractRouter/wiki)。
