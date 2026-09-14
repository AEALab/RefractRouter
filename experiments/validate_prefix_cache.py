"""前缀缓存开发诊断：默认零调用冻结，不替代质量准入或正式 Pareto 实验。"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict, replace
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import time
from threading import RLock

from refractrouter.agent import atomic_json, plan_template, run_agent
from refractrouter.application_config import compile_configuration
from refractrouter.ark_plan import application_configuration
from refractrouter.openai_compatible import OpenAICompatibleClient
from refractrouter.task_budget import TaskCallBudget, InvalidModelOutput
from refractrouter.task_execution import node_messages
from refractrouter.task_plan import validate_plan

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'data/research/prefix-cache-v1.json'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def freeze(protocol_path=PROTOCOL):
    protocol = json.loads(protocol_path.read_text())
    files = sorted((ROOT / 'src/refractrouter').rglob('*.py')) + sorted((ROOT / 'src/refractrouter/resources').rglob('*.json'))
    files += [Path(__file__), protocol_path, ROOT / 'uv.lock', ROOT / 'pyproject.toml']
    raw = {'protocol': protocol, 'source_hashes': {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    return {**raw, 'sha256': fingerprint(raw)}


def probe_messages(task, index, policy):
    plan = validate_plan(plan_template('single', ['准确核对所有材料，保留证据与限制']))
    node = replace(plan.nodes[0], node_id=f'check_{index}')
    return node_messages(task, node, plan.contracts['answer'], {}, prefix_policy=policy)


class LimitedClient:
    """在共享锁下约束整批实际调用，账本另由核心原子预留。"""
    max_retries = 0
    def __init__(self, client, cap):
        from threading import Lock
        self.client, self.cap, self.calls, self.lock = client, cap, 0, Lock()
    def complete(self, *args, **kwargs):
        with self.lock:
            if self.calls >= self.cap:
                raise ValueError('诊断批次达到调用上限')
            self.calls += 1
        return self.client.complete(*args, **kwargs)
    def for_task_call(self, timeout):
        parent = self
        class Bound:
            def complete(self, *args, **kwargs):
                with parent.lock:
                    if parent.calls >= parent.cap:
                        raise ValueError('诊断批次达到调用上限')
                    parent.calls += 1
                return parent.client.for_task_call(timeout).complete(*args, **kwargs)
        return Bound()


def execute(frozen, output, client=None):
    p = frozen['protocol']
    client = LimitedClient(client or OpenAICompatibleClient(max_retries=0, timeout_seconds=None), p['maximum_calls'])
    config = p['configuration']
    models = compile_configuration(config).manifest.models
    budget = TaskCallBudget(client, p['probe_afp_ceiling'], 1, max_calls=32, capture_payload=True)
    rows, applications = [], []
    begin = time.monotonic()
    persist_lock = RLock()
    def persist():
        with persist_lock:
            charged, calls = budget.snapshot()
            atomic_json(output / 'probe-ledger.json', {'charged': charged, 'calls': calls})
    budget.on_reserve = lambda _: persist()
    def invoke(model, policy, phase, task, index):
        label = f'{model.model_id}/{policy}/{phase}/{index}'
        start = time.monotonic()
        error = None
        try:
            budget.complete(model, probe_messages(task, index, policy), label=label,
                            timeout_seconds=p['per_request_timeout_seconds'])
        except InvalidModelOutput as exc:
            error = str(exc)  # 用量已知的失败保留，继续独立诊断。
        finally:
            persist()
        return {'label': label, 'provider': model.provider, 'model': model.api_model,
                'wire_api': model.wire_api, 'prefix_policy': policy, 'phase': phase,
                'cold_state': 'unconfirmed', 'ttft_ms': None,
                'start_ms': (start-begin)*1000, 'end_ms': (time.monotonic()-begin)*1000,
                'error': error}
    try:
        for m_index, model in enumerate(models):
            policies = ['legacy', 'stable-v1'] if m_index % 2 == 0 else ['stable-v1', 'legacy']
            for policy in policies:
                print(f'缓存诊断 {model.api_model} {policy}', flush=True)
                # 独立并发探针先派发；不等待一次完成来人为预热。
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(invoke, model, policy, 'first-concurrent', p['concurrent_task'], n)
                               for n in (0, 1)]
                    errors = []
                    for future in futures:
                        try:
                            rows.append(future.result())
                        except Exception as exc:
                            errors.append(exc)
                    if errors:
                        raise errors[0]  # 在途调用全部结算后整批停止。
                for n, phase in ((2, 'first-sequential'), (3, 'repeat-prefix')):
                    rows.append(invoke(model, policy, phase, p['sequential_task'], n))
                atomic_json(output / 'probes.json', rows)
        for item in p['application_runs']:
            print('同图/直接对照', item['id'], flush=True)
            result = run_agent(item['payload'], provider_config=p['application_configuration'],
                client=client, mode='live', execute_paid_run=True, runs_dir=output / item['id'],
                production_budget=p['application_production_afp'], evaluation_budget=p['application_evaluation_afp'],
                timeout_ms=p['application_timeout_ms'], max_output_tokens=8192)
            applications.append({'id': item['id'], **result})
            atomic_json(output / 'applications.json', applications)
            if result['costs']['unconfirmed'] or result['status'] in {'failed', 'cancelled'}:
                raise RuntimeError('用量、认证、执行或证据异常；停止整批')
    finally:
        persist()
        atomic_json(output / 'probes.json', rows)
        atomic_json(output / 'run-status.json', {'actual_calls': client.calls,
            'wall_time_ms': (time.monotonic()-begin)*1000,
            'completed_probes': len(rows), 'completed_application_runs': len(applications),
            'human_quality_verified': False, 'cache_discount_verified': False})
        atomic_json(output / 'artifact-index.json', {str(f.relative_to(output)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted(output.rglob('*')) if f.is_file() and f.name != 'artifact-index.json'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--freeze-sha256')
    args = parser.parse_args()
    frozen = freeze()
    if args.execute and args.freeze_sha256 != frozen['sha256']:
        parser.error('必须绑定当前源码、材料、配置与协议的 SHA256')
    args.output_dir.mkdir(parents=True, exist_ok=False)
    atomic_json(args.output_dir / 'frozen.json', frozen)
    if not args.execute:
        print(json.dumps({'sha256': frozen['sha256'], 'maximum_calls': frozen['protocol']['maximum_calls']}))
        return
    with tarfile.open(args.output_dir / 'source.tar.gz', 'w:gz') as archive:
        for name in frozen['source_hashes']:
            archive.add(ROOT / name, arcname=name)
    execute(frozen, args.output_dir)


if __name__ == '__main__':
    main()
