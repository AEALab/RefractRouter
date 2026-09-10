"""研究运行器的共享账本、规划缓存与逐样本执行；正式研究编排由上层冻结。"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
from threading import RLock
import time

from .dag_batch_study import recoverable
from .dag_study_execution import direct_plan, write_json
from .model_selection import Weights
from .node_routing import route_nodes
from .research_protocol import PLAN_CRITERIA, digest
from .responses_api import output_token_limit
from .task_budget import TaskCallBudget, InvalidModelOutput
from .task_contracts import decode_output
from .task_evaluation import evaluate_text
from .task_execution import execute_nodes, node_messages, RecoveryEligibleFailure
from .task_plan import PLANNER_SYSTEM, validate_plan
from .task_scheduling import ExecutionPolicy


class PlanRejected(ValueError):
    """规划输出已结算，但不满足冻结的结构、交付条件或容量要求。"""


class EvidenceFailure(RuntimeError):
    """证据写入异常必须停止整批，不能作为模型输出失败继续。"""


def delivery_task(task):
    """把评分所用原始条目显式传给每条执行路线，避免规划路线独享条件。"""
    return task['task'] + '\n\n固定交付验收条件（按节点职责处理，最终交付须全部满足）：\n' + '\n'.join(
        f'{index}. {criterion}' for index, criterion in enumerate(task['criteria'], 1))


class ResearchSession:
    """顺序编排样本，样本内允许有界并发；所有尝试共用一个预算。"""

    def __init__(self, manifest, config, output_dir, client, *, production_limit,
                 evaluation_limit, max_calls, simulated):
        if getattr(client, 'max_retries', None) != 0:
            raise ValueError('research requires zero HTTP retries')
        if config['max_node_fallbacks'] != 0 or config['planner_repairs'] != 0:
            raise ValueError('research session requires zero recovery and repairs')
        if type(max_calls) is not int or max_calls < 1:
            raise ValueError('invalid call envelope')
        self.manifest, self.config = manifest, deepcopy(config)
        self.models = {m.model_id: m for m in manifest.candidates}
        self.policy = ExecutionPolicy.from_request(config['execution_policy'])
        self.out = Path(output_dir)
        self.out.mkdir(parents=True, exist_ok=False)
        (self.out / 'calls').mkdir()
        self.lock = RLock()
        self.started = time.monotonic()
        self.history, self.cache = {}, {}
        self.result = {'schema_version': 'research-session-v1', 'simulated': simulated,
            'status': 'started', 'runs': [], 'plan_setups': [], 'calls': [], 'charged': {},
            'config': self.config, 'manifest': asdict(manifest)}
        self.budget = TaskCallBudget(client, production_limit, evaluation_limit,
                                    max_calls=max_calls, capture_payload=True)
        self.budget.on_reserve = self._request
        self.budget.on_response = self._response
        self.persist()

    def persist(self):
        with self.lock:
            self.result['charged'], self.result['calls'] = self.budget.snapshot()
            try:
                write_json(self.out / 'session.json', self.result)
            except Exception as exc:
                self.budget.stop()
                raise EvidenceFailure('research evidence write failed') from exc

    def _request(self, reservation):
        self.persist()

    def _response(self, row, response):
        with self.lock:
            try:
                write_json(self.out / 'calls' / (hashlib.sha256(row['label'].encode()).hexdigest() + '.json'),
                           {'label': row['label'], **asdict(response)})
            except Exception as exc:
                self.budget.stop()
                raise EvidenceFailure('research response archive failed') from exc

    def _time(self):
        return (time.monotonic() - self.started) * 1000

    def _wait_provider(self, model, deadline):
        # 规划及评审发生在无在途节点时，共用节点执行器的 provider 派发历史。
        remaining = self.history.get(model.provider, -float('inf')) + self.policy.interval(model.provider)/1000 - time.monotonic()
        if remaining > 0:
            time.sleep(min(remaining, max(0, deadline - time.monotonic())))
        if time.monotonic() >= deadline:
            raise ValueError('task-deadline-exhausted')
        self.history[model.provider] = time.monotonic()

    def _judge(self, task, answer, criteria, label, deadline, *, node_input=None):
        self._wait_provider(self.manifest.judge, deadline)
        return evaluate_text(self.budget, self.manifest.judge, task, answer, criteria=criteria,
            label=label, deadline=deadline, input_cap=self.config['judge_input_cap'], node_input=node_input)

    def _plan(self, task, row, label, deadline):
        model = self.models[self.config['planner_model']]
        messages = [{'role': 'system', 'content': PLANNER_SYSTEM}, {'role': 'user', 'content': json.dumps({
            'task': task['task'], 'acceptance_criteria': task['criteria'],
            'execution_policy': self.policy.to_dict()}, ensure_ascii=False)}]
        if len(json.dumps(messages, ensure_ascii=False).encode()) + 256 > self.config['planner_input_cap']:
            raise PlanRejected('planner input exceeds frozen cap')
        row['phase'] = 'planning'
        row['planning_started_ms'] = self._time()
        self._wait_provider(model, deadline)
        reservation = self.budget.reserve(model, messages, label=label + ':planner', json_mode=True,
                                          category_limit=row.get('production_limit'))
        reply = self.budget.invoke(reservation, timeout_seconds=deadline - time.monotonic())
        row['planner_output'] = reply.content
        row['planning_finished_ms'] = self._time()
        row['phase'] = 'structural-check'
        self.persist()
        try:
            plan = validate_plan(json.loads(reply.content), required_criteria=task['criteria'], require_v2=True)
            if any(c['capability']['input_budget_tokens'] > self.config['auto_node_input_cap']
                   for c in plan.contracts.values()):
                raise ValueError('automatic node input cap exceeds frozen envelope')
        except ValueError as exc:
            raise PlanRejected(str(exc)) from exc
        row['plan'], row['structural_valid'] = plan.to_dict(), True
        row['structural_check_finished_ms'] = self._time()
        row['phase'] = 'plan-review'
        row['plan_review'] = self._judge('评估下面原始任务的拆分计划：' + task['task'],
            json.dumps(plan.to_dict(), ensure_ascii=False), PLAN_CRITERIA, label + ':plan-review', deadline)
        row['plan_review_finished_ms'] = self._time()
        # 语义不通过仍执行结构合法计划，测量错误传播；不挑选或修复计划。
        return plan

    def _settle_failure(self, exc, row):
        self.budget.stop()
        row['error_type'] = type(exc).__name__
        row['error'] = str(exc)[:500] if isinstance(exc, ValueError) else type(exc).__name__
        charged, calls = self.budget.snapshot()
        settled = all(c['status'] in ('billed', 'cancelled-before-dispatch') and
                      c['charged'] <= c['reserved'] + 1e-8 for c in calls)
        within = all(charged[k] <= self.budget.limits[k] + 1e-8 for k in charged)
        sample_cap = isinstance(exc, ValueError) and str(exc).startswith('production-budget-exhausted before ')
        if settled and within and (isinstance(exc, (PlanRejected, RecoveryEligibleFailure)) or recoverable(exc, self.budget) or sample_cap):
            # 不创建新预算，不清除调用历史，不给已失败样本再次规划的机会。
            self.budget.stopped = False
            row['status'] = ('planner-failed' if row['phase'] in ('planning', 'structural-check') else
                'plan-review-unavailable' if row['phase'] == 'plan-review' else
                'no-feasible-route' if row['phase'] == 'routing' else 'generation-failed'
                if row['phase'] == 'execution' else 'evaluation-unavailable')
        else:
            self.result['status'] = 'stopped-on-infrastructure'
            row['status'] = 'infrastructure-failed'
            raise exc

    def _finish_row(self, row, first_call):
        _, calls = self.budget.snapshot()
        calls = calls[first_call:]
        row['finished_ms'] = self._time()
        row['wall_time_ms'] = row['finished_ms'] - row['started_ms']
        row['call_labels'] = [c['label'] for c in calls]
        known = all(c['status'] in ('billed', 'cancelled-before-dispatch') for c in calls)
        row['cost_known'] = known
        row['costs'] = {k: sum(c['charged'] for c in calls if c['category'] == k)
                        for k in ('production', 'evaluation')}
        row['deployment_cost'] = sum(row['costs'].values()) if known else None
        grade = row.get('evaluation')
        row['score'] = grade['score'] if grade else None
        row['judge_passed'] = grade['passed'] if grade else None
        row['delivered'] = bool(grade and grade['passed'] and grade['score'] >= self.config['constraints']['qualityMin'])
        self.persist()

    def cache_plan(self, task, cache_id):
        if self.budget.stopped:
            raise RuntimeError('session stopped')
        if cache_id in self.cache:
            raise ValueError('cached plan already frozen')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', cache_id):
            raise ValueError('invalid cache ID')
        row = {'cache_id': cache_id, 'task_sha256': digest(task), 'status': 'started',
               'phase': 'planning', 'started_ms': self._time()}
        self.cache[cache_id] = row
        self.result['plan_setups'].append(row)
        first = len(self.budget.snapshot()[1])
        try:
            self._plan(task, row, 'setup:' + cache_id,
                       time.monotonic() + self.config['constraints']['latencyMaxMs']/1000)
            row['status'] = 'completed'
        except Exception as exc:
            self._settle_failure(exc, row)
        finally:
            self._finish_row(row, first)
        row['frozen_sha256'] = digest({k: v for k, v in row.items() if k != 'frozen_sha256'})
        self.persist()
        return deepcopy(row)

    def run_trial(self, task, run_id, *, mode, fixed_model=None, profiles=(), method='A', cache_id=None,
                  assignment_mode='per-node', explicit_assignments=None, serial=False, unavailable=False):
        if self.budget.stopped:
            raise RuntimeError('session stopped')
        if mode not in ('manual', 'direct', 'auto-cold', 'auto-reuse') or method not in ('A', 'B'):
            raise ValueError('invalid trial mode')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', run_id):
            raise ValueError('invalid trial ID')
        if any(r['run_id'] == run_id for r in self.result['runs']):
            raise ValueError('duplicate trial ID')
        row = {'run_id': run_id, 'task_id': task['task_id'], 'cell': task['cell'], 'mode': mode,
            'status': 'started', 'phase': 'planning', 'started_ms': self._time(), 'nodes': [],
            'production_limit': self.budget.snapshot()[0]['production'] + self.config['constraints']['costMax']}
        self.result['runs'].append(row)
        first = len(self.budget.snapshot()[1])
        start = time.monotonic()
        deadline = start + self.config['constraints']['latencyMaxMs']/1000
        policy = ExecutionPolicy(1, self.policy.provider_concurrency, self.policy.provider_min_interval_ms) if serial else self.policy
        try:
            if unavailable:
                row['phase'] = 'routing'
                raise ValueError('study-no-feasible-route: frozen baseline unavailable')
            if mode == 'auto-cold':
                plan = self._plan(task, row, run_id, deadline)
            elif mode == 'auto-reuse':
                cached = self.cache[cache_id]
                if (cached['task_sha256'] != digest(task) or cached['frozen_sha256'] !=
                        digest({k: v for k, v in cached.items() if k != 'frozen_sha256'})):
                    raise RuntimeError('cached plan evidence changed')
                row['cache_id'], row['setup_cost'] = cache_id, cached['deployment_cost']
                if cached['status'] != 'completed':
                    raise PlanRejected('cached plan unavailable; no regeneration')
                plan = validate_plan(cached['plan'], required_criteria=task['criteria'], require_v2=True)
                row['plan_review'] = deepcopy(cached['plan_review'])
            else:
                plan = direct_plan(task) if mode == 'direct' else validate_plan(task['plan'], required_criteria=task['criteria'], require_v2=True)
            row['plan'] = plan.to_dict()
            row['phase'] = 'routing'
            cap = self.config['constraints']
            if explicit_assignments is not None:
                if set(explicit_assignments) != {n.node_id for n in plan.nodes} or not set(explicit_assignments.values()) <= set(self.models):
                    raise ValueError('invalid explicit handoff assignments')
                row['assignments'] = dict(explicit_assignments)
                row['assignment_origin'] = 'frozen-handoff-validation'
            elif fixed_model is not None:
                if fixed_model not in self.models:
                    raise ValueError('unknown fixed model')
                row['assignments'] = {n.node_id: fixed_model for n in plan.nodes}
                row['assignment_origin'] = 'explicit-control-not-calibrated-routing'
            else:
                eligible = {n.node_id: [mid for mid, m in self.models.items()
                    if plan.contracts[n.node_id]['capability']['input_budget_tokens'] + output_token_limit(m) <= m.context_window]
                    for n in plan.nodes}
                row['routing'] = route_nodes(plan, profiles, method=method, quality_min=cap['qualityMin'],
                    cost_max=cap['costMax'], latency_max_ms=cap['latencyMaxMs'], weights=Weights(**cap['weights']) if method == 'B' else None,
                    eligible_models=eligible, execution_policy=policy,
                    model_providers={mid: m.provider for mid, m in self.models.items()}, assignment_mode=assignment_mode)
                if row['routing']['status'] != 'selected':
                    raise ValueError('study-no-feasible-route')
                row['assignments'] = row['routing']['assignments']
            row['routing_finished_ms'] = self._time()
            row['phase'] = 'execution'
            row['final_output'] = execute_nodes(plan, delivery_task(task), row['assignments'], self.models,
                self.budget, policy, row, self.persist, started=start, deadline=deadline,
                label_prefix=run_id + ':', classify_failure=True, dispatch_history=self.history,
                production_cap=row['production_limit'])
            row['execution_finished_ms'] = self._time()
            row['phase'] = 'final-review'
            review_task = task['task'] + ('\n仅供评审核验的冻结参考：\n'+task['evaluation_reference'] if task.get('evaluation_reference') else '')
            row['evaluation'] = self._judge(review_task, row['final_output'], task['criteria'], run_id + ':final-review', deadline)
            row['status'] = 'completed' if row['evaluation']['passed'] and row['evaluation']['score'] >= cap['qualityMin'] else 'quality-failed'
        except Exception as exc:
            self._settle_failure(exc, row)
        finally:
            self._finish_row(row, first)
        return deepcopy(row)

    def probe_node(self, task, node_id, model_id):
        """固定人工上下文的节点探测，独立评审；不使用整任务分数反推节点质量。"""
        if self.budget.stopped:
            raise RuntimeError('session stopped')
        if task['split'] not in ('development', 'calibration'):
            raise ValueError('held-out task cannot calibrate a node')
        plan = validate_plan(task['plan'], require_v2=True)
        node = next(n for n in plan.nodes if n.node_id == node_id)
        contract = plan.contracts[node_id]
        messages = node_messages(delivery_task(task), node, contract, task['reference_context'])
        label = f"probe:{task['task_id']}:{node_id}:{model_id}"
        if any(r['label'] == label for r in self.budget.records):
            raise ValueError('duplicate node probe')
        observations = self.result.setdefault('observations', {'schema_version': 'node-observations-v1',
            'kind': 'synthetic' if self.result['simulated'] else 'empirical', 'expected_contexts': [], 'observations': []})
        subject = {'task_id': task['task_id'], 'repeat': 1, 'node_id': node_id}
        if subject not in observations['expected_contexts']:
            observations['expected_contexts'].append(subject)
        row = {**subject, 'model_id': model_id, 'phase': 'execution', 'started_ms': self._time()}
        self.result.setdefault('probe_runs', []).append(row)
        first = len(self.budget.snapshot()[1])
        deadline = time.monotonic() + self.config['constraints']['latencyMaxMs']/1000
        try:
            model = self.models[model_id]
            self._wait_provider(model, deadline)
            try:
                response = self.budget.complete(model, messages, label=label,
                    json_mode=contract['output']['format'] == 'json', timeout_seconds=deadline-time.monotonic())
            except InvalidModelOutput:
                from .openai_compatible import ChatResponse
                archived = json.loads((self.out / 'calls' / (hashlib.sha256(label.encode()).hexdigest() + '.json')).read_text())
                response = ChatResponse(**{k: v for k, v in archived.items() if k != 'label'})
            raw_input = json.dumps(messages, ensure_ascii=False)
            ih, oh = (hashlib.sha256(v.encode()).hexdigest() for v in (raw_input, response.content))
            obs = {**subject, 'model_id': model_id, 'input': raw_input, 'output': response.content,
                'input_sha256': ih, 'output_sha256': oh, 'finish_reason': response.finish_reason,
                'status': 'completed' if response.finish_reason == 'stop' and response.content.strip() else 'invalid-output',
                'features': {'node_type': node.node_type, **{k: contract['capability'][k]
                    for k in ('difficulty', 'risk', 'input_budget_tokens')}}, 'output_contract': contract['output'],
                'latency_ms': response.latency_ms, 'usage': {k: getattr(response, k)
                    for k in ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_tokens')}}
            observations['observations'].append(obs)
            try:
                if obs['status'] != 'completed':
                    raise ValueError('invalid output')
                decode_output(response.content, contract)
            except ValueError:
                obs['evaluation'] = {'method': 'deterministic-rejection', 'status': 'rejected',
                    'score': 0, 'passed': False, 'input_sha256': ih, 'output_sha256': oh}
                row['status'] = 'generation-failed'
            else:
                row['phase'] = 'final-review'
                try:
                    review_task = task['task'] + ('\n仅供评审核验的冻结参考：\n'+task['evaluation_reference'] if task.get('evaluation_reference') else '')
                    grade = self._judge(review_task, response.content, contract['checks'], label + ':judge',
                                        deadline, node_input=json.loads(raw_input))
                    obs['evaluation'] = {**grade, 'method': 'independent-text-node-v1', 'status': 'completed',
                                          'input_sha256': ih, 'output_sha256': oh}
                    row['status'] = 'completed'
                except Exception as exc:
                    obs['evaluation'] = {'method': 'unavailable-independent-evaluation', 'status': 'unavailable',
                        'score': None, 'input_sha256': ih, 'output_sha256': oh}
                    raise exc
        except Exception as exc:
            self._settle_failure(exc, row)
        finally:
            self._finish_row(row, first)
        return deepcopy(row)

    def close(self):
        if self.result['status'] == 'started':
            self.result['status'] = 'simulated' if self.result['simulated'] else 'finished'
        self.budget.stop()
        self.persist()
        write_json(self.out / 'artifact-index.json', {str(p.relative_to(self.out)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(self.out.rglob('*')) if p.is_file() and p.name != 'artifact-index.json'})
        return deepcopy(self.result)
