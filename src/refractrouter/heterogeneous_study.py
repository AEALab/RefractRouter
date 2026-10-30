"""六臂异构选模研究：冻结与零网络演练，当前入口不提供付费执行。"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from pathlib import Path
import hashlib
import json
import os
import random
import socket
import subprocess
import time
from threading import Lock
from unittest.mock import patch

from .compact_planning import COMPACT_PLANNER_SYSTEM, compile_compact
from .node_tools import catalog as node_catalog
from .openai_compatible import OpenAICompatibleClient, TransportResponse
from .quality_runtime import FINAL_SYSTEM
from .quality_study import digest, execution_payload
from .schemas import ModelSpec
from .task_budget import TaskCallBudget, request_input_bound
from .task_execution import execute_nodes
from .task_scheduling import ExecutionPolicy

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/node-tool-heterogeneous-v1'
ARMS = ('direct-L', 'direct-H', 'node-LL', 'node-LH', 'dag-L', 'dag-mixed')
PROMPTS = {'contract': FINAL_SYSTEM, 'verify': FINAL_SYSTEM +
    '交付前复核计算、版本、全部约束、来源和正文一致性；证据不足明确未确认。'}
MAIN_INPUT = 600000
EXPERT_INPUT = 32768
MAX_OUTPUT = 384000
REPEATS = 3


@dataclass(frozen=True)
class StudyModel(ModelSpec):
    unrestricted_execution_output: bool = True


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def models():
    return {alias: StudyModel(alias, 'ark-plan', rate, rate, .5, api_model=name,
        base_url='https://ark.cn-beijing.volces.com/api/plan/v3', api_key_env='CODEX_ARK_API_KEY',
        context_window=1024000, max_output_tokens=MAX_OUTPUT, wire_api='responses',
        billing_unit='AFP', cached_input_cost_per_1k=rate, request_options={'temperature': 0})
        for alias,name,rate in [('L','deepseek-v4-flash',.05),('H','deepseek-v4-pro',.55)]}


def bound(alias, input_limit=MAIN_INPUT):
    rate=Decimal(str(models()[alias].input_cost_per_1k))
    return float((Decimal(input_limit)+MAX_OUTPUT)*rate/1000)


def inputs():
    tasks=json.loads((DATA/'tasks.json').read_text())['tasks']
    refs=json.loads((DATA/'references.json').read_text())['references']
    for task in tasks:
        raw={k:v for k,v in task.items() if k!='task_sha256'}
        if digest(raw)!=task['task_sha256'] or refs[task['task_id']]['task_sha256']!=task['task_sha256']:
            raise ValueError('任务或参考绑定失效')
    return tasks, refs


def config(main, maximum, calls):
    return {'schemaVersion':'refractagent-planning-v2', 'enabled':True, 'defaultStrategy':'static',
        'maxProductionCostByUnit':{'AFP':maximum}, 'maxCalls':calls, 'timeoutMs':0,
        'models':[{'id':alias,'provider':'ark-node-study','model':m.api_model,
            'contextWindow':m.context_window,'maxOutputTokens':MAX_OUTPUT,
            'inputPer1k':m.input_cost_per_1k,'outputPer1k':m.output_cost_per_1k,
            'cachedInputPer1k':m.input_cost_per_1k,'billingUnit':'AFP','deployment':'trusted-cloud',
            'trustPolicy':'heterogeneous-study'} for alias,m in models().items()],
        'roles':{'efficient':main}, 'parameters':{'staticMode':'fixed'},
        'trustPolicies':[{'id':'heterogeneous-study','residency':'CN','auditLogging':True,'allowsSensitiveData':True}]}


def case_spec(task, arm, repeat, prompt='verify', phase='comparison'):
    main='H' if arm=='direct-H' else 'L'
    calls=7 if arm.startswith('node-') else 4 if arm.startswith('dag-') else 1
    system=PROMPTS[prompt]
    payload=execution_payload(task)
    maximum=bound(main, request_input_bound([{'role':'system','content':system},
        {'role':'user','content':json.dumps(payload,ensure_ascii=False)}])+4096)
    nodes=None
    if arm.startswith('node-'):
        expert='H' if arm=='node-LH' else 'L'
        maximum=4*bound('L')+3*bound(expert,EXPERT_INPUT)
        nodes={'enabled':True,'maxNodeCalls':3,'maxInputChars':6000,
            'modelBindings':{'main':'L','expert':expert}}
        system+='可按需调用 refract_expert 分析、核对或综合；不必委派；专家结果仍需核对。'
    elif arm.startswith('dag-'):
        maximum=4*bound('H' if arm=='dag-mixed' else 'L')
    run_id=f'{phase}-{task["task_id"]}-{arm}-{prompt}-r{repeat}'
    result={'runId':run_id,'taskId':task['task_id'],'arm':arm,'repeat':repeat,'phase':phase,
        'promptId':prompt,'system':system,'payload':payload,'inputLimit':MAIN_INPUT,'timeoutMs':0,
        'maxMainCalls':4 if nodes else 1,'maxModelCalls':calls,'afpUpperBound':round(maximum,8),
        'sampling':{'temperature':0},'wireControls':True,'rehearsalExpertCalls':3,
        'provider':{'id':'ark-node-study','baseURL':'https://ark.cn-beijing.volces.com/api/plan/v3',
            'api':'openai-responses','credentialRef':'CODEX_ARK_API_KEY','retryPolicy':{'mode':'normal','maxRetries':0}},
        'dshVersion':'0.1.5-rc.3','planningConfig':config(main,maximum,calls)}
    if nodes:result['nodeTools']=nodes
    return result


def assignments(plan, mixed):
    return {n.node_id: ('H' if mixed and (n.node_id==plan.final_node_id or
        plan.contracts[n.node_id]['capability']['difficulty']=='high' or
        plan.contracts[n.node_id]['capability']['risk']=='high') else 'L') for n in plan.nodes}


def compile_study_plan(raw, criteria=None):
    plan=compile_compact(raw,criteria=criteria,max_nodes=4,output_cap=MAX_OUTPUT)
    # 研究输入包络与执行器契约保持一致，避免继承旧版65536的局部隐藏上限。
    for contract in plan.contracts.values():
        contract['capability']['input_budget_tokens']=MAIN_INPUT
    return plan


def select_prompts(rows):
    """开发数据的确定性选择；禁止混入留出结果或不完整候选。"""
    expected={(t['task_id'],r) for t in inputs()[0] if t['split']=='development' for r in range(1,4)}
    if any(row['phase']!='prompt-audit' for row in rows):raise ValueError('提示选择不能读取留出结果')
    chosen={}
    for alias in ('L','H'):
        ranking=[]
        for prompt in PROMPTS:
            group=[row for row in rows if row['model']==alias and row['promptId']==prompt]
            if len(group)!=18 or {(row['taskId'],row['repeat']) for row in group}!=expected:
                raise ValueError('开发提示候选不完整')
            ranking.append((-sum(row['fieldStatus']=='pass' for row in group),
                sum(row['failedCheckCount'] for row in group),sum(row['chargedAfp'] for row in group),prompt))
        chosen[alias]=min(ranking)[-1]
    return {'selected':chosen,'developmentEvidenceSha256':digest(rows)}


def score_delivery(task, reference, text):
    """只核对已冻结的字段及支持来源；完整正文仍须独立语义审查。"""
    checks=[]
    try:
        obj=json.loads(text)
        if set(obj)!={'answer','findings'} or not isinstance(obj['answer'],str) or not obj['answer'].strip():
            raise ValueError('交付合同错误')
        if not isinstance(obj['findings'],list):raise ValueError('findings不是列表')
        found={}
        source_ids={m['source_id'] for m in task['materials']}
        for item in obj['findings']:
            if not isinstance(item,dict) or set(item)!={'id','value','sources'} or not isinstance(item['id'],str):
                raise ValueError('字段合同错误')
            if item['id'] in found:raise ValueError('重复字段')
            if (not isinstance(item['sources'],list) or not item['sources']
                    or any(not isinstance(s,str) or s not in source_ids for s in item['sources'])):
                raise ValueError('来源定位错误')
            found[item['id']]=item
        if set(found)!=set(reference['findings']):raise ValueError('缺少或增加字段')
        for key,spec in reference['findings'].items():
            actual=found[key]['value'];expected=spec['value']
            if spec['kind']=='set':
                valid=isinstance(actual,list) and len(actual)==len(expected) and sorted(map(digest,actual))==sorted(map(digest,expected))
            elif type(expected) in (int,float):
                valid=type(actual) in (int,float) and abs(actual-expected)<=.0001
            else:valid=type(actual) is type(expected) and actual==expected
            supported=any(set(option)<=set(found[key]['sources']) for option in spec['support_options'])
            checks.append({'id':key,'valueCorrect':valid,'sourceCoverage':supported})
        passed=all(c['valueCorrect'] and c['sourceCoverage'] for c in checks)
        return {'fieldStatus':'pass' if passed else 'fail','qualityStatus':'pending' if passed else 'fail',
            'checks':checks,'semanticReview':'未完成独立正文语义审查'}
    except (ValueError,TypeError,KeyError) as exc:
        return {'fieldStatus':'fail','qualityStatus':'fail','checks':checks,'error':str(exc)}


def prepare():
    tasks,_=inputs();dev=[t for t in tasks if t['split']=='development'];held=[t for t in tasks if t['split']=='candidate-holdout']
    cases=[case_spec(t,'direct-'+m,r,p,'prompt-audit') for t in dev for m in ('L','H') for p in PROMPTS for r in range(1,4)]
    setups=[]
    rng=random.Random(20261030)
    for r in range(1,4):
        for task in held:
            arms=list(ARMS);rng.shuffle(arms)
            cases.extend(case_spec(task,a,r) for a in arms)
            setups.append({'taskId':task['task_id'],'repeat':r,'model':'L','maxModelCalls':1,
                'afpUpperBound':bound('L'),'policy':'每对E/F只生成一次图；图完成后绑定哈希；不得按执行结果重规划'})
    qualification=[{'model':alias,'maxModelCalls':1,'afpUpperBound':bound(alias),
        'purpose':'真实调用时核对可用性、实际模型版本和请求能力；不据单条响应认证质量优势'} for alias in ('L','H')]
    paths=sorted(set([str(p.relative_to(ROOT)) for p in (ROOT/'src/refractrouter').rglob('*.py')]+
        [str(p.relative_to(ROOT)) for p in (ROOT/'validation/dsh/plugin/src').rglob('*.ts')]+
        ['validation/dsh/plugin/scripts/run-node-tool-study.ts','experiments/preflight_heterogeneous_study.py',
         'experiments/build_heterogeneous_materials.py','data/node-tool-heterogeneous-v1/tasks.json',
         'data/node-tool-heterogeneous-v1/references.json','data/node-tool-heterogeneous-v1/scoring.json',
         'uv.lock','validation/dsh/plugin/package-lock.json']))
    frozen={'schema':'heterogeneous-six-arm-v1','date':'2026-10-30','arms':ARMS,'cases':cases,'sharedPlanSetups':setups,
        'qualificationProbes':qualification,
        'models':{k:asdict(v) for k,v in models().items()},'prompts':PROMPTS,
        'promptSelection':'仅开发样本：每模型按通过数最多、失败检查最少、实际费用最低、prompt ID字典序选择；冻结赢家后才允许留出。',
        'comparisonPrompt':'direct各用自身开发赢家；工具两臂主循环使用相同L赢家；DAG两臂终稿统一使用L赢家以控制提示。预检verify是占位，非已选赢家。',
        'plannerSystem':COMPACT_PLANNER_SYSTEM,'maxNodes':4,'maxConcurrency':2,
        'sampling':{'temperature':0,'top_p':'provider-default','thinking':'provider-default'},
        'outputTokens':MAX_OUTPUT,'mainInputBytesUpperBound':MAIN_INPUT,'expertInputBytesUpperBound':EXPERT_INPUT,
        'timeoutMs':0,'httpRetries':0,'nodeFallbacks':0,'plannerRepairs':0,
        'maxModelCalls':sum(c['maxModelCalls'] for c in cases)+len(setups)+len(qualification),
        'fullCapacityAfpUpperBound':float(round(sum(Decimal(str(c['afpUpperBound'])) for c in cases)+
            sum(Decimal(str(s['afpUpperBound'])) for s in setups+qualification),8)),
        'suggestedOperationalAfpCap':6000,'operationalCapGuaranteesCompletion':False,
        'budgetPolicy':'完整输出逐调用预留，结算释放余额；6000是待批准运行上限建议，不是全容量完成保证；完整最坏费用另列。',
        'historicalPilot':{'calls':107,'chargedAndReservedAfp':62.0783,'unknownReserveAfp':.63,
            'scope':'独立历史授权，不作为新批授权；未知预留不释放'},
        'quality':{'unit':'task','repeats':3,'taskPass':'三次均通过字段及独立语义审查',
            'primaryPairs':[['node-LH','node-LL'],['dag-mixed','dag-L']],
            'secondaryPairs':[['node-LH','direct-H'],['dag-mixed','direct-H']],
            'sourcePolicy':'每结论至少一个完整支持来源组合；有效替代来源可接受；覆盖失败与数值错误分开记录',
            'humanMaterialReview':'pending','humanOutputReview':'pending','generalization':'探索；同族相关，不证明总体质量等价'},
        'architecture':'研究入口拥有委派/拆分；标准模型API不生成内部专家或DAG；宿主保持编排权。',
        'paidExecutionImplemented':False,'paidApproval':None,
        'sources':{'checkedAt':'2026-10-30','pricing':'https://docs.volcengine.com/docs/ark/agent-plan-personal-afp-credits-billing-rules?lang=zh',
            'capacity':'https://docs.volcengine.com/docs/ark/agent-plan-personal-plan-overview?lang=zh',
            'physicalRevision':'本轮未发真实请求；API别名非不可变版本，付费资格探测后须绑定实际回执版本'},
        'implementation':{p:sha(ROOT/p) for p in paths}}
    groups={'资格探测':qualification,'基线开发':[c for c in cases if c['phase']=='prompt-audit'],
        **{a:[c for c in cases if c['phase']=='comparison' and c['arm']==a] for a in ARMS},'共享规划':setups}
    frozen['budgetBreakdown']={key:{'runs':len(rows),'maxModelCalls':sum(r['maxModelCalls'] for r in rows),
        'fullCapacityAfpUpperBound':float(sum(Decimal(str(r['afpUpperBound'])) for r in rows))} for key,rows in groups.items()}
    frozen['protocolSha256']=digest(frozen)
    return frozen


def validate(frozen):
    if digest({k:v for k,v in frozen.items() if k!='protocolSha256'})!=frozen['protocolSha256']:
        raise ValueError('冻结摘要失效')
    if any(sha(ROOT/p)!=h for p,h in frozen['implementation'].items()):raise ValueError('冻结实现变化')


class OfflineTransport:
    def __init__(self,directory):
        self.directory=directory;directory.mkdir();self.calls=[];self.lock=Lock()
    def post(self,url,headers,body,timeout_seconds):
        payload=json.loads(body);m=next(m for m in models().values() if m.api_model==payload.get('model'))
        if (url!=m.base_url+'/responses' or payload.get('temperature')!=0
                or payload.get('max_output_tokens')!=MAX_OUTPUT or timeout_seconds not in (None,float('inf'))):
            raise ValueError('实际序列化请求未满足冻结控制')
        if 'reasoning' in payload or 'top_p' in payload:raise ValueError('意外改写思考或top_p')
        with self.lock:
            self.calls.append(payload);index=len(self.calls)
            write(self.directory/f'{index:03}-request.json',payload)
        content='离线节点产物，只证明集成路径。'
        value={'id':f'offline-{index}','model':m.api_model,'status':'completed',
            'output':[{'type':'message','role':'assistant','content':[{'type':'output_text','text':content}]}],
            'usage':{'input_tokens':100,'output_tokens':60,'total_tokens':160}}
        return TransportResponse(200,{},json.dumps(value).encode())


class ExecutionBudget(TaskCallBudget):
    def __init__(self,client,limit,final_id):
        super().__init__(client,limit,1,max_calls=4,capture_payload=True)
        self.final_id=final_id
    def reserve(self,model,messages,*,label,**kwargs):
        messages=deepcopy(messages)
        if label==self.final_id:messages[0]['content']=PROMPTS['verify']
        if request_input_bound(messages)>MAIN_INPUT:raise ValueError('DAG输入超过冻结包络')
        reservation=super().reserve(model,messages,label=label,**kwargs)
        reservation.row['stage']='final' if label==self.final_id else 'worker'
        return reservation


def rehearse(frozen, out, *, node_modules, python):
    validate(frozen);out=Path(out);out.mkdir(exist_ok=False)
    tasks,refs=inputs();lookup={t['task_id']:t for t in tasks}
    checks=[];native=[];dag=[];planner_probe=None
    # 逐项检查冻结矩阵、参考、公开投影；所有最终质量仍是pending。
    for case in frozen['cases']:
        task=lookup[case['taskId']];ref=refs[case['taskId']]
        assert case['payload']==execution_payload(task)
        output={'answer':'离线参考夹具，不是真实模型能力证据。','findings':[{'id':k,'value':v['value'],
            'sources':v['support_options'][0]} for k,v in ref['findings'].items()]}
        checked=score_delivery(task,ref,json.dumps(output,ensure_ascii=False))
        assert checked['fieldStatus']=='pass' and checked['qualityStatus']=='pending'
        assert request_input_bound([{'role':'system','content':case['system']},
            {'role':'user','content':json.dumps(case['payload'],ensure_ascii=False)}],
            node_catalog(case.get('nodeTools'))['tools']) < MAIN_INPUT
        checks.append({'runId':case['runId'],'publicPayloadSha256':digest(case['payload']),'referenceFixture':checked})
    # 真实DSH宿主的四种主/专家组合各演练一次，专家三次触及七调用边界；其余矩阵逐项静态检查。
    for arm in ARMS[:4]:
        case=deepcopy(next(c for c in frozen['cases'] if c['phase']=='comparison' and c['arm']==arm))
        case['protocolSha256']=frozen['protocolSha256'];spec=out/(arm+'-case.json');write(spec,case)
        directory=out/arm
        result=subprocess.run(['node','--experimental-strip-types',str(ROOT/'validation/dsh/plugin/scripts/run-node-tool-study.ts'),
            str(node_modules),str(python),str(spec),str(directory),'--rehearse'],cwd=ROOT,
            env={k:v for k,v in os.environ.items() if k not in ('CODEX_ARK_API_KEY','OPENAI_API_KEY')},capture_output=True,text=True)
        (out/(arm+'-host.log')).write_text(result.stdout+result.stderr)
        if result.returncode:raise ValueError('DSH零调用演练失败：'+arm+'；见宿主日志')
        value=json.loads((directory/'result.json').read_text());assert value['unexpectedNetwork']==0 and value['simulated']
        native.append({'arm':arm,'interceptedRequests':value['requests'],'expertCalls':value['expertCalls'],
            'wireEvidence':str(directory.relative_to(out))+'/wire'})
    fake_plan=compile_study_plan({'reason':'离线演练图，不是已生成的真实任务计划','nodes':[
        {'id':'extract','type':'extraction','job':'提取有效材料','parents':[],'difficulty':'low','risk':'low'},
        {'id':'check','type':'verification','job':'核对约束','parents':[],'difficulty':'high','risk':'high'},
        {'id':'answer','type':'generation','job':'完整交付','parents':['extract','check'],'difficulty':'medium','risk':'medium'}]},
        )
    # Python真实序列化、账本和同图并行调度；transport拦截且socket禁网。
    previous=os.environ.get('REFRACT_OFFLINE_KEY');os.environ['REFRACT_OFFLINE_KEY']='offline-fixture'
    try:
        with patch.object(socket.socket,'connect',side_effect=AssertionError('演练禁止网络')):
            planner_transport=OfflineTransport(out/'planner-wire')
            planner_client=OpenAICompatibleClient(max_retries=0,timeout_seconds=None,transport=planner_transport)
            planner_client.complete(replace(models()['L'],api_key_env='REFRACT_OFFLINE_KEY'),[
                {'role':'system','content':frozen['plannerSystem']},
                {'role':'user','content':json.dumps({'task':execution_payload(tasks[0]),'max_nodes':4},ensure_ascii=False)}])
            planner_probe={'interceptedRequests':1,'model':'L','wireEvidence':'planner-wire',
                'note':'只核对真实请求序列化；模拟正文不冒充真实规划结果'}
            for mixed in (False,True):
                directory=out/('dag-mixed' if mixed else 'dag-L');directory.mkdir()
                transport=OfflineTransport(directory/'wire')
                client=OpenAICompatibleClient(max_retries=0,timeout_seconds=None,transport=transport)
                budget=ExecutionBudget(client,4*bound('H' if mixed else 'L'),fake_plan.final_node_id)
                record={'nodes':[]};mapping=assignments(fake_plan,mixed)
                offline_models={k:replace(m,api_key_env='REFRACT_OFFLINE_KEY') for k,m in models().items()}
                execute_nodes(fake_plan,json.dumps(execution_payload(tasks[0]),ensure_ascii=False),mapping,offline_models,budget,
                    ExecutionPolicy(2,{'ark-plan':2}),record,lambda:None,started=time.monotonic(),deadline=float('inf'))
                costs,calls=budget.snapshot();assert len(calls)==3 and all(c['status']=='billed' for c in calls)
                write(directory/'record.json',{'plan':fake_plan.to_dict(),'assignments':mapping,'record':record,'calls':calls,'costs':costs})
                dag.append({'arm':'dag-mixed' if mixed else 'dag-L','planSha256':digest(fake_plan.to_dict()),'models':mapping,
                    'interceptedRequests':len(calls),'simulatedCost':costs['production']})
    finally:
        if previous is None:os.environ.pop('REFRACT_OFFLINE_KEY',None)
        else:os.environ['REFRACT_OFFLINE_KEY']=previous
    assert dag[0]['planSha256']==dag[1]['planSha256']
    result={'schema':'heterogeneous-zero-call-preflight-v1','status':'passed','realModelCalls':0,'realAfp':0,
        'protocolSha256':frozen['protocolSha256'],'matrix':dict(Counter(c['phase'] for c in frozen['cases'])),
        'matrixCases':checks,'nativeHost':native,'dagHost':dag,'plannerProbe':planner_probe,'paidReady':False,
        'remaining':['本轮真实模型版本及能力资格探测尚未执行','开发提示赢家尚未产生','独立材料及正文语义审查待完成','新增付费范围与预算尚未批准'],
        'capacityAlignment':{'mainInput':MAIN_INPUT,'expertInput':EXPERT_INPUT,'output':MAX_OUTPUT,
            'contextWindow':1024000,'nodeContractInput':MAIN_INPUT,'workerWireBytes':16*1024*1024,'hostLineBytes':32*1024*1024,
            'note':'输入按保守序列化计数准入；完整输出与下一步历史可能耗尽模型上下文，届时记录当前任务容量失败，不通过压低输出掩盖。'},
        'scope':'真实宿主四种组合和同图两种分配的零网络演练；矩阵静态检查不冒充288次真实任务质量验收'}
    write(out/'preflight.json',result)
    return result
