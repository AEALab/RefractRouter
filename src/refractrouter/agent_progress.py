"""把核心检查点投影为不含正文、凭证与调用负载的节点进度。"""
import json
from .routing_actions import action_identity

PROTOCOL = 'refractagent-progress/v1'


def dag_snapshot(result, manifest):
    plan = result.get('plan') or {}
    routes = result.get('assignments', (result.get('routing') or {}).get('assignments', {}))
    actions = {m.model_id: action_identity(m) for m in manifest.models}
    latest = {row['node_id']: row for row in result.get('nodes', [])}
    terminal = result.get('status', 'started') != 'started'
    untouched = 'not-run' if result.get('status') in {'preview', 'planned'} else 'blocked' if terminal else 'pending'
    nodes = []
    plan_nodes = plan.get('nodes', [])
    live_roles = result.get('mode') == 'live'
    planner_id = '__role_planner__'
    input_classifier_id = '__role_input_classifier__'
    placement_id = '__role_placement__'
    reviewer_id = '__role_reviewer__'
    has_planner = live_roles and result.get('plan_origin') == 'model'
    placement = result.get('privacy_placement') or {}
    has_placement_gate = bool(placement.get('enabled'))
    has_input_classifier = has_planner and has_placement_gate
    if has_input_classifier:
        input_state = result.get('input_classification_state', 'pending')
        if terminal and input_state == 'running':
            input_state = 'blocked'
        nodes.append({'id': input_classifier_id, 'parents': [], 'node_type': 'role-classifier',
                      'objective': '检查规划输入敏感级别与部署准入', 'state': input_state,
                      'attempt': 1 if input_state == 'ok' else 0,
                      'model': None, 'recovery': None})
    if has_planner:
        planner_state = result.get('planning_state')
        if planner_state is None:
            input_state = result.get('input_classification_state')
            planner_state = ('ok' if plan_nodes else 'blocked' if input_state == 'blocked'
                             else 'pending' if input_state in {'pending', 'running'}
                             else 'failed' if terminal else 'running')
        elif terminal and planner_state == 'running':
            planner_state = 'failed'
        planner_model = result.get('planner_selection', {}).get('model_id')
        nodes.append({'id': planner_id, 'parents': [input_classifier_id] if has_input_classifier else [], 'node_type': 'role-planner',
                      'objective': '生成任务 DAG 与节点依赖', 'state': planner_state,
                      'attempt': sum(row.get('label') in {'planner', 'planner-repair'}
                                     for row in result.get('calls', [])),
                      'model': actions.get(planner_model), 'recovery': None})
    if has_placement_gate:
        placement_state = result.get('placement_state') or {
            'selected': 'ok', 'no-local-candidate': 'blocked', 'blocked': 'blocked'
        }.get(placement.get('status'), 'blocked' if terminal else 'pending')
        if terminal and placement_state == 'running':
            placement_state = 'blocked'
        nodes.append({'id': placement_id,
                      'parents': [planner_id] if has_planner else [],
                      'node_type': 'role-placement',
                      'objective': '检查规划节点的敏感级别与部署路线',
                      'state': placement_state,
                      'attempt': 1 if placement_state == 'ok' else 0,
                      'model': None, 'recovery': None})
    for node in plan_nodes:
        nid = node['node_id']
        row = latest.get(nid, {})
        parents = list(node['parents'])
        if not parents:
            gate_id = placement_id if has_placement_gate else planner_id if has_planner else None
            if gate_id:
                parents.append(gate_id)
        nodes.append({'id': nid, 'parents': parents,
                      'node_type': node.get('node_type'),
                      'difficulty': node.get('contract', {}).get('capability', {}).get('difficulty'),
                      'risk': node.get('contract', {}).get('capability', {}).get('risk'),
                      'objective': (node.get('contract', {}).get('objective') or node.get('prompt_template', ''))[:240],
                      'state': row.get('status', untouched), 'attempt': row.get('attempt', 1 if row else 0),
                      'model': actions.get(row.get('model_id', routes.get(nid))),
                      'recovery': row.get('recovery_status')})
    review = result.get('review') or {}
    if live_roles and review and (review.get('status') in {'running', 'completed', 'skipped'} or terminal):
        review_state = review.get('status', 'pending')
        if review_state == 'completed':
            review_state = 'ok'
        elif review_state == 'skipped':
            review_state = 'skipped'
        elif review_state == 'not-run' or result.get('status') in {'preview', 'planned', 'simulated'}:
            review_state = 'not-run'
        elif review_state == 'running':
            review_state = 'running'
        elif terminal:
            review_state = 'blocked'
        else:
            review_state = 'pending'
        task_nodes = [node for node in nodes if node['node_type'] not in {
            'role-planner', 'role-classifier', 'role-placement', 'role-reviewer'}]
        parents = {parent for node in task_nodes for parent in node['parents'] if parent in {n['id'] for n in task_nodes}}
        sinks = [node['id'] for node in task_nodes if node['id'] not in parents]
        if not sinks and has_planner:
            sinks = [planner_id]
        review_calls = [row for row in result.get('calls', []) if row.get('label') == 'final-judge']
        nodes.append({'id': reviewer_id, 'parents': sinks,
                      'node_type': 'role-reviewer',
                      'objective': '按评审策略检查最终交付质量', 'state': review_state,
                      'attempt': len(review_calls),
                      'model': actions.get(manifest.judge.model_id), 'recovery': None})
    phase = ('finished' if terminal else 'classifying' if any(
        n['node_type'] in {'role-classifier', 'role-placement'} and n['state'] == 'running' for n in nodes)
        else 'evaluating' if any(
        c['category'] == 'evaluation' for c in result.get('calls', [])) else
        'executing' if latest else 'routing' if plan else 'planning')
    return {'phase': phase, 'status': result.get('status', 'started'),
            'simulated': result.get('mode') == 'demo', 'plan_origin': result.get('plan_origin'),
            'reason': str(plan.get('decomposition_reason', ''))[:400], 'nodes': nodes}


class ProgressRecorder:
    def __init__(self, directory, manifest, callback=None):
        self.path = directory / 'progress.ndjson'
        self.run_id = directory.name
        self.manifest = manifest
        self.callback = callback
        self.previous = None
        self.sequence = 0

    def record(self, result):
        snapshot = dag_snapshot(result, self.manifest)
        fingerprint = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
        if fingerprint == self.previous:
            return
        self.sequence += 1
        event = {'protocol': PROTOCOL, 'run_id': self.run_id, 'sequence': self.sequence,
                 **snapshot, 'elapsed_ms': result.get('wall_time_ms', 0)}
        with self.path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n')
        self.previous = fingerprint
        if self.callback:
            self.callback(event)
