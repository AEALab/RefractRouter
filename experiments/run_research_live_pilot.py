"""公开材料的真实执行先导批次；默认零调用预检，非 #39/#40 完整收益验收。"""
import argparse
from copy import deepcopy
from dataclasses import asdict
from difflib import SequenceMatcher
import hashlib
import json
import math
import os
from pathlib import Path

from refractrouter.dag_study import implementation_fingerprint
from refractrouter.dag_study_execution import write_json
from refractrouter.manifest import load_model_manifest
from refractrouter.openai_compatible import OpenAICompatibleClient
from refractrouter.research_execution import ResearchSession
from refractrouter.research_protocol import digest, historical_materials, material_digest
from refractrouter.responses_api import output_token_limit
from refractrouter.task_execution import node_messages
from refractrouter.task_plan import validate_plan

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ('sqlite-fk', 'https://www.sqlite.org/foreignkeys.html', 'SQLite Foreign Key Support',
     'SQLite 外键启用属于连接级设置；不能依赖默认值。多语句事务内修改 foreign_keys 无效且不报错。'
     '即时约束在语句结束检查，延迟约束可到提交事务时检查，未解决的延迟违例使提交失败。',
     '为一个使用两个连接的应用审核如下迁移方案：连接甲先 BEGIN 再 PRAGMA foreign_keys=ON；'
     '连接乙直接写入，认为甲的设置会共享。团队希望先写子记录再补父记录，并在 COMMIT 前补齐。'
     '给出逐条问题、正确操作顺序，以及选择即时或延迟外键时的区别，不声称执行数据库。',
     ['指出连接设置不共享以及事务内启用无效，给出每连接事务外启用并读取状态的步骤。',
      '区分即时与延迟检查，说明补齐父记录与提交条件；不把事务内无效设置写成已生效。'],
     '分别核查连接级启用规则和事务级约束时机。', '核查两个连接的外键启用顺序和问题。', '分析即时与延迟约束下先子后父的可行条件。'),
    ('python-groupby', 'https://docs.python.org/3.13/library/itertools.html',
     'itertools — Functions creating iterators for efficient looping — Python 3.13.15 documentation',
     'itertools.groupby 按相邻连续且键相等的元素分组，并非 SQL 的全局聚合。'
     '如需按键聚合所有元素，可先按相同键排序。每个返回的组迭代器共享底层输入，'
     '外层向后推进会使前一个组的未保留数据不再可用，需要稍后使用时可当场转为列表。',
     '输入为 [("A",2),("B",5),("A",3),("B",7)]。同事用 groupby 按首元素分组，'
     '先保存全部 (key, group_iterator)，循环结束才分别 list(group_iterator)，期待 A 合计5、B合计12。'
     '分析实际连续分组和延迟消费的问题，给出可保留结果的 Python 修正版及期望输出，不声称运行代码。',
     ['指出原顺序产生 A、B、A、B 四组，解释共享迭代器使延后消费丢失内容。',
      '修正版按相同键排序并在当前组有效时消费，给出 A=5、B=12，不声称已运行。'],
     '先解释迭代语义，再据此核验修正代码和输出。', '解释相邻分组及共享底层输入的语义。', '根据上游语义逐步核对错误并构造修正代码与输出。'),
    ('wai-chart', 'https://www.w3.org/WAI/tutorials/images/complex/',
     'Complex Images | Web Accessibility Initiative (WAI) | W3C',
     '复杂图像需要能识别图像的简短替代文本，以及表达关键信息的详细文本说明。'
     '详细说明可包括数值、比例尺、关系、趋势；图像结构有意义时也应解释。'
     '详细说明宜让所有读者可访问，例如放在主内容中，并可在图像附近提供说明链接。',
     '为一张季度访问量柱状图准备无障碍发布稿。站点甲一月至三月为120、90、60，站点乙为80、80、80；'
     '纵轴从0开始，单位为千次。现有 alt="访问量图"，详细数据仅在鼠标悬浮时显示。'
     '输出简短替代文本、可见长说明和发布检查项，保留数值及趋势，不推断下降原因或声称已通过辅助技术测试。',
     ['给出识别图像的简短替代文本与可访问的详细说明，不能只依赖鼠标悬浮。',
      '准确保留两个站点数值、时间、纵轴与单位，指出甲递减乙稳定，不虚构原因或测试。'],
     '数据与趋势核查、文本替代方案可独立设计，再汇总发布稿。', '核对图表数值、尺度和趋势。', '依据材料设计简短替代文本、长说明和发布检查。'),
]


def fingerprint():
    return {'core': implementation_fingerprint(), 'runner': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def prepare():
    manifest = load_model_manifest(ROOT / 'data/model-manifests/volcengine-agent-plan.json')
    tasks = []
    for key, url, title, facts, prompt, criteria, reason, first, second in SOURCES:
        raw = json.loads((ROOT / ('data/task-plans/serial-analysis-v2.json' if key == 'python-groupby'
                                 else 'data/task-plans/parallel-analysis-v2.json')).read_text())
        raw['decomposition_reason'], raw['acceptance_criteria'] = reason, criteria
        for node in raw['nodes']:
            node['contract']['capability'].update(input_budget_tokens=16384, risk='medium')
            instruction = first if node['node_id'] == 'cost' else second if node['node_id'] == 'risk' else '综合上游与原始材料，逐条满足原始交付要求，保留来源与限制。'
            node['prompt_template'] = node['contract']['objective'] = instruction
        text = f'封闭材料任务，只依据以下已核对的官方材料摘要，不联网或执行工具。\n来源 S1：{url}\n摘要：{facts}\n任务：{prompt}'
        tasks.append({'task_id': key, 'cell': key, 'split': 'development', 'task': text, 'criteria': criteria,
            'source_id': url, 'source_title': title, 'material_sha256': material_digest(text), 'plan': raw})
    return {'schema_version': 'research-execution-pilot-v1', 'purpose': '真实执行链路验收，不能关闭 #39/#40，全部材料以后仅作开发资料。',
        'implementation': fingerprint(), 'manifest_sha256': digest(asdict(manifest)), 'tasks': tasks,
        'modes': ['direct', 'manual', 'auto-cold', 'auto-reuse'], 'fixed_model': 'strong',
        'max_node_fallbacks': 0, 'planner_repairs': 0, 'planner_model': 'strong',
        'planner_input_cap': 16384, 'auto_node_input_cap': 16384, 'judge_input_cap': 65536,
        'execution_policy': {'maxConcurrency': 2, 'providerConcurrency': {'ark-plan': 2}, 'providerMinIntervalMs': {'ark-plan': 100}},
        'constraints': {'qualityMin': 80, 'costMax': 300, 'latencyMaxMs': 300000,
                        'weights': {'quality': .5, 'cost': .25, 'latency': .25}},
        'failure_policy': 'isolate-settled-stop-on-infrastructure',
        'material_review': {'reviewer': 'AI-assisted-Playwright', 'human_review': False,
            'date': '2026-09-09', 'source_families': ['数据库约束', '迭代器语义', '图表文本替代'],
            'limits': '三个不同来源任务，只验证短输入执行链路，不构成正式留出、统计迁移或人工复核。'}}


def preflight(raw, manifest):
    if digest(raw) != digest(prepare()):
        raise ValueError('pilot protocol or implementation changed; create a reviewed revision')
    excluded = historical_materials(ROOT)
    for task in raw['tasks']:
        if task['material_sha256'] in excluded:
            raise ValueError('historical material reused')
        plan = validate_plan(task['plan'], required_criteria=task['criteria'], require_v2=True)
        context = {n.node_id: {'result': '结构预检占位', 'evidence': 'S1', 'assumptions': '未执行'} for n in plan.nodes}
        for node in plan.nodes:
            node_messages(task['task'], node, plan.contracts[node.node_id], context)
    model = next(m for m in manifest.candidates if m.model_id == 'strong')
    def bound(model, cap):
        out = output_token_limit(model)
        if cap + out > model.context_window:
            raise ValueError('context envelope exceeded')
        return cap/1000*model.input_cost_per_1k + out/1000*model.output_cost_per_1k
    production = len(raw['tasks']) * 22 * bound(model, 16384)
    evaluation = len(raw['tasks']) * 6 * bound(manifest.judge, 65536)
    overlap = [{'left': a['task_id'], 'right': b['task_id'],
        'character_similarity': SequenceMatcher(None, a['task'], b['task']).ratio()}
        for i, a in enumerate(raw['tasks']) for b in raw['tasks'][i+1:]]
    return {'protocol_sha256': digest(raw), 'real_model_calls': 0, 'maximum_calls': 84,
        'production_limit': math.ceil(production*10000)/10000, 'evaluation_limit': math.ceil(evaluation*10000)/10000,
        'billing_unit': manifest.billing_unit, 'material_overlap': overlap,
        'independence_limit': '不同来源、不同问题；字符检查只是辅助，未作人工语义独立性认证。',
        'scope': '3 个任务 × 4 条固定强模型路线；每任务另有一次缓存计划设置，不是正式 A/B 收益实验。'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--execute-paid-run', action='store_true')
    parser.add_argument('--approved-protocol-sha256')
    parser.add_argument('--max-production-cost', type=float)
    parser.add_argument('--max-evaluation-cost', type=float)
    args = parser.parse_args(argv)
    raw = json.loads(args.protocol.read_text())
    manifest = load_model_manifest(ROOT / 'data/model-manifests/volcengine-agent-plan.json')
    preview = preflight(raw, manifest)
    if not args.execute_paid_run:
        args.output_dir.mkdir(parents=True, exist_ok=False)
        write_json(args.output_dir / 'preflight.json', preview)
        print(json.dumps(preview, ensure_ascii=False))
        return 0
    if (args.approved_protocol_sha256 != preview['protocol_sha256'] or
            args.max_production_cost != preview['production_limit'] or args.max_evaluation_cost != preview['evaluation_limit']):
        parser.error('真实调用须精确匹配已批准的协议摘要和双预算上限')
    if not os.environ.get('CODEX_ARK_API_KEY'):
        parser.error('缺少 CODEX_ARK_API_KEY；不得把密钥写入协议')
    session = ResearchSession(manifest, raw, args.output_dir, OpenAICompatibleClient(max_retries=0),
        production_limit=args.max_production_cost, evaluation_limit=args.max_evaluation_cost,
        max_calls=preview['maximum_calls'], simulated=False)
    session.result['preflight'] = preview
    session.result['planned_runs'] = [{'task_id': t['task_id'], 'mode': mode} for t in raw['tasks'] for mode in raw['modes']]
    try:
        for task in raw['tasks']:
            for mode in raw['modes']:
                if mode == 'auto-reuse':
                    session.cache_plan(task, task['task_id'])
                session.run_trial(task, task['task_id'] + '-' + mode, mode=mode, fixed_model='strong',
                                  cache_id=task['task_id'] if mode == 'auto-reuse' else None)
    finally:
        result = session.close()
    print(json.dumps({'status': result['status'], 'actual_calls': len(result['calls']),
        'charged': result['charged'], 'delivered': sum(r['delivered'] for r in result['runs']),
        'planned': len(result['planned_runs'])}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
