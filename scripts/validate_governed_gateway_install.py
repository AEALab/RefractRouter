"""验收已安装治理网关的真实HTTP链路；只连接本机固定夹具，不调用模型。"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import refractrouter.model_gateway as module
from refractrouter.governed_gateway import GovernedGateway, CONFIG, ALIAS
from refractrouter.release_governance import EVIDENCE, ReleaseStore, frozen_release
from refractrouter.release_monitor import monitor

TEXT='中文🦀🚀👩🏽\u200d💻e\u0301'
PRIVATE='夹具私有思考，仅用于同源工具续接'


def constructed_evidence(snapshot):
    """仅测试门槛的算术正路径；不代表真实研究或产品收益资格。"""
    return {'schemaVersion':EVIDENCE,'kind':'empirical-independent-holdout','strategy':snapshot['strategy'],
        'contextSha256':snapshot['contextSha256'],'sourceAuditSha256':'b'*64,'toolsSha256':'c'*64,
        'hostSha256':'d'*64,'deliverySha256':'e'*64,'independenceAudited':True,'hiddenIsolationAudited':True,
        'billingUnit':snapshot['billingUnit'],'costAuditSha256':'f'*64,
        'costScope':'all-execution-routing-online-review-attempts','researchScoringReportedSeparately':True,
        'criticalRegressions':0,'componentEvidence':{},'incrementalRows':{},'rows':[{'taskId':str(i),'half':i%2,
            'baselinePassed':True,'candidatePassed':True,'completedPair':True,'knownCost':True,
            'baselineCost':1,'candidateCost':.5} for i in range(100)]}


def validate(workspace, *, require_installed=True):
    source=Path(__file__).resolve().parents[1]/'src'
    if require_installed and Path(module.__file__).resolve().is_relative_to(source):
        raise ValueError('本验收必须使用源码目录外实际安装的wheel')
    workspace=Path(workspace);workspace.mkdir(parents=True,exist_ok=True)
    seen=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            seen.append((self.path,body))
            assert body['max_completion_tokens']==1024 and body['stream'] is False
            tools=[]
            if body['messages'][-1]['content']=='工具探针':
                tools=[{'id':'fixture-tool','type':'function','function':{
                    'name':'read','arguments':json.dumps({'path':TEXT+'.txt'},ensure_ascii=False)}}]
            message={'role':'assistant','content':'准备读取' if tools else TEXT,'reasoning_content':PRIVATE}
            if tools:message['tool_calls']=tools
            response={'id':'fixture-'+str(len(seen)),'model':body['model']+'-v1',
                'system_fingerprint':'drifted-provider' if self.path.startswith('/bad/') else 'fixture-provider-v1',
                'choices':[{'message':message,'finish_reason':'tool_calls' if tools else 'stop'}],
                'usage':{'prompt_tokens':80,'completion_tokens':24,'total_tokens':104,
                    'prompt_tokens_details':{'cached_tokens':20},
                    'completion_tokens_details':{'reasoning_tokens':8}}}
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
            self.wfile.write(json.dumps(response,ensure_ascii=False).encode())
    upstream=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    Thread(target=upstream.serve_forever,daemon=True).start()
    features=('jsonObject','jsonSchema','strictTools','toolChoice','parallelToolCalls','promptCacheKey')
    def snapshot(label):
        planning={'schemaVersion':'refractagent-planning-v8','enabled':True,'defaultStrategy':'static',
            'billingUnit':'CNY','maxProductionCostByUnit':{'CNY':1},'maxCalls':10,
            'roles':{'efficient':'small','capable':'large'},
            'models':[{'id':key,'provider':'fixture','model':key,'deployment':'local',
                'contextWindow':16384,'maxOutputTokens':1024,'billingUnit':'CNY',
                'inputPer1k':.001,'cachedInputPer1k':.0002,'outputPer1k':.002,
                'capabilities':{'toolCalling':'verified','requestFeatures':{f:'verified' for f in features}}}
                for key in ('small','large')]}
        config={'schemaVersion':module.GATEWAY_CONFIG_V2,'planningRouting':planning,
            'providers':{'fixture':{'baseURL':f'http://127.0.0.1:{upstream.server_port}/{label}/v1',
                'tokenLimitParameter':'max_completion_tokens'}}}
        versions={'providers':{'fixture':'fixture-provider-v1'},'models':{'small':'small-v1','large':'large-v1'},
            'outputSemantics':{'fixture':{'parameter':'max_completion_tokens',
                'scope':'answer-and-reasoning-total','sourceSha256':'a'*64}}}
        return frozen_release(config,versions,publication_id=label)
    old,new,bad=(snapshot(label) for label in ('old','new','bad'))
    store=ReleaseStore.create(workspace/'registry',old,actor='本机安装验收')
    for value in (new,bad):assert store.add(value,constructed_evidence(value),actor='本机安装验收')['qualified']
    expiry=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    store.start_trial(new['releaseSha256'],max_tasks=1,expires=expiry,actor='本机安装验收',explicit=True)
    config={'schemaVersion':CONFIG,'releaseRegistry':str(store.root)}
    gateway=GovernedGateway(config,workspace/'runs');server=None
    def start(current):
        service=module.create_server(current,port=0,token='fixture-only-token')
        Thread(target=service.serve_forever,daemon=True).start()
        return service
    server=start(gateway)
    def request(path,value=None, *, authorized=True):
        headers={'Content-Type':'application/json'}
        if authorized:headers['Authorization']='Bearer fixture-only-token'
        req=Request(f'http://127.0.0.1:{server.server_port}'+path,
            data=None if value is None else json.dumps(value,ensure_ascii=False).encode(),headers=headers)
        try:
            with urlopen(req,timeout=10) as response:return response.status,response.read(),dict(response.headers)
        except HTTPError as error:
            with error:return error.code,error.read(),dict(error.headers)
    def post(path,value):
        status,raw,headers=request(path,value);assert status==200,(status,raw)
        return json.loads(raw),headers
    def ledgers():
        return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (workspace/'runs').glob('releases/*/planning/*.json')}
    try:
        assert request('/readyz',authorized=False)[0]==401
        assert request('/readyz')[0]==200 and not seen
        assert json.loads(request('/v1/models')[1])['data'][0]['id']==ALIAS
        initial={'model':ALIAS,'store':False,'metadata':{'refract_session':'fixture','refract_task':'tool'},
            'input':[{'role':'user','content':'工具探针'}],'tools':[{'type':'function','name':'read',
                'parameters':{'type':'object','properties':{'path':{'type':'string'}}}}]}
        first,headers=post('/v1/responses',initial)
        assert PRIVATE not in json.dumps(first,ensure_ascii=False)
        call=next(v for v in first['output'] if v['type']=='function_call')
        assert json.loads(call['arguments'])['path']==TEXT+'.txt'
        store.rollback(actor='本机安装验收',reason='验证在途任务绑定')
        second,_=post('/v1/responses',{**initial,'input':initial['input']+first['output']+[
            {'type':'function_call_output','call_id':call['call_id'],'output':'宿主固定结果'}]})
        assert second['output'][0]['content'][0]['text']==TEXT
        assert all(path.startswith('/new/') for path,_ in seen)
        assert seen[1][1]['messages'][-2]['reasoning_content']==PRIVATE
        chat={'model':ALIAS,'messages':[{'role':'user','content':'流式探针'}],
            'stream':True,'stream_options':{'include_usage':True}}
        status,wire,_=request('/v1/chat/completions',chat)
        assert status==200 and b'[DONE]' in wire and PRIVATE.encode() not in wire
        chunks=[json.loads(line[6:]) for line in wire.decode().splitlines()
            if line.startswith('data: ') and line!='data: [DONE]']
        assert ''.join(c['choices'][0].get('delta',{}).get('content','') for c in chunks if c.get('choices'))==TEXT
        usage=next(c['usage'] for c in chunks if c.get('usage'))
        assert usage['prompt_tokens_details']=={'cached_tokens':20}
        assert usage['completion_tokens_details']=={'reasoning_tokens':8}
        assert seen[-1][0].startswith('/old/')
        store.start_trial(bad['releaseSha256'],max_tasks=1,expires=expiry,actor='本机安装验收',explicit=True)
        rejected={'model':ALIAS,'messages':[{'role':'user','content':'身份漂移探针'}],
            'metadata':{'refract_session':'fixture','refract_task':'bad'}}
        status,_,bad_headers=request('/v1/chat/completions',rejected)
        assert status==400 and len(seen)==4
        run_id=bad_headers['X-RefractRouter-Outcome']
        failure,_=post('/v1/refract/outcomes',{'runId':run_id})
        assert failure['calls'][0]['status']=='unknown-usage'
        assert failure['calls'][0]['price_binding_confirmed'] is False
        before=ledgers();costs=monitor(store)['feeLanes']
        store.rollback(actor='本机安装验收',reason='身份漂移后回到基线')
        assert monitor(store)['feeLanes']==costs and ledgers()==before
        server.shutdown();server.server_close();gateway.close();server=None
        gateway=GovernedGateway(config,workspace/'runs');server=start(gateway)
        assert request('/v1/chat/completions',rejected)[0]==400 and len(seen)==4
        restored,_=post('/v1/refract/outcomes',{'runId':run_id})
        assert restored['calls']==failure['calls'] and ledgers()==before
        store.invalidate(old['releaseSha256'],actor='本机安装验收',reason='验证待复核健康状态')
        assert request('/readyz')[0]==503 and json.loads(request('/v1/models')[1])['data']==[]
        assert request('/v1/refract/outcomes',{'runId':run_id})[0]==200
        return {'status':'pass','scope':'installed-wheel-governed-http' if require_installed else 'source-governed-http',
            'paid_model_calls':0,'upstream_fixture_calls':len(seen),'responses_tool_reasoning_roundtrip':True,
            'unicode_buffered_sse_usage':True,'inflight_version_pinned_after_rollback':True,
            'model_identity_drift_stops_trial':True,'restart_no_redispatch':True,
            'unknown_fees_preserved':True,'pending_readyz_503_history_readable':True,
            'fixture_evidence_only':True,'actual_strategy_benefit_qualified':False,
            'actual_provider_compatibility_proven':False,'parent_child_budget_enforced':False}
    finally:
        if server is not None:server.shutdown();server.server_close()
        gateway.close();upstream.shutdown();upstream.server_close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workspace',required=True,type=Path)
    print(json.dumps(validate(parser.parse_args().workspace),ensure_ascii=False))


if __name__=='__main__':main()
