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
from .application_config import SCHEMA, SCHEMA_V4, compile_configuration, migrate_v3_to_v4
from .routing_actions import action_identity
from .openai_compatible import write_host_record
from .route_observations import RouteObservationStore, local_observation_path


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
        from .ark_plan import application_configuration
        return application_configuration()
    return {'schemaVersion': SCHEMA, 'billingUnit': unit, 'qualityMin': 0, 'providers': [provider], 'models': models}


def main(argv=None):
    parser = argparse.ArgumentParser(prog='refractagent', description='RefractAgent 本地文本任务路由')
    commands = parser.add_subparsers(dest='command', required=True)
    models = commands.add_parser('models', help='列出策略；可校验用户模型配置，零调用')
    models.add_argument('--provider-config', type=Path)
    validate = commands.add_parser('validate-config', help='使用 Python 核心校验 provider/model 配置，零调用')
    validate_source = validate.add_mutually_exclusive_group(required=True)
    validate_source.add_argument('--provider-config', type=Path)
    validate_source.add_argument('--request-stdin', action='store_true')
    example = commands.add_parser('config-example', help='生成可编辑的 provider/model 配置示例')
    example.add_argument('--output', type=Path, required=True)
    migrate = commands.add_parser('migrate-config-v4', help='显式迁移 v3 provider 配置，不覆盖来源文件')
    migrate.add_argument('--input', type=Path, required=True)
    migrate.add_argument('--output', type=Path, required=True)
    migrate.add_argument('--planner-model-id', required=True)
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
    route_profiles = commands.add_parser('route-profiles', help='读取本地路线时延观测，零调用')
    route_profiles.add_argument('--runs-dir', type=Path,
                                default=Path.home()/'.local/share/refractagent/runs')
    setup = commands.add_parser('dsh-config', help='生成 DSH 配置覆盖文件；不修改现有用户配置')
    setup.add_argument('--output', type=Path, required=True)
    setup.add_argument('--runs-dir', type=Path, default=Path('.refractagent/runs'))
    setup.add_argument('--mode', choices=['demo', 'live'], default='demo')
    setup.add_argument('--production-budget', type=float, default=40)
    setup.add_argument('--evaluation-budget', type=float, default=80)
    setup.add_argument('--strategy', choices=(*PRESETS, 'auto'))
    setup.add_argument('--template', choices=['single', 'compare', 'auto'], default='single')
    setup_config = setup.add_mutually_exclusive_group()
    setup_config.add_argument('--provider-config', type=Path)
    setup_config.add_argument('--preset', choices=['ark-agent-plan'])
    setup.add_argument('--max-output-tokens', type=int, default=2048)
    setup.add_argument('--credential-env', help='仅覆盖 Ark 预设的凭证引用')
    setup.add_argument('--relax-budget', action='store_true',
                       help='生成放开预算拦截的配置；账本仍完整记录每次调用')
    setup.add_argument('--relax-context', action='store_true',
                       help='放开对话上下文上限；仍受各模型 contextWindow 约束')
    server = commands.add_parser('serve', help='启动 RefractRouter HTTP 服务；默认仅监听本机且禁止付费执行')
    server.add_argument('--host', default='127.0.0.1')
    server.add_argument('--port', type=int, default=8787)
    server.add_argument('--runs-dir', type=Path, default=Path.home()/'.local/share/refractagent/runs')
    server.add_argument('--auth-token-env', help='Bearer token 的环境变量名称；非回环监听时必填')
    server.add_argument('--service-config', type=Path,
                        help='团队项目、成员 token 引用与 SQLite 状态配置；启用 HTTP v2')
    server.add_argument('--production-budget', type=float, default=40)
    server.add_argument('--evaluation-budget', type=float, default=80)
    server.add_argument('--timeout-ms', type=int, default=300000)
    server.add_argument('--max-output-tokens', type=int, default=128000)
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
        if args.command == 'migrate-config-v4':
            data = migrate_v3_to_v4(json.loads(args.input.read_text()), planner_model_id=args.planner_model_id)
            compile_configuration(data)
            with args.output.open('x') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
            print(json.dumps({'source': str(args.input.resolve()), 'config': str(args.output.resolve()),
                              'model_calls': 0}, ensure_ascii=False))
            return 0
        if args.command == 'models':
            exposed = PRESETS
            compiled = None
            if args.provider_config:
                raw = json.loads(args.provider_config.read_text())
                compiled = compile_configuration(raw)
                if raw.get('schemaVersion') == SCHEMA_V4:
                    exposed = {'auto': {'name': '自动路由'}}
            result = {'provider': 'refractagent', 'policy_version': POLICY_VERSION,
                'models': [{'id': key, 'name': 'RefractAgent · '+p['name'],
                            'description': '按用户配置的可用模型进行文本任务路由。'} for key,p in exposed.items()]}
            if compiled is not None:
                result['available_models'] = [{**action_identity(m), 'role': m.role,
                                               **({'roles': list(m.roles)} if m.roles else {})}
                                              for m in compiled.manifest.models]
                result['billing_unit'] = compiled.manifest.billing_unit
                for key in ('defaultReasoningEffort', 'strategies'):
                    if key in raw:
                        result[key] = raw[key]
            print(json.dumps(result, ensure_ascii=False))
            return 0
        if args.command == 'validate-config':
            try:
                raw = (json.loads(args.provider_config.read_text()) if args.provider_config else
                       json.loads(sys.stdin.read(2097153)))
                compiled = compile_configuration(raw)
            except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
                print(json.dumps({
                    'schema_version': 'refractagent-config-validation-v1',
                    'valid': False,
                    'error': str(exc)[:500],
                    'model_calls': 0,
                }, ensure_ascii=False))
                return 1
            role_counts = {
                role: sum(role in model.roles for model in compiled.manifest.models)
                for role in ('planner', 'worker', 'judge', 'classifier')
            }
            credential_references = sorted({
                provider['credentialEnv'] for provider in raw.get('providers', [])
                if isinstance(provider, dict) and isinstance(provider.get('credentialEnv'), str)
            })
            print(json.dumps({
                'schema_version': 'refractagent-config-validation-v1',
                'valid': True,
                'config_schema': raw.get('schemaVersion'),
                'provider_count': len(raw.get('providers', [])),
                'model_count': len(raw.get('models', [])),
                'role_counts': role_counts,
                'credential_references': credential_references,
                'model_calls': 0,
            }, ensure_ascii=False))
            return 0
        if args.command == 'show':
            print((args.run_dir/'summary.json').read_text())
            return 0
        if args.command == 'route-profiles':
            store = RouteObservationStore(local_observation_path(args.runs_dir))
            print(json.dumps(store.catalog(), ensure_ascii=False))
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
            provider_schema = None
            if args.provider_config:
                raw = json.loads(args.provider_config.read_text())
                compile_configuration(raw)
                config['providerConfig'] = raw
                provider_schema = raw.get('schemaVersion')
            if args.preset:
                config.update(preset=args.preset, credentialEnv=args.credential_env or 'CODEX_ARK_API_KEY')
            elif args.credential_env:
                raise ValueError('--credential-env applies only to --preset ark-agent-plan')
            if args.relax_budget or args.relax_context:
                config['limits'] = {'relaxBudget': args.relax_budget, 'relaxContext': args.relax_context}
            if args.mode=='live' and not (args.provider_config or args.preset):
                raise ValueError('live configuration requires --provider-config or an explicit --preset')
            strategy = args.strategy or ('auto' if provider_schema == SCHEMA_V4 else 'balanced')
            if (provider_schema == SCHEMA_V4) != (strategy == 'auto'):
                raise ValueError('v4 provider configuration requires strategy auto; v1-v3 use legacy strategies')
            patch = [{'id': 'refractagent', 'config': config},
                     {'id': 'agent-default-model', 'config': {'provider': 'refractagent', 'model': strategy}}]
            with args.output.open('x') as stream:
                json.dump(patch, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
            print(json.dumps({'config': str(args.output.resolve()), 'paid_enabled': False}))
            return 0
        if args.command == 'serve':
            from .agent_server import ServerConfiguration, serve
            from .team_service import load_team_configuration
            if not 1 <= args.port <= 65535:
                raise ValueError('port must be in 1..65535')
            if args.auth_token_env is not None and not args.auth_token_env.isidentifier():
                raise ValueError('invalid auth token environment reference')
            team = (load_team_configuration(args.service_config, default_runs_dir=args.runs_dir)
                    if args.service_config is not None else None)
            serve(host=args.host, port=args.port, config=ServerConfiguration(
                runs_dir=args.runs_dir, auth_token_env=args.auth_token_env,
                production_budget=args.production_budget, evaluation_budget=args.evaluation_budget,
                timeout_ms=args.timeout_ms, max_output_tokens=args.max_output_tokens, team=team))
            return 0
        if args.host_stdio:
            if os.environ.get('REFRACTROUTER_DSH_BRIDGE') != 'stdio':
                raise ValueError('host stdio requires the DSH plugin')
            payload = json.loads(sys.stdin.readline(2097153))
        else:
            payload = (json.loads(args.request_file.read_text()) if args.request_file else
                       json.loads(sys.stdin.read(262145)) if args.request_stdin else
                       {'task': args.task, 'strategy': args.strategy, 'template': args.template})
        provider_config = json.loads(args.provider_config.read_text()) if args.provider_config else None
        model_profile_provenance = None
        route_observation_path = local_observation_path(args.runs_dir)
        if isinstance(payload, dict) and 'providerConfig' in payload:
            if provider_config is not None or args.preset:
                raise ValueError('conflicting provider configuration sources')
            provider_config = payload.pop('providerConfig')
        if isinstance(payload, dict) and ('dshModelPool' in payload or 'dshCatalogSnapshot' in payload):
            if provider_config is not None or args.preset or 'dshModelPool' not in payload or 'dshCatalogSnapshot' not in payload:
                raise ValueError('conflicting or incomplete DSH model pool configuration')
            from .dsh_model_pool import compile_dsh_model_pool
            provider_config, model_profile_provenance = compile_dsh_model_pool(
                payload.pop('dshModelPool'), payload.pop('dshCatalogSnapshot'),
                latency_profiles=RouteObservationStore(route_observation_path).latency_profiles())
        tool_runtime = None
        if isinstance(payload, dict) and 'hostTools' in payload:
            if not args.host_stdio:
                raise ValueError('host tools require the host stdio channel')
            from .tool_runtime import StdioToolRuntime
            from .openai_compatible import DshStdioBridge
            tool_runtime = StdioToolRuntime(payload.pop('hostTools'), DshStdioBridge())
        cancelled = Event()
        previous = {sig: signal.signal(sig, lambda *_: cancelled.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            result = run_agent(payload, mode=args.mode, runs_dir=args.runs_dir,
                production_budget=args.production_budget, evaluation_budget=args.evaluation_budget,
                timeout_ms=args.timeout_ms, max_output_tokens=args.max_output_tokens,
                manifest_path=args.manifest, profile_path=args.profile,
                execute_paid_run=args.execute_paid_run, cancel_event=cancelled,
                provider_config=provider_config, preset=args.preset, tool_runtime=tool_runtime,
                progress=write_host_record if args.progress_stdio else None,
                model_profile_provenance=model_profile_provenance,
                route_observation_path=route_observation_path)
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
