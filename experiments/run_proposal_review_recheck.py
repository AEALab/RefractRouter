"""有限冻结审核案例；默认零调用，不生成新执行答案。"""
from __future__ import annotations
import argparse
from dataclasses import replace, asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from experiments.run_automatic_applicability import (
    ROOT, HOST, digest, source_hashes, historical_roots, historical_protection,
)
from refractrouter.agent import atomic_json
from refractrouter.dsh_model_pool import compile_dsh_model_pool
from refractrouter.application_config import compile_configuration
from refractrouter.openai_compatible import DshStdioBridge, OpenAICompatibleClient, ModelInvocationError
from refractrouter.task_budget import TaskCallBudget, request_input_bound
from refractrouter.task_evaluation import evaluate_text, evaluation_messages, REVIEW_CONTRACT

CASES = ROOT/'data/research/proposal-constraint-recheck-v2.json'
GROUNDING_CASES = ROOT/'data/research/automatic-grounding-recheck-v1.json'


def hashes(extra=None):
    result = source_hashes()
    for p in (CASES, GROUNDING_CASES, Path(__file__)):
        result[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    if extra is not None:
        p = Path(extra).resolve()
        result[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def freeze(catalog, *, judge_reasoning=None, grounding_cases=False, native_case_file=None):
    if grounding_cases and native_case_file is not None:
        raise ValueError('只能选择一套冻结案例')
    fixture_path = Path(native_case_file).resolve() if native_case_file is not None else (GROUNDING_CASES if grounding_cases else CASES)
    fixture = json.loads(fixture_path.read_text())
    if native_case_file is not None:
        if fixture.get('schemaVersion') != 'automatic-grounding-native-recheck-v1' or not fixture.get('baselineInputSha256'):
            raise ValueError('本次宿主复查必须提供已核对原派发摘要的两例合同')
    configuration, provenance = compile_dsh_model_pool(catalog['pool'], {
        'schemaVersion':'refractagent-dsh-catalog-v1','routes':catalog['routes']})
    model = compile_configuration(configuration).manifest.judge
    model = replace(model, max_output_tokens=min(model.max_output_tokens, fixture['outputLimit']))
    if judge_reasoning is not None:
        route = next((r for r in catalog['routes'] if r['provider']==model.provider and r['model']==model.api_model), {})
        supported = [e['id'] for e in route.get('reasoning', {}).get('efforts', [])]
        if judge_reasoning not in supported:
            raise ValueError('审核推理设置未经当前宿主目录确认')
        model = replace(model, request_options={**model.request_options, 'reasoning_effort':judge_reasoning})
    if model.billing_unit != 'CNY':
        raise ValueError('本次审核仅允许冻结的 CNY 参考价格')
    cases = fixture['cases']
    count = 2 if grounding_cases or native_case_file is not None else 4
    if len(cases) != count or len({c['id'] for c in cases}) != count:
        raise ValueError('本次仅验收所选择的固定案例')
    bounds = []
    for c in cases:
        if hashlib.sha256(c['answer'].encode()).hexdigest() != c['answerSha256']:
            raise ValueError('候选回复摘要不匹配')
        if type(c.get('expectedPassed')) is not bool:
            raise ValueError('案例预期必须明确冻结')
        bound = request_input_bound(evaluation_messages(fixture['task'], c['answer'], fixture['criteria'],
            tool_evidence=fixture.get('toolEvidence')))
        if bound + model.max_output_tokens > model.context_window:
            raise ValueError('审核输入超过模型容量')
        bounds.append(bound)
    maximum = sum(b*max(model.input_cost_per_1k, model.cache_write_cost_per_1k or 0)/1000 + model.max_output_tokens*model.output_cost_per_1k/1000
                  for b in bounds)
    cash_maximum = 0 if model.billing_mode == 'subscription' else maximum
    history = historical_protection(historical_roots(ROOT, Path.home()/'Documents/Codes/RefractRouter'))
    protected = history['cashProtectedCny'] + 1  # 独立历史 Jev 保护，不释放。
    if maximum > 2 or protected + cash_maximum > 100:
        raise ValueError('超过本次参考上限2 CNY或累计现金授权100 CNY')
    result = {'schemaVersion':'proposal-review-preflight-v1','reviewContract':REVIEW_CONTRACT,
        'fixture':fixture,'catalog':catalog,'configuration':configuration,'provenance':provenance,
        'model':asdict(model),'inputBounds':bounds,'maximumCalls':count,'maximumReferenceCny':maximum,
        'maximumCashCny':cash_maximum,'cumulativeCashCeilingCny':100,
        'historyCashProtectedCny':protected,'sourceHashes':hashes(fixture_path) if native_case_file is not None else hashes(),
        **({'fixtureSource':str(fixture_path.relative_to(ROOT))} if native_case_file is not None else {}),
        'httpRetries':0,'newJevCalls':0,'newExecutorCalls':0}
    return {**result,'sha256':digest(result)}


def run(frozen, output):
    if digest({k:v for k,v in frozen.items() if k!='sha256'}) != frozen['sha256']:
        raise ValueError('冻结预检内容被修改')
    actual_hashes = hashes(ROOT/frozen['fixtureSource']) if frozen.get('fixtureSource') else hashes()
    if actual_hashes != frozen['sourceHashes']:
        raise ValueError('源码或候选在预检后变化')
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output/'preflight.json', frozen)
    fixture=frozen['fixture']
    model=replace(compile_configuration(frozen['configuration']).manifest.judge,
                  max_output_tokens=frozen['model']['max_output_tokens'],
                  request_options=frozen['model']['request_options'])
    atomic_json(output/'manifest.json', {'billing_unit':'CNY','models':[asdict(model)]})
    rows=[];budget=None
    with (output/'host-stderr.txt').open('w') as log:
        process=subprocess.Popen(['node','--experimental-strip-types',str(HOST)],cwd=ROOT,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True,
            env={**os.environ,'REFRACT_APPLICABILITY_AUDIT':str((output/'host-diagnostics.ndjson').resolve())})
        def persist():
            if budget is None:return
            charged,calls=budget.snapshot()
            atomic_json(output/'result.json',{'mode':'run','billing_unit':'CNY','charged':charged,
                'cash_costs_cny':budget.cash_snapshot(),'calls':calls,'cases':rows})
        try:
            process.stdin.write(json.dumps(frozen['catalog'].get('catalogRequest',{'op':'catalog'}))+'\n')
            process.stdin.flush()
            if digest(json.loads(process.stdout.readline())) != digest(frozen['catalog']):
                raise ValueError('实际宿主目录在预检后改变')
            actual=OpenAICompatibleClient(dsh_bridge=DshStdioBridge(process.stdout,process.stdin),
                max_retries=0, timeout_seconds=fixture['timeoutMs']/1000)
            class Audited:
                def __init__(self, client):self.client=client
                def for_task_call(self, seconds):return Audited(self.client.for_task_call(seconds))
                def complete(self, model, messages, **kwargs):
                    persist()  # dispatch 已标为 unknown-usage，先落证据再通信。
                    return self.client.complete(model,messages,**kwargs)
            budget=TaskCallBudget(Audited(actual),1,frozen['maximumReferenceCny'],max_calls=frozen['maximumCalls'],capture_payload=True,
                cash_limits={'production':1,'evaluation':max(frozen['maximumCashCny'],.001)})
            budget.on_reserve=lambda _:persist()
            for case in fixture['cases']:
                started=time.monotonic()
                try:
                    verdict=evaluate_text(budget,model,fixture['task'],case['answer'],criteria=fixture['criteria'],
                        label=case['id'],deadline=started+fixture['timeoutMs']/1000,
                        tool_evidence=fixture.get('toolEvidence'))
                    actual_passed=verdict['passed'] and verdict['score']>=80
                    row={'id':case['id'],'expectedPassed':case['expectedPassed'],'actualPassed':actual_passed,
                         'matched':actual_passed==case['expectedPassed'],'verdict':verdict,'status':'completed'}
                except Exception as exc:
                    row={'id':case['id'],'status':'failed','matched':False,
                         'error':exc.public_details() if isinstance(exc,ModelInvocationError) else type(exc).__name__}
                    rows.append({**row,'wallMs':round((time.monotonic()-started)*1000)})
                    budget.stop();persist();raise
                rows.append({**row,'wallMs':round((time.monotonic()-started)*1000)})
                persist()
                print(json.dumps({k:v for k,v in rows[-1].items() if k!='verdict'},ensure_ascii=False),flush=True)
        finally:
            persist()
            if process.stdin:process.stdin.close()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=10)
            atomic_json(output/'completion.json',{'planned':frozen['maximumCalls'],'finished':len(rows),
                'complete':len(rows)==frozen['maximumCalls'] and all(r['status']=='completed' for r in rows),
                'matched':sum(r['matched'] for r in rows)})
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--judge-reasoning', choices=['low','high','max'])
    parser.add_argument('--grounding-cases', action='store_true')
    parser.add_argument('--native-case-file', type=Path)
    parser.add_argument('--freeze-sha256')
    args=parser.parse_args()
    frozen=freeze(json.loads(args.catalog.read_text()), judge_reasoning=args.judge_reasoning,
                  grounding_cases=args.grounding_cases, native_case_file=args.native_case_file)
    if not args.execute:
        args.output_dir.mkdir(parents=True,exist_ok=False)
        atomic_json(args.output_dir/'preflight.json',frozen)
        print(json.dumps({k:frozen[k] for k in ('sha256','maximumCalls','maximumReferenceCny','maximumCashCny','historyCashProtectedCny')},ensure_ascii=False))
    else:
        if args.freeze_sha256 != frozen['sha256']:parser.error('必须绑定冻结摘要')
        run(frozen,args.output_dir)


if __name__=='__main__':main()
