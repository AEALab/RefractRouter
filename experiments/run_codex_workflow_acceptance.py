"""Codex 标准接口的真实文件修复验收；默认只生成零调用冻结预检。"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from threading import Thread

from experiments.automatic_workflow_fixtures import create_fixture, check_fixture
from refractrouter.model_gateway import ModelGateway, HttpModelCaller, create_server, chat_messages, tool_schemas
from refractrouter.planning_config import compile_config, preview
from refractrouter.task_budget import request_input_bound
from refractrouter import gateway_responses


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    path.chmod(0o600)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--baseline-model', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--probe-client', action='store_true', help='实际客户端请求测量，但拒绝模型派发')
    a = p.parse_args()
    config_raw = a.config.read_bytes()
    config = json.loads(config_raw)
    compiled = compile_config(config['planningRouting'])
    model = compiled['models'][compiled['roles']['efficient']]
    if compiled['parameters']['staticMode'] != 'fixed' or model.max_output_tokens != 2048:
        raise ValueError('只验收冻结的 Static 固定模型及 2048 输出包络，不修改日常设置')
    # 本机 CLI 的完整宿主指令及工具目录已零调用测量为 346654 保守输入单位。
    # 这是实验包络，既不删宿主指令，也不修改日常模型配置。
    maximum_calls, input_limit = 8, 524288
    upper = maximum_calls*(input_limit*model.input_cost_per_1k+2048*model.output_cost_per_1k)/1000
    freeze = {'schemaVersion': 'codex-real-workflow-v1',
        'configSha256': hashlib.sha256(config_raw).hexdigest(),
        'catalogSha256': hashlib.sha256(a.baseline.read_bytes()).hexdigest(),
        'provider': model.provider, 'model': model.api_model, 'reasoningEffort': model.request_options.get('reasoning_effort'),
        'maximumCalls': maximum_calls, 'inputBoundPerCall': input_limit, 'maxOutputTokens': 2048,
        'timeoutSeconds': 300, 'httpRetries': 0, 'judgeCalls': 0,
        'cashUpperCny': 0 if model.billing_mode == 'subscription' else upper,
        'referenceUpperCny': upper, 'nativeToolOwner': 'Codex', 'entersDag': False,
        'task': '受控费用精确求和缺陷，真实读写文件和测试，独立边界检查',
        'sourceSha256': {str(path.relative_to(Path(__file__).resolve().parents[1])): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [Path(__file__).resolve(), Path(__file__).resolve().parents[1]/'validation/codex/model_catalog.py',
                         Path(__file__).resolve().parents[1]/'src/refractrouter/model_gateway.py']}}
    if not a.execute:
        a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
        original = create_fixture(a.output/'workspace')
        write(a.output/'fixture-original.json', original)
        check = check_fixture(a.output/'workspace', original)
        if check['passed']:
            raise ValueError('预置缺陷未被独立检查识别')
        write(a.output/'initial-check.json', check)
        gw = ModelGateway(config, a.output/'preview-runs')
        try:
            if not next(row for row in preview(config['planningRouting'])['strategies'] if row['id']=='static')['available']:
                raise ValueError('Static 不可执行')
            module_path = Path(__file__).resolve().parents[1]/'validation/codex/model_catalog.py'
            spec = importlib.util.spec_from_file_location('local_catalog', module_path)
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            write(a.output/'codex-models.json', module.catalog(json.loads(a.baseline.read_text()), a.baseline_model, gw.models()))
        finally:
            gw.close()
        write(a.output/'preflight.json', freeze)
        print(json.dumps({'modelCalls':0, **freeze}, ensure_ascii=False))
        return
    if json.loads((a.output/'preflight.json').read_text()) != freeze:
        raise ValueError('预检已变化，须使用新批次')
    (a.output/'started').open('x').close()
    class Bounded(HttpModelCaller):
        calls = 0
        def guard(self, action):
            if a.probe_client:
                raise ValueError('零调用客户端检查，未派发上游模型')
            if (self.calls >= maximum_calls or action['purpose'] != 'execute'
                    or action['model']['provider'] != model.provider or action['model']['model'] != model.api_model
                    or action['model']['maxTokens'] > 2048
                    or request_input_bound(action['messages'], action['tools']) > input_limit):
                raise ValueError('实际派发超出冻结包络；未重试')
            self.calls += 1
        def __call__(self, action, options):
            self.guard(action); return super().__call__(action, options)
        def stream(self, action, options, on_text):
            self.guard(action); return super().stream(action, options, on_text)
    caller = Bounded(config['providers'])
    class MeasuredGateway(ModelGateway):
        def complete(self, request, **kwargs):
            if a.probe_client:
                write(a.output/'request-measurement.json', {'inputBound':request_input_bound(
                    chat_messages(request['messages']), tool_schemas(request.get('tools',[]))),
                    'calls':0})
                raise ValueError('零调用客户端检查，在预算预留前停止')
            return super().complete(request, **kwargs)
    gw = MeasuredGateway(config, a.output/'runs', caller)
    server = create_server(gw, port=0)
    original_to_chat = gateway_responses.to_chat
    request_tools = []
    def audited_to_chat(request):
        request_tools.append({'tools': [{'type': t.get('type'), 'name': t.get('name'),
            'children': [{'type': child.get('type'), 'name': child.get('name')} for child in t.get('tools', [])]}
            for t in request.get('tools', [])], 'inputTypes': sorted({i.get('type', 'message')
                for i in request.get('input', []) if isinstance(i, dict)})})
        write(a.output/'request-tools.json', request_tools)
        return original_to_chat(request)
    gateway_responses.to_chat = audited_to_chat
    Thread(target=server.serve_forever, daemon=True).start()
    outcome, error = None, None
    try:
        base = f'http://127.0.0.1:{server.server_port}/v1'
        command = ['codex','exec','--ignore-user-config','--ignore-rules','--ephemeral','--skip-git-repo-check',
            '-s','workspace-write','-c','approval_policy="never"','-c','web_search="disabled"',
            '-c','features.multi_agent=false','-c','features.plugins=false',
            '-c','model_provider="refract-workflow-acceptance"',
            '-c',f'model_catalog_json={json.dumps(str((a.output/"codex-models.json").resolve()))}',
            '-c',f'model_providers.refract-workflow-acceptance={{name="Refract 工作流程验收",base_url="{base}",wire_api="responses",request_max_retries=0,stream_max_retries=0}}',
            '-m','refract/static', '这是受控功能验收。阅读 SPEC.md，修复 fees.py，运行 test_fees.py。'
            '不得修改测试或规格；不得委派或联网。仅操作当前目录，最后报告修改和实际测试结果。']
        outcome = subprocess.run(command, cwd=a.output/'workspace', capture_output=True, text=True, timeout=300)
        (a.output/'stdout.txt').write_text(outcome.stdout)
        (a.output/'stderr.txt').write_text(outcome.stderr)
    except Exception as exc:
        error = type(exc).__name__
    finally:
        server.shutdown(); server.server_close()
        gateway_responses.to_chat = original_to_chat
        calls = [row for run in gw.runtime.runs.values() for row in run['budget'].records]
        check = check_fixture(a.output/'workspace', json.loads((a.output/'fixture-original.json').read_text()))
        summary = {'success': error is None and outcome is not None and outcome.returncode == 0 and check['passed'],
            'clientExit': outcome.returncode if outcome else None, 'error': error,
            'actualCalls': caller.calls, 'ledgerCalls': len(calls), 'statuses': [row['status'] for row in calls],
            'cashCostCny': sum(row.get('cash_cost_cny') or 0 for row in calls),
            'referenceCostCny': sum(row.get('reference_cost_cny', row['charged']) for row in calls),
            'modelTtftMs': [row.get('ttft_ms') for row in calls],
            'routerTasks': len(gw.runtime.runs), 'toolOwner': 'Codex', 'httpRetries': 0,
            'dagRuns': 0, 'independentCheck': check}
        write(a.output/'summary.json', summary)
        gw.close()
        print(json.dumps(summary, ensure_ascii=False))
    if a.probe_client and caller.calls == 0 and request_tools:
        return
    if not summary['success']:
        raise RuntimeError('有限真实验收未通过，保留失败记录，不自动扩大或重跑')


if __name__ == '__main__':
    main()
