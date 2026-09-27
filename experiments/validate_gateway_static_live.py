"""两次 Static 真模型调用的有界接线验收；默认仅冻结零调用预检。"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from threading import Thread

from refractrouter.model_gateway import ModelGateway, HttpModelCaller, create_server, chat_messages, tool_schemas
from refractrouter.planning_config import compile_config, preview
from refractrouter.task_budget import request_input_bound


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--execute',action='store_true')
    parser.add_argument('--dsh-modules',type=Path)
    parser.add_argument('--probe-client',action='store_true')
    parser.add_argument('--input-limit',type=int,default=8192)
    parser.add_argument('--client',choices=['dsh','codex','hermes'],default='dsh')
    parser.add_argument('--codex-baseline',type=Path);parser.add_argument('--codex-baseline-model')
    parser.add_argument('--hermes-root',type=Path)
    args=parser.parse_args()
    if args.client=='dsh' and not args.dsh_modules: parser.error('DSH 需要模块路径')
    if args.client=='codex' and not (args.codex_baseline and args.codex_baseline_model):
        parser.error('Codex 需要明确的本机模型目录与基线模型')
    if args.client=='hermes' and not args.hermes_root: parser.error('Hermes 需要安装目录')
    input_limit=args.input_limit
    if not 1 <= input_limit <= 1048576: parser.error('输入上界必须在 1—1048576 内')
    raw=args.config.read_bytes();config=json.loads(raw);p=compile_config(config['planningRouting'])
    model=p['models'][p['roles']['efficient']]
    if p['parameters']['staticMode']!='fixed':
        raise ValueError('只验收固定高效角色的 Static')
    envelope={'configSha256':hashlib.sha256(raw).hexdigest(),'provider':model.provider,'model':model.api_model,
        'modelParameters':dict(model.request_options),'maxCalls':2,'maxInputBoundPerCall':input_limit,'maxOutputTokens':512,
        'billingUnit':model.billing_unit,'upperBound':2*(input_limit/1000*model.input_cost_per_1k+512/1000*model.output_cost_per_1k),
        'timeoutMs':60000,'httpRetries':0,'hostTools':1,'scenario':args.client+' 原生工具往返','strategy':'static'}
    if args.client=='codex':
        envelope['hostCatalogSha256']=hashlib.sha256(args.codex_baseline.read_bytes()).hexdigest()
        envelope['hostBaselineModel']=args.codex_baseline_model
    if not args.execute and not args.probe_client:
        args.output.mkdir(parents=True,exist_ok=False)
        check=ModelGateway(config,args.output/'runs');check.close()
        if not next(row for row in preview(config['planningRouting'])['strategies'] if row['id']=='static')['available']:
            raise ValueError('Static 预检不可用')
        (args.output/'preflight.json').write_text(json.dumps(envelope,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'modelCalls':0,**envelope},ensure_ascii=False));return
    if args.probe_client:
        args.output.mkdir(parents=True,exist_ok=False)
    elif json.loads((args.output/'preflight.json').read_text())!=envelope:
        raise ValueError('预检已改变，必须使用新批次')
    marker=args.output/'started';marker.open('x').close()
    class Bounded(HttpModelCaller):
        calls=0
        def guard(self,action):
            if self.calls>=2 or action['purpose']!='execute' or action['model']['model']!=model.api_model:
                raise ValueError('验收调用范围越界')
            if request_input_bound(action['messages'],action['tools'])>input_limit or action['model']['maxTokens']>512:
                raise ValueError('实际输入或输出超出冻结包络')
            self.calls+=1
        def __call__(self,action,options):
            self.guard(action);return super().__call__(action,options)
        def stream(self,action,options,on_text):
            self.guard(action);return super().stream(action,options,on_text)
    observed=[]
    class MeasuredGateway(ModelGateway):
        def complete(self,request,**kwargs):
            bound=request_input_bound(chat_messages(request['messages']),tool_schemas(request.get('tools',[])))
            observed.append({'inputBound':bound,'tools':len(request.get('tools',[]))})
            (args.output/'request-bounds.json').write_text(json.dumps(observed,indent=2))
            if args.probe_client: raise ValueError('零调用请求测量完成，未派发模型')
            if bound>input_limit: raise ValueError('客户端实际输入超过冻结上界，未派发模型')
            return super().complete(request,**kwargs)
    caller=Bounded(config['providers']);gw=MeasuredGateway(config,args.output/'runs',caller)
    server=create_server(gw,port=0);Thread(target=server.serve_forever,daemon=True).start()
    try:
        base=f'http://127.0.0.1:{server.server_port}/v1'
        if args.client=='dsh':
            command=['node','--experimental-strip-types','validation/dsh/plugin/scripts/check-gateway-tools.ts',str(args.dsh_modules),base,'512']
        elif args.client=='hermes':
            command=[str(args.hermes_root/'venv/bin/python'),'validation/hermes/check_gateway.py',str(args.hermes_root),base]
        else:
            import importlib.util
            spec=importlib.util.spec_from_file_location('catalog','validation/codex/model_catalog.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            catalog=module.catalog(json.loads(args.codex_baseline.read_text()),args.codex_baseline_model,gw.models())
            path=(args.output/'codex-models.json').resolve();path.write_text(json.dumps(catalog));path.chmod(0o600)
            command=['codex','exec','--ignore-user-config','--ignore-rules','--ephemeral','--skip-git-repo-check',
                '-s','read-only','-c','web_search="disabled"','-c','model_provider="refract-static-test"',
                '-c',f'model_catalog_json={json.dumps(str(path))}',
                '-c',f'model_providers.refract-static-test={{name="Refract Static",base_url="{base}",wire_api="responses",request_max_retries=0,stream_max_retries=0}}',
                '-m','refract/static','只做这项功能验收：通过终端工具执行 printf REFRACT_HOST_TOOL_OK 一次，收到结果后只回答 GATEWAY_CLIENT_OK。不要调用其他工具。']
        result=subprocess.run(command,text=True,capture_output=True,timeout=90)
        (args.output/'client-stdout.txt').write_text(result.stdout);(args.output/'client-stderr.txt').write_text(result.stderr)
        calls=[row for run in gw.runtime.runs.values() for row in run['budget'].records]
        summary={'success':result.returncode==0 and (args.client in ('dsh','hermes') or 'GATEWAY_CLIENT_OK' in result.stdout),'exitCode':result.returncode,'calls':caller.calls,'billingUnit':model.billing_unit,
            'charged':sum(row['charged'] for row in calls),'statuses':[row['status'] for row in calls],
            'userFirstTextMs':[row.get('userFirstTextMs') for row in calls], 'modelTtftMs':[row.get('ttft_ms') for row in calls],
            'toolOwner':args.client,'routerTasks':len(gw.runtime.runs),'automaticRetries':0}
        (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False))
        if args.probe_client and observed and caller.calls==0: return
        if not summary['success']: raise RuntimeError('真实验收未通过，保留原始证据，不自动重跑')
    finally:
        server.shutdown();server.server_close();gw.close()

if __name__=='__main__':main()
