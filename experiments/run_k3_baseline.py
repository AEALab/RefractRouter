"""K3 一次调用对照成本约束 DAG：零调用预检、盲评交接与分阶段执行。"""
from dataclasses import asdict
import argparse
import hashlib
import json
import math
import os
from pathlib import Path

if __package__:
    from .run_execution_modes import FixtureAdapter
    from .run_real_v0_1 import BudgetedAdapter, CostLedger, _estimated_invocation_cost
else:
    from run_execution_modes import FixtureAdapter
    from run_real_v0_1 import BudgetedAdapter, CostLedger, _estimated_invocation_cost
from refractrouter.adapters import OpenAICompatibleAdapter
from refractrouter.blind_review import digest, template
from refractrouter.dataset import load_benchmark_dataset
from refractrouter.k3_experiment import (
    chinese_task, roles, prepare, compose, finalize, fixture_reviews,
)
from refractrouter.manifest import load_model_manifest
from refractrouter.openai_compatible import OpenAICompatibleClient
from refractrouter.review_calibration import build_calibration, check_calibration

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def read_bundle(directory):
    index = json.loads((directory/'evidence-index.json').read_text())
    if not isinstance(index.get('artifacts'), dict) or not {'private/state.json', 'preflight.json'} <= index['artifacts'].keys():
        raise ValueError('输入索引缺少必要证据')
    for name, expected in index['artifacts'].items():
        path = (directory/name).resolve()
        if not path.is_relative_to(directory.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('输入证据哈希或路径非法')
    return json.loads((directory/'private/state.json').read_text())


class RecordedAdapter:
    """每次完成调用后立即留证；后续中断时仍能核对已完成结果与费用。"""

    def __init__(self, delegate, path):
        self.delegate, self.path = delegate, path
        self.results = []

    def invoke(self, task, node, prompt, context, model):
        result = self.delegate.invoke(task, node, prompt, context, model)
        self.results.append(result)
        with self.path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(asdict(result), ensure_ascii=False, allow_nan=False)+'\n')
            stream.flush()
        return result


def save_bundle(output, state, summary=None):
    write(output/'private/state.json', state)
    for name, public in [('calibration',state['calibration']['public']),
                         ('node-review',state.get('node_packet')), ('final-review',state.get('final_packet'))]:
        if public:
            write(output/f'public/{name}.json', public)
            write(output/f'public/{name}-template.json', template(public))
    if summary: write(output/'benchmark-summary.json', summary)
    lines = ['# K3 整任务基线对照', '', f"当前阶段：`{state['stage']}`。",
        '离线模拟不构成真实收益证据。' if state['simulation'] else '原始执行与评审分别留证，未知费用不按零处理。', '',
        '主对照为 Kimi-K3 一次完成任务，对比质量达标后选最低费用模型的 DAG。',
        '节点参考路线与探针属于选路开销；不能只报告最终路线费用。', '',
        '仅将 public 中对应材料发给评审者；private 包含策略映射，不应交给盲评者。',
        '复制评分模板到本目录以外填写；保留原模板与证据索引。不要编辑被冻结的输入目录。',
        '节点评分与最终评分必须由同一个已通过校准的评审身份提供。模型自述可能暴露身份，元数据盲化不能消除该风险。',
        '模型评审仍需外部调用和单独用量记录；本入口不会暗中调用一个默认评审模型。']
    if summary and 'baseline_quality' in summary:
        lines += ['', '| 指标 | 数值 |', '|---|---:|']
        for key,label in [('baseline_quality','K3 评审分'),('routed_quality','DAG 评审分'),
                          ('baseline_cost','K3 路线费用'),('routed_cost','DAG 路线费用'),
                          ('selection_setup_cost','参考与探针费用'),('routed_first_use_cost','DAG 首次使用费用'),
                          ('total_production_cost','实验生产总费用')]:
            lines.append(f'| {label} | {summary[key]} |')
        lines += ['', f"判定：`{summary['decision']}`；单轮不自动通过收益门槛。",
                  '外部模型评审费用、人工工时与等待时间另计，当前未知。']
    (output/'README.md').write_text('\n'.join(lines)+'\n')
    write(output/'evidence-index.json', {'artifacts': {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.rglob('*')) if p.is_file() and p.name!='evidence-index.json'},
        'hash_basis':'文件原始字节的 SHA-256；用于完整性核对，不是签名'})


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--manifest', type=Path, default=ROOT/'data/model-manifests/volcengine-agent-plan.json')
    p.add_argument('--dataset', type=Path, default=ROOT/'data/benchmarks/v0.1.json')
    p.add_argument('--phase', choices=['k3-baseline'], default='k3-baseline')
    p.add_argument('--stage', choices=['prepare','compose','finalize'], default='prepare')
    p.add_argument('--mode', choices=['preflight','offline'], default='preflight')
    p.add_argument('--input-dir', type=Path)
    p.add_argument('--reviews', type=Path)
    p.add_argument('--repeats', type=int, default=1)
    p.add_argument('--max-retries', type=int, default=0)
    p.add_argument('--quality-floor', type=float, default=85)
    p.add_argument('--max-quality-gap', type=float, default=5)
    p.add_argument('--execute-paid-run', action='store_true')
    p.add_argument('--max-production-cost', type=float)
    p.add_argument('--max-evaluation-cost', type=float)
    a = p.parse_args(argv)
    if a.repeats!=1 or a.max_retries!=0 or (a.execute_paid_run and a.mode=='offline'):
        p.error('本版本仅允许单轮、零重试，模拟与付费互斥')
    if any(not math.isfinite(v) or not 0<=v<=100 for v in [a.quality_floor,a.max_quality_gap]):
        p.error('质量阈值必须为 0—100 有限数值')
    if a.output_dir.exists() and any(a.output_dir.iterdir()): p.error('必须使用全新输出目录')
    manifest = load_model_manifest(a.manifest)
    baseline, registry = roles(manifest)
    if any(m.provider!='ark-plan' or m.base_url!='https://ark.cn-beijing.volces.com/api/plan/v3'
           or m.wire_api!='chat-completions' for m in manifest.models) or manifest.billing_unit!='AFP':
        p.error('仅允许专用 Agent Plan 清单')
    task = chinese_task(next(t for t in load_benchmark_dataset(a.dataset, ROOT/'data/tasks', ROOT/'data/source_packs').all_tasks if t.task_id=='report_001'))
    code = {str(path.relative_to(ROOT)): digest(path.read_text()) for base in (ROOT/'src/refractrouter', ROOT/'experiments')
            for path in sorted(base.glob('*.py'))}
    config = {'task': asdict(task), 'models': [asdict(m) for m in (*registry.list(),baseline)],
        'manifest_sha256': digest(a.manifest.read_text()), 'dataset_sha256': digest(a.dataset.read_text()),
        'code': code, 'quality_floor': a.quality_floor, 'max_quality_gap': a.max_quality_gap}
    state = read_bundle(a.input_dir) if a.input_dir else None
    if state and state['config_sha256'] != digest(config): p.error('输入材料与当前冻结配置或代码不一致')
    forbidden_models = [baseline.api_model, *(m.api_model for m in registry.list())]
    cap = max(m.max_output_tokens or 0 for m in manifest.models)
    costs = {m.model_id:_estimated_invocation_cost(m,4000,cap) for m in (*registry.list(),baseline)}
    prepare_cost = costs[baseline.model_id]+7*costs[registry.strongest().model_id]+7*sum(costs[m.model_id] for m in registry.list())
    compose_cost = 7*max(costs[m.model_id] for m in registry.list())
    count = 1+7+7*len(registry.list()) if a.stage=='prepare' else 7 if a.stage=='compose' else 0
    estimated = prepare_cost if a.stage=='prepare' else compose_cost if a.stage=='compose' else 0
    preflight = {'phase':'k3-baseline','stage':a.stage,'billing_unit':'AFP','output_language':'zh-CN',
        'model_calls':None if a.execute_paid_run else 0, 'credential_env':baseline.api_key_env, 'wire_api':baseline.wire_api,
        'call_plan':{'training_model_calls':0,'production_model_calls':count,'judge_model_calls':0,'total_model_calls':count},
        'cost_estimates':{'billing_unit':'AFP','production_upper_estimate':round(estimated,2),
            'evaluation_upper_estimate':0,'total_upper_estimate':round(estimated,2)},
        'minimum_production_limit':math.ceil(estimated*100)/100,
        'whole_experiment':{'production_calls':1+14+7*len(registry.list()),'production_estimate':round(prepare_cost+compose_cost,2),
            'independent_review_items':7*len(registry.list())+4,'external_review_cost':None,'outer_dsh_cost':None},
        '说明':'仅计本入口的生产调用；外部独立评审与外层费用未知。输入 4000 token 为估计，不是严格上界。',
        'config':config}
    a.output_dir.mkdir(parents=True, exist_ok=True)
    write(a.output_dir/'preflight.json',preflight)
    if a.mode=='preflight' and not a.execute_paid_run and a.stage!='finalize':
        setup = state or {'stage':'preflight','simulation':False,'config_sha256':digest(config),
                         'calibration':build_calibration(task,ROOT)}
        save_bundle(a.output_dir,setup)
        print(json.dumps({'状态':'零调用预检','本阶段生产预估_AFP':round(estimated,2),'全实验':preflight['whole_experiment']},ensure_ascii=False))
        return 0
    response = json.loads(a.reviews.read_text()) if a.reviews else {}
    if a.mode=='offline':
        if a.input_dir or a.reviews: p.error('完整模拟不接收真实输入材料')
        fixture = FixtureAdapter(registry)
        result = prepare(task,manifest,fixture,simulation=True)
        if result['stage']=='node-review-ready':
            result = compose(result,fixture_reviews(result['node_packet']),fixture,quality_floor=a.quality_floor,max_quality_gap=a.max_quality_gap)
        result.update(calibration=build_calibration(task,ROOT),config_sha256=digest(config))
        summary = (finalize(result,fixture_reviews(result['final_packet']),calibration_passed=False)
                   if result['stage']=='final-review-ready' else {'status':'blocked','simulation':True})
        # 模拟仅检查调用和数据流；不会伪造校准通过。
        summary.update(actual_network_calls=0,actual_paid_cost=0,fixture_production_calls=fixture.calls)
        save_bundle(a.output_dir,result,summary)
        print(json.dumps({'状态':'模拟完成','模拟生产调用':fixture.calls,'实际费用':0},ensure_ascii=False))
        return 0
    if not state or not response: p.error('真实阶段必须提供冻结输入目录与独立评审文件')
    calibration = check_calibration(state['calibration'],response.get('calibration'),forbidden_models=forbidden_models)
    if not calibration['passed']: p.error('评审校准未通过，不启动付费执行')
    if state.get('calibration_result', {}).get('reviewer', calibration['reviewer']) != calibration['reviewer']:
        p.error('评审身份必须与前一阶段一致')
    if state.get('simulation'): p.error('模拟材料不得用于真实运行')
    write(a.output_dir/'submitted-reviews.json', response)
    write(a.output_dir/'input-evidence-index.json', json.loads((a.input_dir/'evidence-index.json').read_text()))
    if a.stage=='finalize':
        if a.execute_paid_run: p.error('汇总阶段禁止模型调用')
        if response.get('final', {}).get('reviewer') != calibration['reviewer']: p.error('最终评审身份与校准身份不一致')
        result=finalize(state,response['final'],calibration_passed=True)
        save_bundle(a.output_dir,{**state, 'stage':result['status']},result)
        return 0 if result['status']=='complete' else 1
    expected_stage = 'preflight' if a.stage=='prepare' else 'node-review-ready'
    if state['stage']!=expected_stage: p.error('输入阶段不匹配')
    if a.stage=='compose' and response.get('nodes',{}).get('reviewer')!=calibration['reviewer']:
        p.error('节点评审身份与校准身份不一致')
    if (a.max_production_cost is None or not math.isfinite(a.max_production_cost) or a.max_production_cost<estimated
        or a.max_evaluation_cost is None or not math.isfinite(a.max_evaluation_cost) or a.max_evaluation_cost<0):
        p.error('必须声明覆盖预检的生产额度及评审额度')
    if os.environ.get('REFRACTROUTER_K3_BASELINE_HOST')!='dsh-plugin' or not os.environ.get(baseline.api_key_env or ''):
        p.error('付费执行必须通过 DSH 原生边界并配置凭据')
    client=OpenAICompatibleClient(max_retries=0,environment={**os.environ,'REFRACTROUTER_MODEL_PROGRESS':str(a.output_dir/'model-progress.ndjson')})
    ledger=CostLedger('AFP',a.max_production_cost,a.max_evaluation_cost,4000,8000,cap)
    adapter=RecordedAdapter(BudgetedAdapter(OpenAICompatibleAdapter(client),ledger), a.output_dir/'production-results.ndjson')
    if a.stage=='prepare': result=prepare(task,manifest,adapter,simulation=False)
    else: result=compose(state,response['nodes'],adapter,quality_floor=a.quality_floor,max_quality_gap=a.max_quality_gap)
    unknown = [{'node_id':r.node_id,'model_id':r.model_id,'failure_type':r.failure_type}
               for r in adapter.results if r.status!='ok' and r.attempts>0 and r.input_tokens==r.output_tokens==0]
    costs = {'stage_production_cost':None if unknown else ledger.production_spent,
             'known_stage_production_cost':ledger.production_spent, 'unknown_usage_requests':unknown}
    result.update(calibration=state['calibration'],calibration_result=calibration,config_sha256=digest(config),**costs)
    summary={'status':result['stage'],'simulation':False,**costs}
    # 交接状态不冒充实验完成。
    write(a.output_dir/'benchmark-summary.json',summary)
    save_bundle(a.output_dir,result)
    return 1 if result['stage']=='blocked' else 0


if __name__=='__main__': raise SystemExit(main())
