"""源码外安装验收：原生回答/思考费用与真实本机HTTP线缆；上游完全为夹具。"""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread

import refractrouter.model_gateway as module

TEXT='中文预算🦀🚀'


def validate(workspace,*,require_installed=True):
    source=Path(__file__).resolve().parents[1]/'src'
    if require_installed and Path(module.__file__).resolve().is_relative_to(source):
        raise ValueError('必须使用源码目录外实际安装的wheel')
    workspace=Path(workspace);workspace.mkdir(parents=True,exist_ok=True)
    seen=[];cancelled=[False]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_args):pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));seen.append(body)
            answer_only='max_tokens' in body
            assert body['max_tokens' if answer_only else 'max_completion_tokens']==(131072 if answer_only else 32768)
            outputs,reasoning=(250000,249000) if answer_only else (20000,19000)
            usage={'prompt_tokens':100,'completion_tokens':outputs,'total_tokens':100+outputs,
                'completion_tokens_details':{'reasoning_tokens':reasoning},
                'prompt_tokens_details':{'cached_tokens':0}}
            last=body['messages'][-1]['content']
            if last=='cancel':cancelled[0]=True
            if last=='unknown':usage=None
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream' if body['stream'] else 'application/json');self.end_headers()
            if body['stream']:
                frames=[{'id':'fixture','choices':[{'index':0,'delta':{'content':c},'finish_reason':None}]} for c in TEXT]
                frames.append({'id':'fixture','choices':[{'index':0,'delta':{},'finish_reason':'stop'}]})
                if usage is not None:frames.append({'id':'fixture','choices':[],'usage':usage})
                for frame in frames:self.wfile.write(('data: '+json.dumps(frame,ensure_ascii=False)+'\n\n').encode())
                self.wfile.write(b'data: [DONE]\n\n')
            else:
                value={'id':'fixture','choices':[{'message':{'role':'assistant','content':TEXT},'finish_reason':'stop'}]}
                if usage is not None:value['usage']=usage
                self.wfile.write(json.dumps(value,ensure_ascii=False).encode())
    upstream=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    Thread(target=upstream.serve_forever,daemon=True).start();gateways=[]
    def gateway(label,*,scope='answer-only',budget=1000):
        parameter='max_tokens' if scope=='answer-only' else 'max_completion_tokens'
        planning={'schemaVersion':'refractagent-planning-v8','enabled':True,'defaultStrategy':'static',
            'billingUnit':'CNY','maxProductionCostByUnit':{'CNY':budget},'maxCalls':10,
            'roles':{'efficient':'native','capable':'native'},'models':[{
                'id':'native','provider':'fixture','model':'native','deployment':'local','billingUnit':'CNY',
                'contextWindow':1_024_000,'maxOutputTokens':131072 if scope=='answer-only' else 32768,
                'inputPer1k':.45,'outputPer1k':.45,'outputBudget':{
                    'scope':scope,'parameter':parameter,'sourceSha256':'a'*64},'capabilities':{'toolCalling':'verified'}}]}
        value=module.ModelGateway({'schemaVersion':module.GATEWAY_CONFIG_V2,'planningRouting':planning,
            'providers':{'fixture':{'baseURL':f'http://127.0.0.1:{upstream.server_port}/v1',
                'tokenLimitParameter':parameter}}},workspace/label)
        gateways.append(value);return value
    def request(text='探针'):
        return {'model':'refract/static','messages':[{'role':'user','content':text}]}
    try:
        low=gateway('insufficient',budget=70)
        try:low.complete(request())
        except ValueError:pass
        else:raise AssertionError('不足以覆盖原生思考的预算应拒绝派发')
        assert not seen and all(not run['budget'].records for run in low.runtime.runs.values())
        for scope in ('answer-only','answer-and-reasoning-total'):
            current=gateway(scope,scope=scope);result=current.complete(request())
            assert result['choices'][0]['message']['content']==TEXT
            texts=[];streamed=current.complete({**request(),'stream':True},on_text=lambda _meta,text:texts.append(text))
            assert ''.join(texts)==TEXT and streamed['usage']==result['usage']
            for run in current.runtime.runs.values():
                row=run['budget'].records[0];assert row['status']=='billed'
                assert row['wire_output_tokens']==(131072 if scope=='answer-only' else 32768)
                if scope=='answer-only':
                    assert row['charged']==112.545 and row['reserved']==460.8
                    assert row['observed_answer_tokens']==1000 and row['observed_reasoning_tokens']==249000
        unknown=gateway('unknown')
        try:unknown.complete(request('unknown'))
        except ValueError:pass
        else:raise AssertionError('缺少用量不能视为零费用')
        record=next(iter(unknown.runtime.runs.values()));row=record['budget'].records[0]
        assert row['status']=='unknown-usage' and row['charged']==row['reserved']==460.8
        unknown.runtime.handle({'op':'end','runId':record['id']});assert row['charged']==460.8
        final=gateway('cancelled')
        try:final.complete(request('cancel'),cancelled=lambda:cancelled[0])
        except (ConnectionError,RuntimeError):pass
        else:raise AssertionError('取消后不能交付候选')
        record=next(iter(final.runtime.runs.values()));row=record['budget'].records[0]
        assert row['status']=='billed' and row['disposition']=='discarded' and row['charged']==112.545
        assert record['status']=='cancelled' and len(seen)==6
        return {'status':'pass','scope':'installed-native-output-http' if require_installed else 'source-native-output-http',
            'paid_model_calls':0,'fixture_http_calls':len(seen),'native_answer_limit':131072,
            'answer_only_total_output':250000,'reasoning_tokens':249000,'pure_answer_tokens':1000,
            'protected_fixture_cost_cny':460.8,'known_fixture_cost_cny':112.545,
            'insufficient_budget_zero_dispatch':True,'total_output_native_limit':32768,
            'unicode_stream_usage':True,'cancelled_known_usage_settled':True,
            'unknown_reserve_preserved':True,'actual_provider_verified':False}
    finally:
        for current in gateways:current.close()
        upstream.shutdown();upstream.server_close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workspace',type=Path,required=True)
    print(json.dumps(validate(parser.parse_args().workspace),ensure_ascii=False))


if __name__=='__main__':main()
