"""显式模型排列的交接验证；不将指定异构组合解释为路由收益。"""
from dataclasses import asdict
import hashlib
from itertools import permutations
import json
from pathlib import Path
import time

from .dag_study import implementation_fingerprint, validate_implementation
from .dag_study_execution import StudyDemoClient, write_json
from .manifest import load_model_manifest
from .task_budget import TaskCallBudget
from .task_evaluation import evaluate_text
from .task_execution import execute_nodes
from .task_plan import validate_plan
from .task_runtime import validate_models
from .task_scheduling import ExecutionPolicy


def load_handoff(path):
    path = Path(path)
    raw = json.loads(path.read_text())
    if raw.get('schema_version') != 'dag-handoff-validation-v1':
        raise ValueError('unsupported handoff protocol')
    validate_implementation(raw)
    manifest_path = path.parent / raw['manifest_path']
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != raw['manifest_sha256']:
        raise ValueError('frozen manifest changed')
    manifest = load_model_manifest(manifest_path)
    validate_models(manifest)
    if manifest.billing_unit != 'AFP' or any(m.provider != 'ark-plan' for m in manifest.models):
        raise ValueError('handoff requires Agent Plan')
    plan = validate_plan(raw['plan'], require_v2=True)
    ids = [m.model_id for m in manifest.candidates]
    if len(ids) != 3 or len(plan.nodes) != 3 or not isinstance(raw.get('task'), str) or not raw['task'].strip():
        raise ValueError('handoff requires three candidates and three nodes')
    expected = [dict(zip(plan.order(), mids)) for mids in permutations(ids)]
    if raw.get('assignments') != expected:
        raise ValueError('handoff requires all six frozen model permutations')
    policy = ExecutionPolicy.from_request(raw['execution_policy'])
    if raw.get('failure_policy') != 'stop-on-first-failure' or raw.get('maximum_calls') != 24:
        raise ValueError('invalid handoff stopping rule')
    if raw.get('deadline_ms') != 300000 or raw.get('minimum_quality') != 80:
        raise ValueError('invalid handoff acceptance')
    candidates = {m.model_id: m for m in manifest.candidates}
    def cost(model, cap):
        output = min(model.max_output_tokens, 8192)
        if cap + output > model.context_window:
            raise ValueError('handoff context envelope exceeded')
        return cap/1000*model.input_cost_per_1k + output/1000*model.output_cost_per_1k
    production = sum(cost(candidates[mid], plan.contracts[nid]['capability']['input_budget_tokens'])
                     for assignments in expected for nid, mid in assignments.items())
    evaluation = 6 * cost(manifest.judge, 65536)
    preflight = {'status': 'preflight', 'real_model_calls': 0, 'maximum_calls': 24,
                 'protocol_sha256': hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                 'production_limit': round(production, 6), 'evaluation_limit': round(evaluation, 6),
                 'purpose': '验证指定模型组合的真实交接与最终语义，不证明自动选路或路由收益。'}
    return raw, manifest, plan, policy, preflight


def run_handoff(loaded, output_dir, *, client=None, simulated=True, production_limit=None, evaluation_limit=None):
    raw, manifest, plan, policy, preflight = loaded
    validate_implementation(raw)
    if not simulated and (client is None or client.max_retries != 0
            or production_limit is None or production_limit < preflight['production_limit']
            or evaluation_limit is None or evaluation_limit < preflight['evaluation_limit']):
        raise ValueError('handoff requires zero retries and complete admission envelope')
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)
    write_json(out/'protocol.json', raw)
    write_json(out/'manifest.json', asdict(manifest))
    write_json(out/'preflight.json', preflight)
    write_json(out/'implementation.json', implementation_fingerprint())
    budget = TaskCallBudget(StudyDemoClient() if simulated else client,
                           1e12 if simulated else production_limit,
                           1e12 if simulated else evaluation_limit,
                           capture_payload=True, max_calls=24)
    candidates = {m.model_id: m for m in manifest.candidates}
    result = {'status': 'started', 'simulated': simulated, 'runs': [], 'issues': [],
              'routing_benefit': None, 'assignment_origin': 'frozen-validation-permutations'}
    def persist():
        result['charged'], result['calls'] = budget.snapshot()
        write_json(out/'result.json', result)
    budget.on_reserve = lambda _: persist()
    def archive_response(row, response):
        write_json(out/(hashlib.sha256(row['label'].encode()).hexdigest()+'-response.json'),
                   {'label': row['label'], **asdict(response)})
    budget.on_response = archive_response
    try:
        for i, assignments in enumerate(raw['assignments'], 1):
            run = {'id': i, 'assignments': assignments, 'status': 'started', 'nodes': [],
                   'final_output': '', 'evaluation': None}
            result['runs'].append(run)
            start = time.monotonic()
            deadline = start + raw['deadline_ms']/1000
            try:
                run['final_output'] = execute_nodes(plan, raw['task'], assignments, candidates, budget,
                    policy, run, persist, started=start, deadline=deadline, label_prefix=f'handoff-{i}:')
                run['evaluation'] = evaluate_text(budget, manifest.judge, raw['task'], run['final_output'],
                    criteria=plan.acceptance_criteria, label=f'handoff-{i}:judge', deadline=deadline)
                if time.monotonic() > deadline:
                    raise ValueError('handoff deadline exceeded')
                if not run['evaluation']['passed'] or run['evaluation']['score'] < raw['minimum_quality']:
                    run['status'] = 'quality-failed'
                    raise ValueError('handoff final quality failed')
                run['status'] = 'simulated' if simulated else 'completed'
            except Exception:
                if run['status'] == 'started':
                    run['status'] = 'failed'
                raise
            finally:
                run['wall_time_ms'] = (time.monotonic()-start)*1000
                persist()
        result['status'] = 'simulated' if simulated else 'completed'
    except Exception as exc:
        budget.stop()
        result['status'] = 'failed'
        result['issues'] = [str(exc) if isinstance(exc, ValueError) else type(exc).__name__]
    finally:
        persist()
        write_json(out/'artifact-index.json', {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(out.iterdir()) if p.is_file() and p.name != 'artifact-index.json'})
    return result
