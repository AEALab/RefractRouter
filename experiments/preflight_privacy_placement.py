"""零调用预检：真实 Ark 文字模型池声明 simulated-local 后的节点放置与成本口径。

研究假设：把云端公开模型按本地部署对待（simulated-local），边际成本记 0。
本入口不发网关请求、不产生费用，只输出分级、候选收窄、守门事件与双口径价格表。
"""
from copy import deepcopy
import argparse
import json
from pathlib import Path

from refractrouter.agent import run_agent
from refractrouter.application_config import SCHEMA_V2, compile_configuration
from refractrouter.ark_plan import application_configuration

ROOT = Path(__file__).resolve().parents[1]
LOCAL_MODEL = 'deepseek-v4-flash'
SENSITIVE_TASK = '整理客户合同：联络人 wang@example.com，金额 120 万元，输出摘要'
PUBLIC_TASK = '把三段产品说明合并成一段摘要，输出中文短文'


def configuration(*, judge_local=False, privacy=True):
    """真实 Ark 文字模型池；把 deepseek-v4-flash 声明为模拟本地候选。"""
    raw = application_configuration()
    raw['schemaVersion'] = SCHEMA_V2
    for row in raw['models']:
        if row['id'] == LOCAL_MODEL:
            row['deployment'] = 'simulated-local'
        if judge_local and row['role'] == 'judge':
            row['deployment'] = 'simulated-local'
    if privacy:
        raw['privacy'] = {'enabled': True, 'sensitiveTerms': [], 'maxPromptBytes': 1048576}
    return raw


def pricing_rows(raw):
    """求解与记账价格（边际成本）对申报价格：本地化假设的差额留痕。"""
    compiled = compile_configuration(raw).manifest.models
    return [{'model_id': m.model_id, 'deployment': m.deployment,
             'effective_input_per_1k': m.input_cost_per_1k, 'effective_output_per_1k': m.output_cost_per_1k,
             'declared_pricing': m.declared_pricing}
            for m in compiled if getattr(m, 'declared_pricing', None)]


def scenario(name, payload, raw, directory):
    result = run_agent(payload, provider_config=raw, mode='preflight', runs_dir=directory)
    record = json.loads((Path(result['run_dir'])/'result.json').read_text())
    placement = record.get('privacy_placement') or {}
    return {'scenario': name, 'status': result['status'], 'issues': result.get('issues', []),
            'placement_status': placement.get('status'),
            'grades': {node: row['grade'] for node, row in placement.get('grades', {}).items()},
            'eligible_models': placement.get('eligible_models'),
            'blocked': placement.get('blocked'), 'role_checks': placement.get('role_checks'),
            'judge_isolation': placement.get('judge_isolation'), 'events': placement.get('events')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path,
                        default=ROOT/'reports/privacy-placement-v1/preflight-01')
    args = parser.parse_args(argv)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error('必须使用全新输出目录')
    args.output_dir.mkdir(parents=True)
    lease = args.output_dir
    sensitive, public = SENSITIVE_TASK, PUBLIC_TASK
    scenarios = [
        scenario('public-task', {'task': public, 'template': 'single'},
                 configuration(), lease/'runs-public'),
        scenario('sensitive-task-cloud-judge', {'task': sensitive, 'template': 'single'},
                 configuration(), lease/'runs-sensitive-cloud-judge'),
        scenario('sensitive-task-local-judge', {'task': sensitive, 'template': 'single'},
                 configuration(judge_local=True), lease/'runs-sensitive-local-judge'),
    ]
    evidence = {'实验': '隐私感知放置零调用预检',
                '假设': 'deepseek-v4-flash 按 simulated-local 记 0 边际成本',
                '实际模型调用': 0, 'privacy': configuration()['privacy'], 'scenarios': scenarios,
                'pricing': pricing_rows(configuration())}
    (lease/'preflight.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
