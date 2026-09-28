"""Advisor／Composite 三客户端真实接线；先冻结预检，再显式执行。"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
from threading import Thread

import yaml

from refractrouter import gateway_responses
from refractrouter.model_gateway import ModelGateway, HttpModelCaller, create_server, chat_messages, tool_schemas
from refractrouter.planning_config import compile_config, preview
from refractrouter.task_budget import request_input_bound


MAX_CALLS = 5
INPUT_LIMIT = 98304
CODEX_INPUT_LIMIT = 300000
EXECUTION_LIMIT = 2048
MAX_BATCH_OUTPUT = 4096
PRIOR_AFP_WORST_CASE = 140
AUTHORIZED_AFP = 2000


def snapshot(profile: Path, strategy: str):
    # YAML 的日期类型只存在于 Python 读取过程；DSH 运行时持有字符串。
    root = json.loads(json.dumps(yaml.safe_load(profile.read_text()), default=str))
    planning = deepcopy(root['refractagent']['planningRouting'])
    selected = planning[strategy]
    ids = set()
    if strategy == 'advisor':
        ids.update((selected['executor'], selected['judge'].get('modelId')))
    else:
        ids.update((*selected['pool'], selected['takeover'], selected['judge'].get('modelId')))
    planning['maxProductionCost'] = 400
    planning['maxCalls'] = MAX_CALLS
    planning['timeoutMs'] = 300000
    compiled = compile_config(planning)
    if not next(row for row in preview(planning)['strategies'] if row['id'] == strategy)['available']:
        raise ValueError('当前策略零调用检查不可用')
    models = {key: compiled['models'][key] for key in ids if key in compiled['models']}
    if any(model.billing_unit != 'AFP' or model.provider != 'ark' for model in models.values()):
        raise ValueError('本批仅授权已冻结的 Ark AFP 路线')
    return {'planningRouting': planning, 'providers': {'ark': {
        'baseURL': 'https://ark.cn-beijing.volces.com/api/plan/v3',
        'apiKeyEnv': 'CODEX_ARK_API_KEY', 'timeoutSeconds': 120},
        'deepseek-official': {'baseURL': 'https://api.deepseek.com/v1'}}}, models


def command_for(args, base, gateway):
    if args.client == 'dsh':
        return ['node', '--experimental-strip-types',
            'validation/dsh/plugin/scripts/check-gateway-tools.ts',
            str(args.dsh_modules), base, '256', args.strategy]
    if args.client == 'hermes':
        return [str(args.hermes_root / 'venv/bin/python'),
            'validation/hermes/check_gateway.py', str(args.hermes_root), base, args.strategy]
    import importlib.util
    spec = importlib.util.spec_from_file_location('codex_catalog', 'validation/codex/model_catalog.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    baseline = json.loads(args.codex_baseline.read_text())
    adapted = module.catalog(baseline, args.codex_baseline_model, gateway.models())
    catalog = (args.output / 'codex-models.json').resolve()
    catalog.write_text(json.dumps(adapted, ensure_ascii=False))
    catalog.chmod(0o600)
    return ['codex', 'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral',
        '--skip-git-repo-check', '-s', 'read-only', '-c', 'web_search="disabled"',
        '-c', 'model_provider="refract-acceptance"',
        '-c', f'model_catalog_json={json.dumps(str(catalog))}',
        '-c', f'model_providers.refract-acceptance={{name="Refract acceptance",base_url="{base}",'
              'wire_api="responses",request_max_retries=0,stream_max_retries=0}',
        '-m', 'refract/' + args.strategy,
        '只做此项接线验收：通过终端工具执行 printf REFRACT_HOST_TOOL_OK 一次，'
        '收到结果后只回答 GATEWAY_CLIENT_OK。不要调用其他工具。']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--client', choices=('dsh', 'codex', 'hermes'), required=True)
    parser.add_argument('--strategy', choices=('advisor', 'composite'), required=True)
    parser.add_argument('--dsh-modules', type=Path)
    parser.add_argument('--codex-baseline', type=Path)
    parser.add_argument('--codex-baseline-model')
    parser.add_argument('--hermes-root', type=Path)
    parser.add_argument('--probe', action='store_true')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.probe and args.execute:
        parser.error('测量和真实执行不能同时使用')
    if args.client == 'dsh' and not args.dsh_modules:
        parser.error('需要当前 DSH 模块目录')
    if args.client == 'codex' and not (args.codex_baseline and args.codex_baseline_model):
        parser.error('需要当前 Codex 模型目录和基线模型')
    if args.client == 'hermes' and not args.hermes_root:
        parser.error('需要当前 Hermes 安装目录')
    config, models = snapshot(args.profile, args.strategy)
    input_limit = CODEX_INPUT_LIMIT if args.client == 'codex' else INPUT_LIMIT
    judge_limit = config['planningRouting'][args.strategy].get('maxJudgeOutputTokens', 1024)
    if judge_limit > MAX_BATCH_OUTPUT:
        raise ValueError('Judge 输出上限超过整批冻结范围')
    if any(m.input_cost_per_1k > .25 or m.output_cost_per_1k > .25 for m in models.values()):
        raise ValueError('模型价格已超出整批冻结的每千单位 0.25 AFP 上限')
    highest = max(models.values(), key=lambda m: m.input_cost_per_1k + m.output_cost_per_1k)
    upper = MAX_CALLS * (input_limit * highest.input_cost_per_1k
                         + max(EXECUTION_LIMIT, judge_limit) * highest.output_cost_per_1k) / 1000
    batch_upper = 2 * MAX_CALLS * (CODEX_INPUT_LIMIT * .25 + MAX_BATCH_OUTPUT * .25) / 1000
    batch_upper += 4 * MAX_CALLS * (INPUT_LIMIT * .25 + MAX_BATCH_OUTPUT * .25) / 1000
    if PRIOR_AFP_WORST_CASE + batch_upper >= AUTHORIZED_AFP:
        raise ValueError('整批保守上限超过累计 AFP 授权')
    frozen = json.dumps(config, ensure_ascii=False, sort_keys=True).encode()
    implementation = [Path('src/refractrouter/planning_config.py'),
                      Path('src/refractrouter/planning_runtime.py'),
                      Path('src/refractrouter/model_gateway.py'),
                      Path('validation/hermes/check_gateway.py'), Path(__file__)]
    core_digest = hashlib.sha256(b''.join(path.read_bytes() for path in implementation)).hexdigest()
    envelope = {'client': args.client, 'strategy': args.strategy,
        'configSha256': hashlib.sha256(frozen).hexdigest(), 'coreSha256': core_digest,
        'actualRoutes': {key: {'provider': m.provider, 'model': m.api_model,
            'reasoningEffort': m.request_options.get('reasoning_effort'),
            'billingUnit': m.billing_unit} for key, m in models.items()},
        'maxRemoteCalls': MAX_CALLS, 'maxInputBoundPerCall': input_limit,
        'maxExecutionOutputTokens': EXECUTION_LIMIT,
        'maxJudgeOutputTokens': judge_limit, 'timeoutMs': 300000,
        'upperBoundAfp': round(upper, 5),
        'allSixFlowsUpperBoundAfp': round(batch_upper, 5),
        'priorAfpWorstCase': PRIOR_AFP_WORST_CASE,
        'authorizedCumulativeAfp': AUTHORIZED_AFP,
        'httpRetries': 0, 'delegation': False}
    if not args.probe and not args.execute:
        args.output.mkdir(parents=True, exist_ok=False)
        (args.output / 'preflight.json').write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + '\n')
        (args.output / 'config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({'modelCalls': 0, **envelope}, ensure_ascii=False))
        return
    if json.loads((args.output / 'preflight.json').read_text()) != envelope:
        raise ValueError('配置或验收范围已变化，必须建立新批次')
    if args.execute and (args.output / 'started').exists():
        raise ValueError('同一批次禁止重复派发')
    if args.execute:
        (args.output / 'started').touch(exist_ok=False)

    observed = []
    class Bounded(HttpModelCaller):
        calls = 0

        def guard(self, action):
            if (self.calls >= MAX_CALLS or action['model']['provider'] != 'ark'
                    or action['model']['model'] not in {m.api_model for m in models.values()}):
                raise ValueError('模型调用超过冻结范围')
            limit = judge_limit if action['purpose'] in ('task', 'advisor') else EXECUTION_LIMIT
            if request_input_bound(action['messages'], action['tools']) > input_limit:
                raise ValueError('实际模型输入超过冻结包络')
            if action['model']['maxTokens'] > limit:
                raise ValueError('实际模型输出上限超过冻结包络')
            self.calls += 1

        def __call__(self, action, options):
            self.guard(action)
            return super().__call__(action, options)

        def stream(self, action, options, on_text):
            self.guard(action)
            return super().stream(action, options, on_text)

    class MeasuredGateway(ModelGateway):
        def complete(self, request, **kwargs):
            bound = request_input_bound(chat_messages(request['messages']),
                                        tool_schemas(request.get('tools', [])))
            observed.append({'inputBound': bound, 'tools': len(request.get('tools', [])),
                'toolResults': sum(row.get('role') == 'tool' for row in request['messages']),
                'reasoningEffort': request.get('reasoning_effort')})
            (args.output / 'request-bounds.json').write_text(json.dumps(observed, indent=2))
            if args.probe:
                raise ValueError('零调用测量完成')
            if bound > input_limit:
                raise ValueError('宿主请求超过冻结输入包络')
            return super().complete(request, **kwargs)

    caller = Bounded(config['providers'])
    gateway = MeasuredGateway(config, args.output / 'runs', caller)
    if args.probe:
        original_lower_tools = gateway_responses.lower_tools
        def inspect_tools(request):
            types = [{'type': tool.get('type'),
                'childTypes': [child.get('type') for child in tool.get('tools', [])]}
                for tool in request.get('tools', []) if isinstance(tool, dict)]
            (args.output / 'probe-tool-types.json').write_text(json.dumps(types, indent=2))
            return original_lower_tools(request)
        gateway_responses.lower_tools = inspect_tools
    server = create_server(gateway, port=0)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f'http://127.0.0.1:{server.server_port}/v1'
        command = command_for(args, base, gateway)
        result = subprocess.run(command, text=True, capture_output=True, timeout=310)
        prefix = 'probe-' if args.probe else ''
        (args.output / (prefix + 'client-stdout.txt')).write_text(result.stdout)
        (args.output / (prefix + 'client-stderr.txt')).write_text(result.stderr)
        records = [row for run in gateway.runtime.runs.values() for row in run['budget'].records]
        calls = [row for run in gateway.runtime.runs.values() for row in run['calls']]
        success = result.returncode == 0 and (
            'GATEWAY_CLIENT_OK' in result.stdout if args.client == 'codex' else True)
        summary = {'client': args.client, 'strategy': args.strategy,
            'success': success, 'exitCode': result.returncode,
            'remoteCalls': caller.calls, 'purposes': [row.get('purpose') for row in calls],
            'chargedAfp': round(sum(row['charged'] for row in records), 6),
            'statuses': [row['status'] for row in records],
            'routerTasks': len(gateway.runtime.runs),
            'hostToolResults': sum(row['toolResults'] for row in observed),
            'automaticRetries': 0}
        path = args.output / ('probe-summary.json' if args.probe else 'summary.json')
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(summary, ensure_ascii=False))
        if args.probe:
            if not observed or caller.calls:
                raise ValueError('零调用请求测量失败')
        elif not success:
            raise RuntimeError('真实接线失败；保留证据，不在同一批次重跑')
    finally:
        server.shutdown()
        server.server_close()
        gateway.close()
        if args.probe:
            gateway_responses.lower_tools = original_lower_tools


if __name__ == '__main__':
    main()
