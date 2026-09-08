"""Install both distributions in isolation and run all three native DSH models.

No provider credential is needed. Demo output is never reported as live acceptance.
This deliberately runs outside the checkout, using an installed wheel and tgz.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def validate_configured_providers(run, workspace, executable, runs, env):
    """已安装 DSH + Python 的本机 HTTP 联调；不会请求外部模型服务。"""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    calls = []
    failures = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                expected = 'Bearer refractrouter-fixture-' + self.path.split('/')[1]
                assert self.headers.get('Authorization') == expected, 'wrong provider credential'
                responses = self.path.endswith('/responses')
                assert responses or self.path.endswith('/chat/completions'), 'wrong endpoint'
                if responses:
                    assert body['max_output_tokens']==32768 and body['store'] is False, f"unexpected output cap: {body.get('max_output_tokens')}"
                    assert body['reasoning']['effort'] in {'low','medium','high'} and 'temperature' not in body
                    if body['model']=='fixture-review':
                        assert body['text']['format']=={'type':'json_object'}
                last = body['input' if responses else 'messages'][-1]['content']
                if isinstance(last, list):
                    last = ''.join(b.get('text', '') for b in last)
                payload = json.loads(last)
                if responses:
                    is_json = body['model']=='fixture-review' or payload['contract']['output']['format']=='json'
                    if is_json: assert body['text']['format']=={'type':'json_object'}
                    else: assert 'text' not in body
                if body['model'] == 'fixture-review':
                    content = {'score': 92, 'passed': True, 'rationale': '本机模拟评审',
                        'criteria': [{'criterion': c, 'passed': True, 'rationale': '本机校验'} for c in payload['criteria']]}
                else:
                    content = {key: '本机模拟服务已收到用户任务。' for key in payload['contract']['output']['fields']}
                answer = json.dumps(content, ensure_ascii=False)
                usage = {'prompt_tokens': 100, 'completion_tokens': 80, 'total_tokens': 180}
                calls.append({'path': self.path, 'model': body['model'], 'stream': body.get('stream', False),
                              'reasoning_effort': body.get('reasoning', {}).get('effort')})
                response = {'id': 'fixture-request', 'object': 'chat.completion', 'created': 1,
                    'model': body['model'], 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': answer},
                    'finish_reason': 'stop'}], 'usage': usage}
                if responses:
                    response = {'id':'fixture-responses', 'status':'completed',
                        'output':[{'type':'reasoning','summary':[]},
                            {'type':'message','role':'assistant','content':[{'type':'output_text','text':answer}]}],
                        'usage':{'input_tokens':100, 'input_tokens_details':{'cached_tokens':20},
                                 'output_tokens':9000,'output_tokens_details':{'reasoning_tokens':8000}}}
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream' if body.get('stream') else 'application/json')
                self.end_headers()
                if body.get('stream'):
                    first = {**response, 'object': 'chat.completion.chunk', 'choices': [{'index': 0,
                        'delta': {'role': 'assistant', 'content': answer}, 'finish_reason': None}]}
                    final = {**first, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]}
                    for chunk in (first, final):
                        self.wfile.write(('data: '+json.dumps(chunk)+'\n\n').encode())
                    self.wfile.write(b'data: [DONE]\n\n')
                else:
                    self.wfile.write(json.dumps(response).encode())
            except Exception as exc:
                failures.append(type(exc).__name__+': '+str(exc))
                self.send_error(500, 'fixture request failed')

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f'http://127.0.0.1:{server.server_port}'
    results = []
    env['FIXTURE_DIRECT_KEY'] = 'refractrouter-fixture-direct'
    env['FIXTURE_HOST_KEY'] = 'refractrouter-fixture-host'
    try:
        for kind in ('direct', 'native', 'mixed', 'responses', 'reasoning-dag'):
            providers = [
                {'id': 'direct', 'type': 'openai-compatible', 'baseUrl': base_url+'/direct', 'credentialEnv': 'FIXTURE_DIRECT_KEY'},
                {'id': 'host', 'type': 'dsh', 'dshProvider': 'fixture-host'},
            ]
            selected = {'direct': [providers[0]], 'native': [providers[1]], 'mixed': providers,
                        'responses': [{**providers[0], 'type':'openai-responses'}],
                        'reasoning-dag': [{**providers[0], 'type':'openai-responses'}]}[kind]
            config = {'schemaVersion': 'refractagent-providers-v1', 'billingUnit': 'USD', 'providers': selected,
                'models': [{'id': role, 'provider': selected[0 if role=='candidate' else -1]['id'],
                    'model': 'fixture-answer' if role=='candidate' else 'fixture-review', 'role': role,
                    'contextWindow': 131072, 'maxOutputTokens': 2048,
                    'pricing': {'unit': 'USD', 'inputPer1k': .001, 'outputPer1k': .002},
                    **({'routing': {'quality': 90, 'latencyMs': 1000}} if role=='candidate' else {})}
                    for role in ('candidate', 'judge')]}
            if kind in {'responses', 'reasoning-dag'}:
                for model in config['models']:
                    model.update(maxOutputTokens=32768, requestOptions={'reasoning':{'effort':'medium'}})
            if kind == 'reasoning-dag':
                low, judge = config['models']
                low.update(id='answer-low', reasoningEffort='low', requestOptions={}, contextWindow=262144)
                low['routing'] = {'quality':60, 'latencyMs':1000, 'outputTokens':1000, 'profiles':[
                    {'nodeType':'synthesis', 'difficulty':'medium', 'risk':'medium',
                     'quality':92, 'latencyMs':1000, 'outputTokens':1000}]}
                high = deepcopy(low)
                high.update(id='answer-high', reasoningEffort='high')
                high['routing'] = {'quality':96, 'latencyMs':8000, 'outputTokens':10000, 'profiles':[
                    {'nodeType':'synthesis', 'difficulty':'medium', 'risk':'medium',
                     'quality':90, 'latencyMs':8000, 'outputTokens':10000}]}
                config['models'] = [low, high, judge]
                config['qualityMin'] = 80
            source = workspace/f'{kind}-providers.json'
            source.write_text(json.dumps(config))
            patch_file = workspace/f'{kind}-live.json'
            run([executable, 'dsh-config', '--provider-config', source, '--output', patch_file,
                 '--runs-dir', runs/kind, '--mode', 'live', '--production-budget', 2, '--evaluation-budget', 1,
                 '--max-output-tokens', 32768 if kind in {'responses','reasoning-dag'} else 2048])
            patch = json.loads(patch_file.read_text())
            next(p for p in patch if p['id']=='refractagent')['config']['allowPaidRuns'] = True
            if kind == 'reasoning-dag':
                next(p for p in patch if p['id']=='refractagent')['config']['template'] = 'compare'
            patch.append({'id': 'llm-pi-ai', 'config': {'providers': {'fixture-host': {
                'displayName': 'Local fixture', 'apiKeyEnv': 'FIXTURE_HOST_KEY',
                'api': 'openai-completions', 'baseURL': base_url+'/host',
                'retryPolicy': {'mode': 'normal', 'maxRetries': 0},
                'models': [{'id': mid, 'name': mid, 'contextWindow': 131072, 'maxTokens': 8192}
                           for mid in ('fixture-answer', 'fixture-review')]}}}})
            patch_file.write_text(json.dumps(patch))
            start = len(calls)
            try:
                answer = run(['dsh', '--profile', 'headless', '--patch', patch_file, '请用一句话比较两种方案。'])
            except RuntimeError as exc:
                raise RuntimeError(f'{kind}: fixture failures={failures}; calls={calls[start:]}') from exc
            summaries = [json.loads(p.read_text()) for p in (runs/kind).glob('*/summary.json')]
            assert len(summaries)==1, answer[-1000:]
            summary = summaries[0]
            assert not failures, failures
            assert summary['status']=='completed', (kind, summary['issues'], answer[-1000:])
            assert summary['billing_unit']=='USD' and not summary['simulated']
            if kind in {'responses', 'reasoning-dag'}:
                assert summary['usage']['reasoning_tokens']==(32000 if kind=='reasoning-dag' else 16000)
                assert summary['usage']['output_tokens']==(36000 if kind=='reasoning-dag' else 18000)
                assert summary['costs']['unconfirmed']==0
            assert len(calls)-start==(4 if kind=='reasoning-dag' else 2) and all(c['stream']==(c['path'].startswith('/host/')) for c in calls[start:])
            if kind == 'reasoning-dag':
                assert {nid: route['id'] for nid, route in summary['model_routes'].items()} == {
                    'cost':'answer-low', 'risk':'answer-low', 'answer':'answer-high'}
                assert [call['reasoning_effort'] for call in calls[start:]] == ['low','low','high','medium']
                result = json.loads(Path(summary['result_path']).read_text())
                assert all(call['reserved'] > .065 for call in result['calls'])
            elif kind == 'responses':
                assert [call['reasoning_effort'] for call in calls[start:]] == ['medium','medium']
            expected_providers = ['fixture-host' if p['type']=='dsh' else p['id'] for p in selected]
            assert summary['model_routes']['answer']['provider']==expected_providers[0]
            assert summary['evaluation_model']['provider']==expected_providers[-1]
            for artifact in (runs/kind).rglob('*.json'):
                assert 'refractrouter-fixture-' not in artifact.read_text(), 'credential in task artifact'
            results.append({'path': kind, 'status': summary['status'], 'model_routes': summary['model_routes'],
                'evaluation_model': summary['evaluation_model'], 'calls': calls[start:],
                'costs': summary['costs'], 'usage':summary['usage'], 'billing_unit': summary['billing_unit']})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    return {'scope': 'installed-dsh-and-python-local-http-fixtures', 'external_model_calls': 0, 'results': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--configured-providers', action='store_true', help='追加直接、DSH 原生及混合 provider 的本机 HTTP 联调')
    parser.add_argument('--packages-dir', type=Path, help='可选：在新目录保留本次验收的安装包')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('use a fresh output directory')
    if args.packages_dir is not None and args.packages_dir.exists():
        parser.error('use a fresh packages directory')
    output = args.output.resolve()
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='refractagent-package-check-') as temporary:
        base = Path(temporary)
        workspace = base/'workspace'
        workspace.mkdir()
        env = os.environ.copy()
        for key in list(env):
            if key.endswith(('API_KEY','API_TOKEN')) or key in {'PYTHONPATH','PYTHONHOME','VIRTUAL_ENV'}:
                env.pop(key,None)
        env.update(DSH_HOME=str(base/'dsh'), UV_TOOL_DIR=str(base/'tools'),
                   UV_TOOL_BIN_DIR=str(base/'bin'), npm_config_cache=str(base/'npm-cache'))
        commands = []
        def run(command, cwd=workspace):
            result = subprocess.run([str(x) for x in command], cwd=cwd, env=env,
                text=True, capture_output=True, timeout=180)
            commands.append({'command':[str(x) for x in command], 'exit_code':result.returncode})
            if result.returncode:
                raise RuntimeError(f'{command[0]} failed: {result.stderr[-5000:]}\n{result.stdout[-1000:]}')
            return result.stdout
        run(['uv','build','--wheel','--out-dir',base/'packages'],ROOT)
        wheel = next((base/'packages').glob('*.whl'))
        packed = json.loads(run(['npm','pack',ROOT/'validation/dsh/plugin','--pack-destination',base/'packages','--json'],ROOT))
        tgz = base/'packages'/packed[0]['filename']
        run(['uv','tool','install',wheel])
        executable = base/'bin/refractagent'
        catalog = json.loads(run([executable,'models']))
        assert [m['id'] for m in catalog['models']] == ['economy','balanced','quality']
        run(['dsh','plugin','--profile','headless','add',tgz])
        runs = workspace/'runs'
        expected = {'economy':'deepseek-v4-flash','balanced':'minimax-m3','quality':'deepseek-v4-pro'}
        results = []
        for strategy, physical in expected.items():
            patch = workspace/f'{strategy}.json'
            run([executable,'dsh-config','--output',patch,'--runs-dir',runs,'--mode','demo','--strategy',strategy])
            composed = run(['dsh','--profile','headless','--patch',patch,'--dump-config'])
            assert 'name: dsh-refractrouter-validation/agent' in composed
            assert 'provider: refractagent' in composed
            task = '请用两句话比较小规模试点和全面推广。'
            answer = run(['dsh','--profile','headless','--patch',patch,task])
            assert '[SIMULATED]' in answer
            candidates = [json.loads(p.read_text()) for p in runs.glob('*/summary.json')]
            summary = next(r for r in candidates if r['strategy']==strategy)
            assert summary['status']=='simulated' and summary['simulated']
            assert summary['models']=={'answer':physical}
            request = json.loads((Path(summary['run_dir'])/'request.json').read_text())
            assert request['mode']=='demo'
            assert request['payload']['task']==task
            assert task in summary['answer']
            assert 'You are an AI agent' in request['payload']['context']
            # Preserve compact acceptance results, not temporary input/system-prompt dumps.
            results.append({k:summary[k] for k in ('strategy','models','status','simulated','costs')})
        configured = validate_configured_providers(run, workspace, executable, runs, env) if args.configured_providers else None
        evidence = {'configured_providers': configured, 'status':'pass','scope':'installed-wheel-and-tgz-native-dsh-demo',
            'paid_model_calls':0,'live_acceptance':False,'catalog':catalog,'results':results,
            'versions':{'dsh':run(['dsh','--version']).strip(),'node':run(['node','--version']).strip()},
            'artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (wheel,tgz)},
            'commands':commands}
        (output/'acceptance.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        if args.packages_dir is not None:
            args.packages_dir.mkdir(parents=True)
            for package in (wheel,tgz):
                shutil.copy2(package,args.packages_dir/package.name)
        print(json.dumps({'status':'pass','strategies':list(expected),'paid_model_calls':0,'evidence':str(output/'acceptance.json')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
