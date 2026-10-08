"""复用失败公开题目，有限比较默认／low；默认零调用，不修改用户配置。"""
import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess

from refractrouter.agent import atomic_json
from refractrouter.application_config import compile_configuration
from refractrouter.dsh_model_pool import compile_dsh_model_pool
from refractrouter.openai_compatible import DshStdioBridge, OpenAICompatibleClient, ModelInvocationError
from refractrouter.task_budget import TaskCallBudget, request_input_bound, InvalidModelOutput
try:
    from .run_automatic_applicability import ROOT, HOST, digest, source_hashes, record_invocation_failure
except ImportError:  # 直接执行实验文件时仍保持同一实现。
    from run_automatic_applicability import ROOT, HOST, digest, source_hashes, record_invocation_failure


def freeze(catalog, messages):
    configuration, _ = compile_dsh_model_pool(catalog['pool'], {
        'schemaVersion':'refractagent-dsh-catalog-v1', 'routes':catalog['routes']})
    model = next(m for m in compile_configuration(configuration).manifest.models
                 if (m.provider, m.api_model) == ('ark', 'deepseek-v4-flash'))
    route = next(r for r in catalog['routes'] if (r['provider'], r['model']) == ('ark','deepseek-v4-flash'))
    if model.billing_mode != 'subscription' or 'low' not in [r['id'] for r in route['reasoning']['efforts']]:
        raise ValueError('诊断仅授权订阅路线及已支持的 low')
    if request_input_bound(messages) > 32768:
        raise ValueError('诊断输入超过授权包络')
    maximum = 2 * (32768 * model.input_cost_per_1k + 8192 * model.output_cost_per_1k) / 1000
    if maximum > .27:
        raise ValueError('诊断估值超过授权上限')
    sources = source_hashes()
    for path in [Path(__file__), ROOT/'validation/dsh/responses_wire_audit.ts']:
        sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    value = {'catalog':catalog, 'configuration':configuration, 'messages':messages,
             'sourceHashes':sources, 'modelId':model.model_id, 'maximumReferenceCny':maximum,
             'maximumCalls':2, 'maxOutputTokens':8192, 'timeoutSeconds':300,
             'reasoning':['default','low'], 'retries':0, 'judgeCalls':0}
    return {**value, 'sha256':digest(value)}


def run(frozen, output):
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output/'preflight.json',frozen)
    model = next(m for m in compile_configuration(frozen['configuration']).manifest.models
                 if m.model_id == frozen['modelId'])
    log = (output/'host-stderr.txt').open('w')
    process = subprocess.Popen(['node','--experimental-strip-types',str(HOST)], cwd=ROOT,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True,
        env={**os.environ, 'REFRACT_APPLICABILITY_AUDIT':str((output/'host.ndjson').resolve()),
             'REFRACT_APPLICABILITY_WIRE_AUDIT':str((output/'wire.ndjson').resolve())})
    budget = None
    try:
        process.stdin.write('{"op":"catalog"}\n');process.stdin.flush()
        if digest(json.loads(process.stdout.readline())) != digest(frozen['catalog']):
            raise ValueError('宿主目录或版本与预检不一致')
        client = OpenAICompatibleClient(dsh_bridge=DshStdioBridge(process.stdout,process.stdin),max_retries=0)
        budget = TaskCallBudget(client,frozen['maximumReferenceCny'],1,max_calls=2,capture_payload=True)
        def persist():
            costs, rows = budget.snapshot()
            atomic_json(output/'ledger.json',{'referenceCostsCny':costs,'cashCostsCny':budget.cash_snapshot(),'records':rows})
        results = []
        for effort in frozen['reasoning']:
            selected = replace(model,max_output_tokens=8192,
                request_options={} if effort == 'default' else {'reasoning_effort':effort})
            reservation = budget.reserve(selected,frozen['messages'],label=effort)
            budget.dispatch(reservation,timeout_seconds=300)
            persist()
            try:
                response = client.for_task_call(300).complete(reservation.model,frozen['messages'])
                budget.settle(reservation,response)
                row = {'effort':effort,'status':'complete','contentChars':len(response.content)}
            except InvalidModelOutput as exc:
                row = {'effort':effort,'status':'invalid-output','message':str(exc)}
            except ModelInvocationError as exc:
                record_invocation_failure(budget,reservation,exc)
                row = {'effort':effort,'status':'error',**exc.public_details()}
            finally:
                persist()
            results.append(row)
            atomic_json(output/'results.json',results)
            print(json.dumps(row,ensure_ascii=False),flush=True)
            if budget.stopped or any(r['status']=='unknown-usage' for r in budget.records):
                break
    finally:
        if process.stdin: process.stdin.close()
        try: process.wait(timeout=15)
        except subprocess.TimeoutExpired: process.terminate();process.wait(timeout=15)
        log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',type=Path,required=True)
    parser.add_argument('--messages',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--freeze-sha256')
    args = parser.parse_args()
    frozen = freeze(json.loads(args.catalog.read_text()),json.loads(args.messages.read_text()))
    if args.execute:
        if args.freeze_sha256 != frozen['sha256']: parser.error('预检已变化，禁止实跑')
        run(frozen,args.output_dir)
    else:
        args.output_dir.mkdir(parents=True,exist_ok=False)
        atomic_json(args.output_dir/'preflight.json',frozen)
        print(json.dumps({k:frozen[k] for k in ['sha256','maximumReferenceCny','maximumCalls']},ensure_ascii=False))


if __name__ == '__main__': main()
