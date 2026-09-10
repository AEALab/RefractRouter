"""进度必须来自实际规划与调度，测试不使用网络或付费模型。"""
import json
from pathlib import Path
from threading import Event

import pytest

from refractrouter.agent import run_agent
from refractrouter.agent_progress import dag_snapshot
from tests.test_fast_dynamic_dag import Client, config
from tests.test_text_tasks import MANIFEST


def test_live_progress_arrives_before_blocked_model_finishes(tmp_path):
    released = Event()
    events = []
    class Slow(Client):
        def complete(self, model, messages, **kwargs):
            nid = json.loads(messages[-1]['content']).get('node_id')
            if nid in {'left', 'right'}:
                assert released.wait(3), '运行中的节点未及时展示'
            return super().complete(model, messages, **kwargs)
    def progress(event):
        events.append(event)
        if any(row['state'] == 'running' for row in event['nodes']):
            released.set()
    result = run_agent({'task':'比较两个方案', 'template':'auto'}, provider_config=config(), client=Slow(),
        mode='live', execute_paid_run=True, runs_dir=tmp_path, progress=progress)
    assert result['status'] == 'completed', result['issues']
    assert events[0]['phase'] == 'planning' and events[0]['nodes'] == []
    assert any(e['phase'] == 'routing' and e['nodes'] for e in events)
    assert any(e['phase'] == 'evaluating' for e in events)
    final = events[-1]
    assert final['phase'] == 'finished'
    assert all(n['state'] == 'ok' for n in final['nodes'])
    assert next(n for n in final['nodes'] if n['id']=='answer')['parents'] == ['left','right']
    assert all(n['model']['model'] for n in final['nodes'])
    assert [e['sequence'] for e in events] == list(range(1,len(events)+1))
    saved = [json.loads(line) for line in (Path(result['run_dir'])/'progress.ndjson').read_text().splitlines()]
    assert saved == events
    for row in events:
        assert not {'task','messages','output','calls','context','credentials'} & row.keys()
    assert result['dag']['nodes'] == final['nodes']


@pytest.mark.parametrize('failure', ['request','unknown'])
def test_dynamic_nodes_and_failed_downstream_are_not_hidden(tmp_path, failure):
    events = []
    result = run_agent({'task':'比较两个方案', 'template':'auto'}, provider_config=config(),
        client=Client(failure=failure), mode='live', execute_paid_run=True, runs_dir=tmp_path, progress=events.append)
    final = events[-1]
    if failure == 'request':
        assert len(final['nodes']) == 5
        assert any(n['state'] == 'invalid-output' for e in events for n in e['nodes'])
        assert all(n['state']=='ok' for n in final['nodes'])
    else:
        assert result['status'] != 'completed'
        assert next(n for n in final['nodes'] if n['id']=='answer')['state'] == 'blocked'
        assert any(n['state']=='failed' for n in final['nodes'])


def test_preview_is_not_reported_as_failed_execution():
    result = {'status':'preview','plan':{'nodes':[{'node_id':'answer','parents':[]}]},'nodes':[]}
    assert dag_snapshot(result, MANIFEST)['nodes'][0]['state'] == 'not-run'
