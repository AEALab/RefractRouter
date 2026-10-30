"""从原逐调用账本和独立标签监控发布；不改费用、资格、模型池或配置。"""
from collections import defaultdict
from decimal import Decimal
import json
from pathlib import Path

from .release_governance import HASH
from .task_results import TaskResults
from .task_cost_observation import observe,amount
from .review_benefit import independent_labels,audit


def prediction_error(view,costs):
    shadow=view.get('taskShadow') or {}
    missing={'status':'unknown','absoluteError':None,'signedError':None,
        'reason':'no-comparable-bound-full-cost-prediction'}
    if (shadow.get('predictionStale') or shadow.get('costBasis')!='empirical-full-managed-task'
            or shadow.get('corpusKind')!='empirical' or not view.get('costContext')
            or not costs['pricedCallAmountsComplete'] or costs.get('cacheUsageComplete') is not True):return missing
    execution=[r for r in view['calls'] if r.get('purpose') in ('execute','redo','takeover')]
    if (not execution or execution[0]['model_id']!=shadow.get('actualCandidateId')
            or len({r.get('host_request_id') for r in view['calls'] if r.get('call_id')})!=1):return missing
    row=next((r for r in shadow.get('rows',[]) if r.get('modelId')==shadow['actualCandidateId']),None)
    estimate=row.get('estimate') if row else None
    if not estimate or estimate.get('includesAllManagedCalls') is not True:return missing
    reference=costs.get('referenceCostCny')
    if reference is not None:
        dimension=['reference-valuation','CNY'];actual=Decimal(reference['knownCalculated'])
    elif len(costs['costs'])==1:
        cost=costs['costs'][0];dimension=[cost['lane'],cost['unit']];actual=Decimal(cost['knownCalculated'])
    else:return missing
    if estimate.get('dimension')!=dimension:return missing
    predicted=amount(estimate['mean']);error=actual-predicted
    return {'status':'observed','absoluteError':str(abs(error)),'signedError':str(error),
        'prediction':str(predicted),'knownCalculated':str(actual),'dimension':dimension,
        'scope':'single-bound-flow-not-future-error-guarantee'}


def monitor(store,annotations=None):
    annotations={} if annotations is None else annotations
    if type(annotations) is not dict:raise ValueError('独立监控标签必须按运行ID索引')
    index=store.execution_records();records=index['records'];bound=index['root']
    tasks=[];lanes=defaultdict(lambda:[Decimal(0),Decimal(0)]);fees_complete=True
    if records and bound is None:raise ValueError('任务存在但执行根记录缺失')
    root=Path(bound['path']) if bound else None
    if root is not None:
        marker=root/'.governed-root'
        if not marker.is_file() or marker.is_symlink() or marker.read_text()!=bound['nonce']:
            raise ValueError('历史执行根标记丢失，不能把费用当零')
    for item in records:
        result={'task':item['task'],'releaseSha256':item['release_id'],'runId':item['run_id'],
            'completeDeliveryQuality':'UNKNOWN','transportDelivery':'unknown','reworkAttempts':None,
            'unnecessaryInterventions':None,'independentUpgradeAudits':None,'predictionError':None,
            'feeAnomalies':[],'costObservation':None}
        if item['run_id'] is None:
            fees_complete=False
            result['reason']='not-started-or-no-execution-receipt';tasks.append(result);continue
        if HASH.fullmatch(item['run_id']) is None or HASH.fullmatch(item['release_id']) is None:
            raise ValueError('历史执行索引损坏')
        path=root/'releases'/item['release_id']/'planning'/(item['run_id']+'.json')
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            fees_complete=False
            result['reason']='source-record-unavailable';tasks.append(result);continue
        raw=json.loads(path.read_bytes())
        view=TaskResults(path.parent/'outcomes').view(raw)
        costs=observe(view);result['costObservation']=costs
        for row in costs['costs']:
            totals=lanes[row['lane'],row['unit']]
            totals[0]+=Decimal(row['knownCalculated']);totals[1]+=Decimal(row['unknownProtected'])
        labels=annotations.get(item['run_id'],{'criteriaSha256':'0'*64,'annotations':[],'upgradeAssessments':[]})
        if type(labels) is not dict or set(labels)!={'criteriaSha256','annotations','upgradeAssessments'}:
            raise ValueError('监控裁定字段不完整')
        active_annotations=labels['annotations'];active_criteria=labels['criteriaSha256']
        try:
            quality=independent_labels(view,active_annotations,criteria_sha256=active_criteria)
            result['labelBindingValid']=True
        except ValueError:
            quality={};active_annotations=[];active_criteria='0'*64
            result['labelBindingValid']=False;result['labelError']='independent-label-binding-unconfirmed'
        selected=[c for c in view['candidates'] if c['routerDisposition']=='accepted']
        if (view['status']=='completed' and selected and next((r.get('finish_reason') for r in view['calls']
                if r.get('call_id')==selected[-1]['candidateId']),None)=='stop'):
            result['completeDeliveryQuality']=quality.get(selected[-1]['candidateId'],'UNKNOWN')
        dispatched=[c for c in view['calls'] if c.get('call_id') and c.get('status') not in ('reserved','cancelled-before-dispatch')]
        result['reworkAttempts']=sum(c.get('purpose')=='redo' for c in dispatched)
        if view['strategy'] in ('static','advisor','escalation'):
            review=audit(view,active_annotations,criteria_sha256=active_criteria)
            result['unnecessaryInterventions']={'known':review['unnecessaryInterventions'],
                'unknown':review['interventionUnknown'],'scope':'bound-advisor-escalation-only'}
        switches=[]
        executed=[c for c in dispatched if c.get('purpose') in ('execute','redo','takeover')]
        for previous,current in zip(executed,executed[1:]):
            if previous['model_id']!=current['model_id']:
                switches.append((previous['call_id'],current['call_id']))
        assessments=labels['upgradeAssessments']
        if type(assessments) is not list:raise ValueError('升级审计须为列表')
        witnessed=set();unnecessary=0;known_judgements=0
        for judgement in assessments:
            if (type(judgement) is not dict or set(judgement)!={'fromCallId','toCallId','decisionSha256',
                    'independent','verdict','recordSha256'} or judgement['independent'] is not True
                    or judgement['verdict'] not in ('necessary','unnecessary','unknown')
                    or type(judgement['recordSha256']) is not str or HASH.fullmatch(judgement['recordSha256']) is None):
                raise ValueError('升级审计需要明确独立来源与固定记录')
            pair=judgement['fromCallId'],judgement['toCallId']
            target=next((c for c in executed if c['call_id']==pair[1]),None)
            if (pair not in switches or pair in witnessed or target is None
                    or not any(d['sha256']==judgement['decisionSha256'] and d.get('model')==target['model_id']
                        for d in view['decisions'])):raise ValueError('升级审计未绑定实际模型切换及原决策')
            witnessed.add(pair);unnecessary+=judgement['verdict']=='unnecessary'
            known_judgements+=judgement['verdict']!='unknown'
        result['independentUpgradeAudits']={'knownUnnecessary':unnecessary,'assessedSwitches':known_judgements,
            'submittedAssessments':len(witnessed),'unknownSwitches':len(switches)-known_judgements,
            'rate':None if known_judgements!=len(switches) or not switches
                else unnecessary/len(switches),'scope':'maintainer-audited-model-switches'}
        result['predictionError']=prediction_error(view,costs)
        for call in view['calls']:
            if (call.get('status') not in ('billed','cancelled-before-dispatch','local-inference')
                    or call.get('price_binding_confirmed') is False
                    or amount(call.get('charged',0))>amount(call.get('reserved',call.get('charged',0)))):
                result['feeAnomalies'].append(call.get('call_id'))
        tasks.append(result)
    return {'schemaVersion':'routing-release-monitor-v1','taskCount':len(tasks),'tasks':tasks,
        'feeSummaryComplete':fees_complete,
        'feeLanes':[{'lane':lane,'unit':unit,'knownCalculated':str(v[0]) if fees_complete else None,
            'unknownProtected':str(v[1]) if fees_complete else None,
            'readableKnownCalculated':str(v[0]),'readableUnknownProtected':str(v[1])}
            for (lane,unit),v in sorted(lanes.items())],
        'completeDelivery':{quality:sum(t['completeDeliveryQuality']==quality for t in tasks)
            for quality in ('PASS','FAIL','UNKNOWN')},'currenciesCombined':False,
        'providerDebitVerified':False,'modelCalls':0,'financialLedgerChanged':False,
        'modelPoolChanged':False,'qualificationAutomaticallyUpdated':False,
        'coverage':'managed-agent-only','parentChildSharedBudgetEnforced':False}
