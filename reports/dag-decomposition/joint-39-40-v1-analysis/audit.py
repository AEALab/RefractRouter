"""从冻结档案重算费用、摘要、材料数值与人工抽样；不调用模型或改动原始目录。"""
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
RAW=ROOT/'reports/dag-decomposition/joint-39-40-v1-actual'


def write(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def material_audit(protocol):
    results=[]
    for task in protocol['tasks']:
        if task['cell']!='large-high':continue
        key=task['task_id']; groups={}
        rows=[line for line in task['task'].splitlines() if line.startswith('来源 ')]
        assert len(rows)==100
        for i,line in enumerate(rows,1):
            assert f'{key}-L{i:03d}：' in line
            content=line.split('：',1)[1]
            group=re.search(r'([甲乙丙丁])(?:组|校区)',content)
            group=group[1] if group else re.search(r'类别 ([ABC])',content)[1]
            nums=[int(x) for x in re.findall(r'\d+',content)][1:]
            if key=='cal_archive':nums.append(int('锁定 是' in content))
            elif key=='cal_sensor':nums.append(0)
            a,b=nums
            groups.setdefault(group,[]).append((a,b))
        expected=json.loads(task['evaluation_reference'])
        for group,values in groups.items():
            a=[r[0] for r in values];b=[r[1] for r in values]
            checks={'记录数':len(values),'第一列总和':sum(a),'第二列总和':sum(b)}
            if key=='cal_sensor':
                checks.update(合格=sum(x in range(18,25) for x in a),异常=sum(x not in range(18,25) for x in a))
            elif key=='cal_archive':
                checks.update(锁定=sum(b),待审批=sum(x>{'A':30,'B':90,'C':365}[group] and y==0 for x,y in values))
            elif key=='test_seating':
                cap={'甲':70,'乙':90,'丙':110,'丁':130}[group]
                checks.update(申请=sum(a),有资格=sum(b),无资格=sum(a)-sum(b),席位=cap,缺口=max(sum(b)-cap,0))
            else:
                positive=sum(x-y for x,y in values if x>y)
                negative=sum(y-x for x,y in values if y>x)
                checks.update(第一列减第二列=sum(a)-sum(b),正缺口=positive,
                    第二列较大记录数=sum(y>x for x,y in values),第一列较大记录数=sum(x>y for x,y in values),正超额=negative)
                assert positive-negative==sum(a)-sum(b)
            assert checks==expected[group], (key,group,checks,expected[group])
        results.append({'task_id':key,'source_rows':100,'groups':len(groups),'all_reference_fields_match':True})
    return {'method':'重新解析冻结题目中的原始文本，独立重算所有参考字段；未导入材料生成器。','results':results}


def main():
    protocol=json.loads((ROOT/'data/research/joint-39-40-v1.json').read_text())
    write('material-numeric-audit.json',material_audit(protocol))
    if '--materials-only' in sys.argv:return
    session=json.loads((RAW/'session.json').read_text())
    assert session['status']!='started','只分析已结算批次'
    hashes=json.loads((RAW/'artifact-index.json').read_text())
    assert all(hashlib.sha256((RAW/path).read_bytes()).hexdigest()==h for path,h in hashes.items())
    models={m['model_id']:m for m in session['manifest']['models']}
    billed=0; totals={'production':0.,'evaluation':0.};unknown=[]
    for call in session['calls']:
        encoded=json.dumps(call['request_messages'],ensure_ascii=False).encode()
        assert hashlib.sha256(encoded).hexdigest()==call['input_sha256']
        if call['status']!='billed':
            if call['status']!='cancelled-before-dispatch':unknown.append(call['label'])
            continue
        response=json.loads((RAW/'calls'/(hashlib.sha256(call['label'].encode()).hexdigest()+'.json')).read_text())
        assert response['attempts']==1 and response['usage_available']
        assert response['content']==call['response_output']
        assert hashlib.sha256(response['content'].encode()).hexdigest()==call['output_sha256']
        for k in ('input_tokens','output_tokens','cached_input_tokens','reasoning_tokens'):
            assert response[k]==call[k]
        model=models[call['model_id']]
        actual=((call['input_tokens']-call['cached_input_tokens'])*model['input_cost_per_1k']+
            call['cached_input_tokens']*model['cached_input_cost_per_1k']+call['output_tokens']*model['output_cost_per_1k'])/1000
        assert math.isclose(actual,call['charged'],abs_tol=1e-8)
        totals[call['category']]+=actual;billed+=1
    if not unknown:
        for category,total in totals.items():assert math.isclose(total,session['charged'][category],abs_tol=1e-8)
    observed=[r for r in session['runs'] if r.get('split')=='test']
    calls={c['label']:c for c in session['calls']}
    handoffs=[]
    for row in session['runs']:
        if not row.get('plan'):continue
        nodes={n['node_id']:n for n in row['plan']['nodes']}
        checked=heterogeneous=0
        for node in row['nodes']:
            call=calls.get(row['run_id']+':'+node['node_id'])
            if not call:continue
            payload=json.loads(call['request_messages'][-1]['content'])
            for parent,actual in payload['upstream'].items():
                upstream=calls[row['run_id']+':'+parent]
                contract=nodes[parent]['contract']
                expected=({'text':upstream['response_output']} if contract['output']['format']=='text'
                    else json.loads(upstream['response_output']))
                fields=nodes[node['node_id']]['contract']['inputs'][parent]['fields']
                assert actual=={k:expected[k] for k in fields}
                checked+=1;heterogeneous+=int(call['model_id']!=upstream['model_id'])
        if checked or row.get('arm')=='handoff':
            handoffs.append({'run_id':row['run_id'],'verified_edges':checked,'cross_model_edges':heterogeneous,
                'delivered':row['delivered'],'status':row['status']})
    planned=session['planned_runs']
    keys=lambda r:(r['task_id'],r['repeat'],r['arm'])
    assert len({keys(r) for r in observed})==len(observed)
    assert {keys(r) for r in observed}<={keys(r) for r in planned}
    report={'status':session['status'],'indexed_files_verified':len(hashes),'billed_calls':billed,
        'unknown_usage_calls':unknown,'verified_billed_afp':totals,'planned_test_runs':len(planned),
        'observed_test_runs':len(observed),'delivered_test_runs':sum(r['delivered'] for r in observed),
        'failed_costs_retained':True,'human_review_complete':False}
    write('audit.json',report)
    write('handoff-audit.json',{'method':'逐条对比下游请求实际字段与上游原始响应，统计真实跨模型边。','rows':handoffs})
    tasks={t['task_id']:t for t in protocol['tasks'] if t['split']=='test'}
    selected={min(t['task_id'] for t in tasks.values() if t['challenge']==challenge) for challenge in {t['challenge'] for t in tasks.values()}}
    candidates=[]
    for tid in sorted(selected):
        candidates.append((tid,'manual',tasks[tid]['plan'],None))
    for row in observed:
        if row['arm'].startswith('auto-cold') and (row['task_id'] in selected or row['status']=='planner-failed'):
            candidates.append((row['task_id'],row['run_id'],row.get('plan'),row.get('planner_output')))
    for row in session['plan_setups']:
        tid=row['cache_id'][:-2]
        if tid in selected or row['status']=='planner-failed':
            candidates.append((tid,'cache:'+row['cache_id'],row.get('plan'),row.get('planner_output')))
    random.Random(394010).shuffle(candidates)
    packet=[];mapping={}
    for i,(tid,origin,plan,raw) in enumerate(candidates,1):
        rid=f'P{i:03d}';mapping[rid]={'task_id':tid,'origin':origin}
        packet.append({'review_id':rid,'task':tasks[tid]['task'],'criteria':tasks[tid]['criteria'],
            'plan':plan,'raw_plan_if_unparsed':raw if plan is None else None,
            'reviewer':None,'reviewed_at':None,'decomposition_appropriate':None,'original_delivery_covered':None,
            'dependencies_correct':None,'parallelism_appropriate':None,'handoff_risks':None,'overall_passed':None,'rationale':None})
    write('human-review-packet.json',{'scope':'真人复核；不得由自动评分或模型填表替代。','rows':packet})
    write('human-review-mapping.json',mapping)
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
