"""离线复核新应用验收的原始文件、调用、费用及实际交接，不修改原始产物。"""
import argparse
import hashlib
import json
from pathlib import Path


def audit(directory):
    directory = Path(directory)
    index = json.loads((directory/'artifact-index.json').read_text())
    for name, expected in index.items():
        assert hashlib.sha256((directory/name).read_bytes()).hexdigest() == expected, name
    frozen = json.loads((directory/'preflight.json').read_text())
    source = dict(frozen)
    fingerprint = source.pop('sha256')
    assert hashlib.sha256(json.dumps(source,ensure_ascii=False,sort_keys=True).encode()).hexdigest() == fingerprint
    rows = json.loads((directory/'results.json').read_text())
    compact = 'runs' in frozen['protocol']
    tasks = ({t['id']:t for t in frozen['protocol']['runs']} if compact else
             {t['id']: t for t in frozen['protocol']['tasks'] if t['split'] == frozen['split']})
    seen, calls, edges = set(), [], 0
    checked = []
    for row in rows:
        task_id = row['case_id'] if compact else row['task_id']
        template = tasks[task_id]['template'] if compact else row['template']
        pair = (task_id, template)
        assert pair not in seen
        seen.add(pair)
        run = directory/task_id/row['run_id'] if compact else directory/task_id/template/row['run_id']
        raw = json.loads((run/'result.json').read_text())
        request = json.loads((run/'request.json').read_text())
        manifest = json.loads((run/'manifest.json').read_text())
        models = {m['model_id']: m for m in manifest['models']}
        assert request['payload']['task'] == tasks[task_id]['task']
        assert request['payload']['acceptanceCriteria'] == tasks[task_id]['criteria']
        if template == 'auto':
            assert 'plan' not in request['runtime_request'] and raw['plan_origin']=='model'
        total = {'production': 0., 'evaluation': 0.}
        call_by_node = {}
        for call in raw['calls']:
            assert call['status'] == 'billed' and call['charged'] <= call['reserved'] + 1e-8
            assert hashlib.sha256(json.dumps(call['request_messages'],ensure_ascii=False).encode()).hexdigest() == call['input_sha256']
            response = call['response']
            assert response['attempts'] == 1 and response['usage_available']
            assert response['finish_reason'] == 'stop'
            assert response['content'] == call['response_output']
            assert hashlib.sha256(response['content'].encode()).hexdigest() == call['output_sha256']
            assert response['input_tokens'] > 0 and response['output_tokens'] > 0
            for key in ('input_tokens','output_tokens','cached_input_tokens','reasoning_tokens'):
                assert response[key] == call[key]
            m = models[call['model_id']]
            cost = ((call['input_tokens']-call['cached_input_tokens']) * m['input_cost_per_1k']
                + call['cached_input_tokens'] * m['cached_input_cost_per_1k']
                + call['output_tokens'] * m['output_cost_per_1k']) / 1000
            assert abs(cost-call['charged']) < 1e-8
            total[call['category']] += cost
            call_by_node[call['label']] = call
            calls.append(call)
        assert row['costs']['unconfirmed'] == 0
        for kind in total:
            assert abs(total[kind]-raw['charged'][kind]) < 1e-8
            assert abs(total[kind]-row['costs'][kind]) < 1e-8
        assert abs(sum(total.values())-sum(row['cost_breakdown'].values())) < 1e-8
        actual = {n['node_id']: n for n in raw['nodes']}
        for node in (raw.get('plan') or {}).get('nodes',[]):
            if node['node_id'] not in actual or actual[node['node_id']]['status']!='ok':
                continue
            payload = json.loads(call_by_node[actual[node['node_id']].get('call_label',node['node_id'])]['request_messages'][-1]['content'])
            assert set(payload['upstream']) == set(node['parents'])
            for parent, contract in node['contract']['inputs'].items():
                assert actual[parent]['end_ms'] <= actual[node['node_id']]['start_ms']
                parent_node = next(n for n in raw['plan']['nodes'] if n['node_id']==parent)
                output = actual[parent]['output']
                value = json.loads(output) if parent_node['contract']['output']['format']=='json' else {'text':output}
                assert payload['upstream'][parent] == {key:value[key] for key in contract['fields']}
                edges += 1
        grade = raw.get('evaluation')
        if row['status']=='completed':
            assert grade and grade['passed'] and grade['score'] >= (frozen['configuration']['qualityMin'] if compact else frozen['protocol']['quality_min'])
            assert len(actual)==len(raw['plan']['nodes'])
            assert all(n['status']=='ok' for n in actual.values())
            assert raw['final_output']==actual[raw['plan']['final_node_id']]['output']
            assert raw['final_output']==(run/'answer.md').read_text()==row['answer']
        for event in raw.get('dynamic_decomposition',{}).get('events',[]):
            assert event['status']=='admitted'
            assert hashlib.sha256(json.dumps(event['upstream'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()==event['upstream_sha256']
            for nid in event['completed_nodes']:
                assert len([n for n in raw['node_attempts'] if n['node_id']==nid])==1
            assert len(event['plan']['nodes'])<=8
        checked.append({'task':task_id, 'template':template,
            'plan_ready_ms':row.get('plan_ready_ms'), 'content_validation':row.get('content_validation'),
            'dynamic_events':len(raw.get('dynamic_decomposition',{}).get('events',[])),
            'dynamic_planning_afp':row['cost_breakdown'].get('dynamic_planning',0), 'status':row['status'],
            'nodes':len(actual), 'score':grade['score'] if grade else None,
            'planning_afp':row['cost_breakdown']['planning'], 'execution_afp':row['cost_breakdown']['execution'],
            'evaluation_afp':row['cost_breakdown']['evaluation'], 'total_afp':sum(total.values()),
            'wall_time_ms':raw['wall_time_ms'], 'node_execution_ms':raw.get('execution',{}).get('wall_time_ms'),
            'peak_running_nodes':raw.get('execution',{}).get('peak_running_nodes',0)})
    assert len(calls) <= (frozen['limits']['maximum_calls'] if compact else frozen['maximum_calls'])
    for kind in ('production','evaluation'):
        assert sum(c['charged'] for c in calls if c['category']==kind) <= (frozen['limits'][kind+'_per_run']*len(tasks) if compact else frozen['budget'][kind])
    expected = ({(t,v['template']) for t,v in tasks.items()} if compact else
                {(t, template) for t in tasks for template in frozen['protocol']['order']})
    return {'verified':True,'complete':seen==expected,'files':len(index),'calls':len(calls),'checked_handoffs':edges,
        'total_afp':sum(c['charged'] for c in calls), 'comparisons':checked,
        'scope':'仅核对结构交接与账本；模型是否正确理解上游语义仍由最终评审及材料复核判断。'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=audit(args.directory)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as out:
        json.dump(result,out,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ('verified','complete','files','calls','checked_handoffs','total_afp')}))
