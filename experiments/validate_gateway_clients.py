"""使用已安装客户端与独立 Base URL 的零付费功能验收。"""
import argparse
import json
from pathlib import Path
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from refractrouter.model_gateway import ModelGateway, create_server


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--client',choices=['dsh','codex','hermes'],required=True)
    parser.add_argument('--dsh-modules',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--codex-baseline',type=Path);parser.add_argument('--codex-baseline-model')
    parser.add_argument('--hermes-root',type=Path)
    parser.add_argument('--hermes-python',type=Path)
    parser.add_argument('--strategy',choices=['static','stage','task','composite','advisor'],default='static')
    parser.add_argument('--scenario',choices=['normal','advisor-redo'],default='normal')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    if args.scenario == 'advisor-redo' and args.strategy != 'advisor':
        parser.error('受控返工场景只适用于 Advisor')
    observed=[]
    state={'executorCalls':0,'judgeCalls':0}
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self,*a): pass
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            observed.append({'model':data['model'],'tools':len(data.get('tools',[])),
                'toolResults':sum(m['role']=='tool' for m in data['messages']),'stream':data['stream']})
            names=[t['function']['name'] for t in data.get('tools',[])]
            if len(observed)>5: raise RuntimeError('超过客户端接线冻结五次调用上限')
            if data['model']=='judge-fixture':
                state['judgeCalls']+=1
                if args.strategy in ('task','composite'):
                    payload={'answers':{'candidates':{
                        'fixture':{'score':.95,'missingInformation':0},
                        'capable-fixture':{'score':.2,'missingInformation':0}}}}
                else:
                    verdict=('REDO' if args.scenario=='advisor-redo' and state['judgeCalls']==1
                             else 'APPROVE')
                    payload={'verdict':verdict}
                    if verdict=='REDO': payload['feedback']='调用宿主工具取得标记后，只回答 GATEWAY_CLIENT_OK。'
                delta={'content':json.dumps(payload,ensure_ascii=False)};finish='stop'
            else:
                state['executorCalls']+=1
                found=any(m['role']=='tool' and 'REFRACT_HOST_TOOL_OK' in str(m.get('content')) for m in data['messages'])
                name={'dsh':'refract_local_echo','codex':'exec_command','hermes':'terminal'}[args.client]
                if found:
                    delta={'content':'GATEWAY_CLIENT_OK'};finish='stop'
                elif args.scenario=='advisor-redo' and state['executorCalls']==1:
                    delta={'content':'错误候选：未执行工具但声称已经完成。'};finish='stop'
                else:
                    if name not in names: raise ValueError('宿主工具未暴露')
                    params={} if args.client=='dsh' else {'cmd':'printf REFRACT_HOST_TOOL_OK','max_output_tokens':128}
                    if args.client=='hermes': params={'command':'printf REFRACT_HOST_TOOL_OK'}
                    delta={'tool_calls':[{'index':0,'id':'fixture_host_tool_1','type':'function','function':{'name':name,'arguments':json.dumps(params)}}]};finish='tool_calls'
            if not data['stream']:
                message={key:value for key,value in delta.items() if key!='tool_calls'}
                if 'tool_calls' in delta:
                    message['tool_calls']=[{key:value for key,value in row.items() if key!='index'}
                                           for row in delta['tool_calls']]
                body=json.dumps({'choices':[{'index':0,'message':message,'finish_reason':finish}],
                    'usage':{'prompt_tokens':100,'completion_tokens':20}}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
                return
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            for value in ({'choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                          {'choices':[{'index':0,'delta':{},'finish_reason':finish}]},
                          {'choices':[],'usage':{'prompt_tokens':100,'completion_tokens':20}}):
                self.wfile.write(b'data: '+json.dumps(value).encode()+b'\n\n');self.wfile.flush()
            self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
    up=ThreadingHTTPServer(('127.0.0.1',0),Upstream);threading.Thread(target=up.serve_forever,daemon=True).start()
    schema='refractagent-planning-v6' if args.strategy in ('advisor','composite') else \
        'refractagent-planning-v3' if args.strategy=='task' else 'refractagent-planning-v1'
    config={'schemaVersion':schema,'enabled':True,'defaultStrategy':args.strategy,
        'maxProductionCost':10,'maxCalls':8,'timeoutMs':60000,
        'models':[{'id':'fixture','provider':'fixture','model':'fixture','contextWindow':1000000,
            'maxOutputTokens':256,'inputPer1k':.001,'outputPer1k':.002,'deployment':'local',
            'capabilityCard':'适合普通工具任务','capabilities':{'mainExecutor':True,
                'toolCalling':'verified','modalities':{}}}],
        'roles':{'efficient':'fixture'}}
    if args.strategy in ('stage','task','composite'):
        config['models'][0]['reasoningEffort']='low'
        config['models'].append({**config['models'][0], 'id':'capable-fixture',
            'model':'capable-fixture','capabilityCard':'适合复杂工具任务'})
        config['roles']['capable']='capable-fixture'
        if args.strategy in ('task','composite'):
            config['models'].append({**config['models'][0], 'id':'judge-fixture',
                'model':'judge-fixture','capabilityCard':'',
                'capabilities':{'mainExecutor':False,'toolCalling':'unknown','modalities':{}}})
            route={'pool':['fixture','capable-fixture'],'fallback':'capable-fixture',
                'judge':{'type':'llm','modelId':'judge-fixture'},'threshold':.8,
                'maxInputChars':12000,'maxExecutionOutputTokens':256}
            if args.strategy=='task': config['task']=route
            else: config['composite']={**{k:v for k,v in route.items() if k!='fallback'},
                'takeover':'capable-fixture','stage':{'mode':'rules','window':3,
                    'threshold':.5,'holdTurns':2}}
    elif args.strategy=='advisor':
        config['models'].append({**config['models'][0], 'id':'judge-fixture', 'model':'judge-fixture'})
        config['advisor']={'executor':'fixture','judge':{'type':'llm','modelId':'judge-fixture'},
            'threshold':.8,'judgeTimeoutMs':30000,'maxJudgeInputBytes':65536,
            'maxExecutionOutputTokens':256,'maxJudgeOutputTokens':256}
    elif args.client=='hermes': config['models'][0]['reasoningEffort']='low'
    if args.client=='hermes':
        for model in config['models']: model['reasoningEffort']='low'
    gw=ModelGateway({'planningRouting':config,'providers':{'fixture':{'baseURL':f'http://127.0.0.1:{up.server_port}/v1'}}},args.output/'runs')
    server=create_server(gw,port=0);threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}/v1'
    if args.client=='dsh':
        if not args.dsh_modules: raise ValueError('请指定实际 DSH 模块目录')
        command=['node','--experimental-strip-types','validation/dsh/plugin/scripts/check-gateway-tools.ts',str(args.dsh_modules),base,'256',args.strategy]
    elif args.client=='hermes':
        if not args.hermes_root: raise ValueError('请指定本机 Hermes 安装目录')
        python=args.hermes_python or args.hermes_root/'venv/bin/python'
        command=[str(python), 'validation/hermes/check_gateway.py',str(args.hermes_root),base,args.strategy]
    else:
        command=['codex','exec','--ignore-user-config','--ignore-rules','--ephemeral','--skip-git-repo-check',
            '-s','read-only','-c','web_search="disabled"','-c','model_provider="refract-fixture"',
            '-c',f'model_providers.refract-fixture={{name="Refract fixture",base_url="{base}",wire_api="responses",request_max_retries=0,stream_max_retries=0}}',
            '-m','refract/'+args.strategy,'请执行 printf REFRACT_HOST_TOOL_OK 一次，收到标记后回答 GATEWAY_CLIENT_OK。']
    if args.client == 'codex' and args.codex_baseline:
        import importlib.util
        spec=importlib.util.spec_from_file_location('codex_catalog','validation/codex/model_catalog.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        adapted=module.catalog(json.loads(args.codex_baseline.read_text()),args.codex_baseline_model,gw.models())
        path=(args.output/'codex-models.json').resolve()
        path.write_text(json.dumps(adapted));path.chmod(0o600)
        command[-1:-1]=['-c',f'model_catalog_json={json.dumps(str(path))}']
    try:
        result=subprocess.run(command,text=True,capture_output=True,timeout=60)
        success=result.returncode==0 and 'GATEWAY_CLIENT_OK' in result.stdout if args.client=='codex' else result.returncode==0
        summary={'client':args.client,'strategy':args.strategy,'scenario':args.scenario,
            'success':success,'exitCode':result.returncode,'upstreamCalls':observed,'paidCalls':0,
            'routerTasks':len(gw.runtime.runs),'hostToolResultReceived':any(r['toolResults'] for r in observed)}
        (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        (args.output/'client-stdout.txt').write_text(result.stdout)
        (args.output/'client-stderr.txt').write_text(result.stderr)
        print(json.dumps(summary,ensure_ascii=False))
        if not success: raise RuntimeError('接线验收未通过，查看本地日志')
    finally:
        server.shutdown();server.server_close();up.shutdown();up.server_close();gw.close()

if __name__=='__main__':main()
