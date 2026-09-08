"""从仓库根目录执行，离线复核本轮原始证据并重建配对分析。"""
from pathlib import Path
from collections import Counter
import hashlib,json,statistics,sys
sys.path.insert(0,'src')
from refractrouter.manifest import load_model_manifest
from refractrouter.openai_compatible import ChatResponse,model_response_cost
from refractrouter.task_contracts import decode_output
from refractrouter.task_plan import validate_plan
root=Path('reports/dag-decomposition/issue-32-usage-verified-20260908');study=root/'study'
r=json.loads((study/'study-result.json').read_text());assert r['status']=='completed' and r['comparison']['complete']
index=json.loads((study/'artifact-index.json').read_text())
for name,digest in index.items():
 p=(study/name).resolve();assert p.is_relative_to(study.resolve()) and hashlib.sha256(p.read_bytes()).hexdigest()==digest,name
manifest=load_model_manifest(study/'manifest.json');models={m.model_id:m for m in manifest.models}
for c in r['calls']:
 assert c['status']=='billed' and c['input_tokens']>0 and c['output_tokens']>0 and c['finish_reason']=='stop',c['label']
 stem=hashlib.sha256(c['label'].encode()).hexdigest()
 response=json.loads((study/'calls'/(stem+'-response.json')).read_text())
 request=json.loads((study/'calls'/(stem+'-request.json')).read_text())
 assert response['usage_available'] is True and isinstance(response['raw_usage'],dict)
 usage=response['raw_usage']
 assert usage.get('prompt_tokens',usage.get('input_tokens'))==response['input_tokens']==c['input_tokens']
 assert usage.get('completion_tokens',usage.get('output_tokens'))==response['output_tokens']==c['output_tokens']
 assert response['attempts']==1
 assert hashlib.sha256(json.dumps(request['messages'],ensure_ascii=False).encode()).hexdigest()==c['input_sha256']
 assert hashlib.sha256(response['content'].encode()).hexdigest()==c['output_sha256']
 value=ChatResponse(**{k:v for k,v in response.items() if k!='label'})
 assert abs(model_response_cost(models[c['model_id']],value)-c['charged'])<1e-8
rows=[];handoffs=[];verified_edges=0
for trial in r['runs']:
 a=json.loads((study/trial['result_path']).read_text())
 assert trial['status']=='completed' and trial['delivered'] and a['evaluation']['passed']
 assert abs(sum(c['charged'] for c in a['calls'])-trial['deployment_cost'])<1e-8
 plan=validate_plan(a['plan']); context={n['node_id']:decode_output(n['output'],plan.contracts[n['node_id']]) for n in a['nodes']}
 folder=trial['result_path'].split('/')[0]
 for node in plan.nodes:
  label=folder+':'+node.node_id
  req=json.loads((study/'calls'/(hashlib.sha256(label.encode()).hexdigest()+'-request.json')).read_text())
  actual=json.loads(req['messages'][-1]['content'])['upstream']
  expected={parent:{field:context[parent][field] for field in plan.contracts[node.node_id]['inputs'][parent]['fields']} for parent in node.parents}
  assert actual==expected,label
  assert req['model_id']==a['assignments'][node.node_id]
  verified_edges+=len(node.parents)
 info={'task_id':trial['task_id'],'repeat':trial['repeat'],'method':trial['method'],'assignments':a['assignments'],
       'heterogeneous':len(set(a['assignments'].values()))>1,'score':trial['score'],'delivered':trial['delivered']}
 if trial['split']=='handoff':handoffs.append(info)
 elif trial['split']=='test':rows.append(info)
assert len(handoffs)==6 and all(len(set(h['assignments'].values()))==3 for h in handoffs)
assert len({tuple(sorted(h['assignments'].items())) for h in handoffs})==6
assert len(rows)==72 and len({(x['task_id'],x['repeat'],x['method']) for x in rows})==72
assert all(len(set(x['assignments'].values()))==1 for x in rows if x['method'].startswith('dag-single-'))
paired=[]
for c in r['comparison']['comparisons']:
 p=c['joint_graded_pairs'];assert len(p)==len(c['outcome_pairs'])==9
 paired.append({'candidate':c['candidate'],'baseline':c['baseline'],'pairs':len(p),
 'mean':{k:statistics.mean(x[k] for x in p) for k in ('quality_delta','cost_saving','latency_ratio')},
 'conditional_interval_95':c['conditional_interval_95'],'exploratory_signal':c['exploratory_signal']})
summary={'status':'completed','real_calls':len(r['calls']),'confirmed_calls':len(r['calls']),'unconfirmed_calls':0,
 'call_categories':dict(Counter(c['category'] for c in r['calls'])),'charged':r['charged'],'total_afp_estimate':sum(r['charged'].values()),
 'source_calibration_calls':283,'new_calibration_calls':0,'handoffs':handoffs,'test_results':rows,
 'automatic_heterogeneous_test_runs':sum(x['heterogeneous'] for x in rows if x['method'] in ('dag-node-a','dag-node-b')),
 'verified_upstream_edges':verified_edges,'verified_artifacts':len(index),'comparisons':paired,
 'limitation':'仅本轮冻结三任务、三类能力/风险组合与一个输入预算区间；同一 DAG 单模型对照不等于一次调用的优化整任务路由。'}
(root/'result-analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:summary[k] for k in ('real_calls','charged','total_afp_estimate','automatic_heterogeneous_test_runs','verified_upstream_edges','verified_artifacts')},ensure_ascii=False))
for c in paired:print(c['candidate'],c['baseline'],c['mean'],c['exploratory_signal'],c['conditional_interval_95'])
