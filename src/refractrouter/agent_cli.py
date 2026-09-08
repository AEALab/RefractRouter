"""Installed application CLI; no checkout paths or benchmark dependencies required."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import sys
from threading import Event

from .agent import PRESETS, POLICY_VERSION, run_agent


def main(argv=None):
    parser = argparse.ArgumentParser(prog='refractagent', description='RefractAgent 本地文本任务路由')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('models', help='列出三个策略；零调用')
    run = commands.add_parser('run', help='执行文本任务，默认零调用预检')
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument('--task')
    source.add_argument('--request-file', type=Path)
    source.add_argument('--request-stdin', action='store_true')
    run.add_argument('--strategy', choices=tuple(PRESETS), default='balanced')
    run.add_argument('--template', choices=['single', 'compare'], default='single')
    run.add_argument('--mode', choices=['preflight', 'demo', 'live'], default='preflight')
    run.add_argument('--runs-dir', type=Path, default=Path.home()/'.local/share/refractagent/runs')
    run.add_argument('--production-budget', type=float, default=40)
    run.add_argument('--evaluation-budget', type=float, default=80)
    run.add_argument('--timeout-ms', type=int, default=300000)
    run.add_argument('--max-output-tokens', type=int, default=2048)
    run.add_argument('--manifest', type=Path)
    run.add_argument('--profile', type=Path)
    run.add_argument('--execute-paid-run', action='store_true')
    inspect = commands.add_parser('show', help='查看已保存任务的策略、模型、结果和费用')
    inspect.add_argument('run_dir', type=Path)
    setup = commands.add_parser('dsh-config', help='生成 DSH 配置覆盖文件；不修改现有用户配置')
    setup.add_argument('--output', type=Path, required=True)
    setup.add_argument('--runs-dir', type=Path, required=True)
    setup.add_argument('--mode', choices=['demo', 'live'], default='demo')
    setup.add_argument('--production-budget', type=float, default=40)
    setup.add_argument('--evaluation-budget', type=float, default=80)
    setup.add_argument('--strategy', choices=tuple(PRESETS), default='balanced')
    setup.add_argument('--credential-env', default='CODEX_ARK_API_KEY')
    args = parser.parse_args(argv)
    try:
        if args.command == 'models':
            print(json.dumps({'provider': 'refractagent', 'policy_version': POLICY_VERSION,
                'models': [{'id': key, 'name': 'RefractAgent · '+p['name'],
                            'description': '文本任务路由；质量为预测偏好，实际结果单独评估。'}
                           for key,p in PRESETS.items()]}, ensure_ascii=False))
            return 0
        if args.command == 'show':
            print((args.run_dir/'summary.json').read_text())
            return 0
        if args.command == 'dsh-config':
            from .node_routing import number
            number(args.production_budget, 'production budget', positive=True)
            number(args.evaluation_budget, 'evaluation budget', positive=True)
            # JSON is valid YAML, so quoting stays correct for spaces and Unicode paths.
            config = {'pythonExecutable': sys.executable, 'executionMode': args.mode,
                      'runsDir': str(args.runs_dir.expanduser().resolve()),
                      'allowPaidRuns': False, 'maxProductionCost': args.production_budget,
                      'maxEvaluationCost': args.evaluation_budget, 'credentialEnv': args.credential_env}
            patch = [{'id': 'refractagent', 'config': config},
                     {'id': 'agent-default-model', 'config': {'provider': 'refractagent', 'model': args.strategy}}]
            # The DSH patch syntax is verified by its real profile loader in integration tests.
            with args.output.open('x') as stream:
                json.dump(patch, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
            print(json.dumps({'config': str(args.output.resolve()), 'paid_enabled': False}))
            return 0
        payload = (json.loads(args.request_file.read_text()) if args.request_file else
                   json.loads(sys.stdin.read(262145)) if args.request_stdin else
                   {'task': args.task, 'strategy': args.strategy, 'template': args.template})
        cancelled = Event()
        previous = {sig: signal.signal(sig, lambda *_: cancelled.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            result = run_agent(payload, mode=args.mode, runs_dir=args.runs_dir,
                production_budget=args.production_budget, evaluation_budget=args.evaluation_budget,
                timeout_ms=args.timeout_ms, max_output_tokens=args.max_output_tokens,
                manifest_path=args.manifest, profile_path=args.profile,
                execute_paid_run=args.execute_paid_run, cancel_event=cancelled)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0 if result['status'] in {'preview', 'simulated', 'completed', 'quality-failed'} else 1
    except Exception as exc:
        # Provider exception bodies and credentials are never emitted by this boundary.
        detail = str(exc)[:500] if isinstance(exc, (ValueError, FileExistsError, FileNotFoundError)) else type(exc).__name__
        print(json.dumps({'schema_version': 'refractagent-error-v1', 'error': detail}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
