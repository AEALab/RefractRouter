"""Installed application CLI; user provider configuration stays independent of DSH."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import sys
from threading import Event

from .agent import PRESETS, POLICY_VERSION, resource, run_agent
from .application_config import SCHEMA, compile_configuration
from .routing_actions import action_identity


def example_configuration(kind):
    provider = {'id': 'team', 'type': kind}
    if kind == 'dsh':
        provider['dshProvider'] = 'YOUR_DSH_PROVIDER_ID'
    else:
        provider.update(baseUrl='https://your-provider.example/v1', credentialEnv='TEAM_MODEL_KEY')
    models = []
    for mid, role in [('answer', 'candidate'), ('review', 'judge')]:
        models.append({'id': mid, 'provider': 'team', 'model': 'YOUR_MODEL_ID' if role=='candidate' else 'YOUR_JUDGE_MODEL_ID',
            'role': role, 'contextWindow': 32768, 'maxOutputTokens': 2048,
            'pricing': {'unit': 'USD', 'inputPer1k': .001, 'outputPer1k': .002},
            **({'routing': {'quality': 85, 'latencyMs': 10000}} if role=='candidate' else {})})
    if kind == 'openai-responses':
        provider.update(baseUrl='https://api.openai.com/v1', credentialEnv='OPENAI_API_KEY')
        for model in models:
            model.update(contextWindow=131072, maxOutputTokens=32768,
                         requestOptions={'reasoning': {'effort': 'medium'}})
    unit = 'USD'
    if kind == 'ark-agent-plan':
        source = json.loads(resource('agent-plan.json').read_text())
        provider = {'id': 'ark-plan', 'type': kind, 'credentialEnv': 'CODEX_ARK_API_KEY'}
        unit = 'AFP'
        models = []
        for m in source['models']:
            models.append({'id': m['model_id'], 'provider': 'ark-plan', 'model': m['api_model'], 'role': m['role'],
                'contextWindow': source['defaults']['context_window'], 'maxOutputTokens': 2048,
                'jsonMode': m.get('json_mode_strategy', 'json-object-hint'),
                'requestOptions': source['defaults']['request_options'],
                'pricing': {'unit': unit, 'inputPer1k': m['input_cost_per_1k'], 'outputPer1k': m['output_cost_per_1k'],
                            'cachedInputPer1k': m['cached_input_cost_per_1k']},
                **({'routing': {'quality': round(m['capability']*100), 'latencyMs': 10000}} if m['role']=='candidate' else {})})
    return {'schemaVersion': SCHEMA, 'billingUnit': unit, 'qualityMin': 0, 'providers': [provider], 'models': models}


def main(argv=None):
    parser = argparse.ArgumentParser(prog='refractagent', description='RefractAgent 本地文本任务路由')
    commands = parser.add_subparsers(dest='command', required=True)
    models = commands.add_parser('models', help='列出策略；可校验用户模型配置，零调用')
    models.add_argument('--provider-config', type=Path)
    example = commands.add_parser('config-example', help='生成可编辑的 provider/model 配置示例')
    example.add_argument('--output', type=Path, required=True)
    example.add_argument('--provider-type', choices=['openai-compatible', 'openai-responses', 'dsh', 'ark-agent-plan'], default='openai-compatible')
    run = commands.add_parser('run', help='执行文本任务，默认零调用预检')
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument('--task')
    source.add_argument('--request-file', type=Path)
    source.add_argument('--request-stdin', action='store_true')
    source.add_argument('--host-stdio', action='store_true', help=argparse.SUPPRESS)
    run.add_argument('--strategy', choices=tuple(PRESETS), default='balanced')
    run.add_argument('--template', choices=['single', 'compare', 'auto'], default='single')
    run.add_argument('--mode', choices=['preflight', 'demo', 'live'], default='preflight')
    run.add_argument('--runs-dir', type=Path, default=Path.home()/'.local/share/refractagent/runs')
    run.add_argument('--production-budget', type=float, default=40)
    run.add_argument('--evaluation-budget', type=float, default=80)
    run.add_argument('--timeout-ms', type=int, default=300000)
    run.add_argument('--max-output-tokens', type=int, default=2048)
    run.add_argument('--manifest', type=Path)
    run.add_argument('--profile', type=Path)
    run_config = run.add_mutually_exclusive_group()
    run_config.add_argument('--provider-config', type=Path)
    run_config.add_argument('--preset', choices=['ark-agent-plan'])
    run.add_argument('--execute-paid-run', action='store_true')
    run.add_argument('--progress-stdio', action='store_true', help='输出脱敏节点进度 NDJSON，最后一行为完整结果')
    inspect = commands.add_parser('show', help='查看已保存任务的策略、模型、结果和费用')
    inspect.add_argument('run_dir', type=Path)
    setup = commands.add_parser('dsh-config', help='生成 DSH 配置覆盖文件；不修改现有用户配置')
    setup.add_argument('--output', type=Path, required=True)
    setup.add_argument('--runs-dir', type=Path, default=Path('.refractagent/runs'))
    setup.add_argument('--mode', choices=['demo', 'live'], default='demo')
    setup.add_argument('--production-budget', type=float, default=40)
    setup.add_argument('--evaluation-budget', type=float, default=80)
    setup.add_argument('--strategy', choices=tuple(PRESETS), default='balanced')
    setup.add_argument('--template', choices=['single', 'compare', 'auto'], default='single')
    setup_config = setup.add_mutually_exclusive_group()
    setup_config.add_argument('--provider-config', type=Path)
    setup_config.add_argument('--preset', choices=['ark-agent-plan'])
    setup.add_argument('--max-output-tokens', type=int, default=2048)
    setup.add_argument('--credential-env', help='仅覆盖 Ark 预设的凭证引用')
    args = parser.parse_args(argv)
    try:
        if args.command == 'config-example':
            data = example_configuration(args.provider_type)
            compile_configuration(data)
            with args.output.open('x') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
            print(json.dumps({'config': str(args.output.resolve()), 'requires_user_configuration': True, 'model_calls': 0}))
            return 0
        if args.command == 'models':
            result = {'provider': 'refractagent', 'policy_version': POLICY_VERSION,
                'models': [{'id': key, 'name': 'RefractAgent · '+p['name'],
                            'description': '按用户配置的可用模型进行文本任务路由。'} for key,p in PRESETS.items()]}
            if args.provider_config:
                compiled = compile_configuration(json.loads(args.provider_config.read_text()))
                result['available_models'] = [{**action_identity(m), 'role': m.role}
                                              for m in compiled.manifest.models]
                result['billing_unit'] = compiled.manifest.billing_unit
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.command == 'show':
            print((args.run_dir/'summary.json').read_text())
            return 0
        if args.command == 'dsh-config':
            from .node_routing import number
            number(args.production_budget, 'production budget', positive=True)
            number(args.evaluation_budget, 'evaluation budget', positive=True)
            if not 1000 <= args.max_output_tokens <= 128000:
                raise ValueError('output cap must be an integer in 1000..128000')
            config = {'pythonExecutable': sys.executable, 'executionMode': args.mode,
                      'runsDir': str(args.runs_dir.expanduser().resolve()), 'allowPaidRuns': False,
                      'maxOutputTokens': args.max_output_tokens,
                      'template': args.template,
                      'maxProductionCost': args.production_budget, 'maxEvaluationCost': args.evaluation_budget}
            if args.provider_config:
                raw = json.loads(args.provider_config.read_text())
                compile_configuration(raw)
                config['providerConfig'] = raw
            if args.preset:
                config.update(preset=args.preset, credentialEnv=args.credential_env or 'CODEX_ARK_API_KEY')
            elif args.credential_env:
                raise ValueError('--credential-env applies only to --preset ark-agent-plan')
            if args.mode=='live' and not (args.provider_config or args.preset):
                raise ValueError('live configuration requires --provider-config or an explicit --preset')
            patch = [{'id': 'refractagent', 'config': config},
                     {'id': 'agent-default-model', 'config': {'provider': 'refractagent', 'model': args.strategy}}]
            with args.output.open('x') as stream:
                json.dump(patch, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
            print(json.dumps({'config': str(args.output.resolve()), 'paid_enabled': False}))
            return 0
        if args.host_stdio:
            if os.environ.get('REFRACTROUTER_DSH_BRIDGE') != 'stdio':
                raise ValueError('host stdio requires the DSH plugin')
            payload = json.loads(sys.stdin.readline(262145))
        else:
            payload = (json.loads(args.request_file.read_text()) if args.request_file else
                       json.loads(sys.stdin.read(262145)) if args.request_stdin else
                       {'task': args.task, 'strategy': args.strategy, 'template': args.template})
        provider_config = json.loads(args.provider_config.read_text()) if args.provider_config else None
        if isinstance(payload, dict) and 'providerConfig' in payload:
            if provider_config is not None or args.preset:
                raise ValueError('conflicting provider configuration sources')
            provider_config = payload.pop('providerConfig')
        cancelled = Event()
        previous = {sig: signal.signal(sig, lambda *_: cancelled.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            result = run_agent(payload, mode=args.mode, runs_dir=args.runs_dir,
                production_budget=args.production_budget, evaluation_budget=args.evaluation_budget,
                timeout_ms=args.timeout_ms, max_output_tokens=args.max_output_tokens,
                manifest_path=args.manifest, profile_path=args.profile,
                execute_paid_run=args.execute_paid_run, cancel_event=cancelled,
                provider_config=provider_config, preset=args.preset,
                progress=(lambda event: print(json.dumps(event, ensure_ascii=False), flush=True))
                         if args.progress_stdio else None)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0 if result['status'] in {'preview', 'simulated', 'completed', 'quality-failed'} else 1
    except Exception as exc:
        detail = str(exc)[:500] if isinstance(exc, (ValueError, FileExistsError, FileNotFoundError)) else type(exc).__name__
        print(json.dumps({'schema_version': 'refractagent-error-v1', 'error': detail}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
