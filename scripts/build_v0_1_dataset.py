from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOPICS = (
    "企业 Agent 可观测性平台选型",
    "企业 RAG 架构方案选型",
    "向量数据库平台选型",
    "云成本优化平台选型",
    "身份与访问管理平台选型",
    "事故响应管理平台选型",
    "数据治理平台选型",
    "客服自动化平台选型",
    "研发效能平台选型",
    "API 网关平台选型",
    "业务流程自动化平台选型",
    "模型服务平台选型",
    "企业知识管理平台选型",
    "安全运营自动化平台选型",
    "合同审查自动化平台选型",
    "分析与 BI 平台选型",
    "CRM 迁移方案选型",
    "文档管理平台选型",
    "AI 编程助手治理方案选型",
)
SECTIONS = (
    "Executive Summary",
    "Background",
    "Selection Criteria",
    "Platform Comparison",
    "Risks",
    "Conclusion",
    "References",
)
NODES = (
    ("parse_requirements", "planning", "Extract the report topic, audience, required sections, and output constraints.", ()),
    ("build_outline", "planning", "Build a section outline that covers every required section.", ("parse_requirements",)),
    ("extract_evidence", "extraction", "Extract the most relevant claims from the fixed source pack. Preserve source_id and content_hash.", ("build_outline",)),
    ("synthesize_analysis", "synthesis", "Compare candidate platforms against the selection criteria and identify tradeoffs.", ("extract_evidence",)),
    ("write_report", "generation", "Write the full report body with every required section and citation.", ("synthesize_analysis",)),
    ("render_html", "rendering", "Render the report as a standalone HTML document with a source trace.", ("write_report",)),
    ("verify_report", "verification", "Verify required sections, citations, HTML validity, and output constraints.", ("render_html",)),
)


def main() -> int:
    for index, topic in enumerate(TOPICS, start=2):
        task_id = f"report_{index:03d}"
        source_pack = ROOT / "data" / "source_packs" / task_id
        source_pack.mkdir(parents=True, exist_ok=True)
        monthly_volume = 1000 + index * 137
        current_days = 10 + index % 7
        alpha_cost = 100 + index * 4
        beta_cost = 70 + index * 3
        alpha_tco = alpha_cost * 3 + 60
        beta_tco = beta_cost * 3 + 90
        sources = (
            ("业务背景", f"该组织每月处理 {monthly_volume} 个与“{topic}”相关的工作项，当前平均周期为 {current_days} 天。项目目标是在不降低合规性的前提下，将周期缩短至少 25%。"),
            ("Atlas 方案", f"Atlas 预计 6 周上线，自动化覆盖率为 70%，年度许可成本为 {alpha_cost} 千美元。它支持单点登录、审计导出和私有网络连接。"),
            ("Beacon 方案", f"Beacon 预计 12 周上线，自动化覆盖率为 55%，年度许可成本为 {beta_cost} 千美元。它覆盖全部五个关键业务系统，但其中两个连接器需要定制。"),
            ("安全评审", "Atlas 已支持客户管理密钥、角色权限和不可变审计日志。Beacon 支持角色权限，但客户管理密钥计划在第四季度提供。"),
            ("集成评估", "Atlas 原生覆盖五个关键系统中的四个，缺失系统可通过标准 API 接入。Beacon 原生覆盖五个关键系统，但两个连接器仍需为本项目配置定制字段映射。"),
            ("运营评估", "Atlas 提供 99.90% 服务目标和 7x24 支持。Beacon 提供 99.95% 服务目标，但标准套餐仅含工作日支持。"),
            ("财务模型", f"包含实施、许可和内部运维后，Atlas 三年总拥有成本为 {alpha_tco} 千美元，Beacon 为 {beta_tco} 千美元。该估算不包含未来用量增长。"),
            ("风险与建议", "当合规、上线速度和支持覆盖优先时，评审组倾向 Atlas；当最低三年成本和现成集成广度优先时，Beacon 更有优势。最终决策应通过限时试点验证自动化覆盖率。"),
        )
        for source_index, (title, content) in enumerate(sources, start=1):
            path = source_pack / f"source_{source_index:03d}.md"
            path.write_text(
                f"# {title}\n\n> 合成 benchmark brief，不代表现实供应商事实。\n\n{content}\n",
                encoding="utf-8",
            )
        task = {
            "task_id": task_id,
            "domain": topic,
            "source_pack_id": task_id,
            "required_sections": list(SECTIONS),
            "output_constraints": [
                "standalone HTML",
                "all claims cite source_id",
                "no external CSS or JavaScript",
            ],
            "expected_claims": [
                f"Atlas 预计 6 周上线，年度许可成本为 {alpha_cost} 千美元。",
                f"Beacon 预计 12 周上线，年度许可成本为 {beta_cost} 千美元。",
                f"Atlas 三年总拥有成本为 {alpha_tco} 千美元，Beacon 为 {beta_tco} 千美元。",
            ],
            "scoring_rubric_version": "v0.1",
            "nodes": [
                {
                    "node_id": node_id,
                    "node_type": node_type,
                    "prompt_template": prompt,
                    **({"parents": list(parents)} if parents else {}),
                }
                for node_id, node_type, prompt, parents in NODES
            ],
        }
        (ROOT / "data" / "tasks" / f"{task_id}.json").write_text(
            json.dumps(task, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
