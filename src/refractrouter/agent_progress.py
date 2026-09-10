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
    for node in plan.get('nodes', []):
        nid = node['node_id']
        row = latest.get(nid, {})
        nodes.append({'id': nid, 'parents': node['parents'],
                      'objective': (node.get('contract', {}).get('objective') or node.get('prompt_template', ''))[:240],
                      'state': row.get('status', untouched), 'attempt': row.get('attempt', 1 if row else 0),
                      'model': actions.get(row.get('model_id', routes.get(nid))),
                      'recovery': row.get('recovery_status')})
    phase = ('finished' if terminal else 'evaluating' if any(
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
