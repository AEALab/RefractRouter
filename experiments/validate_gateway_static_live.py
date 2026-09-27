"""两次 Static 真模型调用的有界接线验收；默认仅冻结零调用预检。"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from threading import Thread

from refractrouter.model_gateway import ModelGateway, HttpModelCaller, create_server
from refractrouter.planning_config import compile_config, preview
from refractrouter.task_budget import request_input_bound


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--execute',action='store_true')
    parser.add_argument('--dsh-modules',type=Path,required=True);args=parser.parse_args()
    raw=args.config.read_bytes();config=json.loads(raw);p=compile_config(config['planningRouting'])
    model=p['models'][p['roles']['efficient']]
    if p['parameters']['staticMode']!='fixed':
        raise ValueError('只验收固定高效角色的 Static')
    envelope={'configSha256':hashlib.sha256(raw).hexdigest(),'provider':model.provider,'model':model.api_model,
        'modelParameters':dict(model.request_options),'maxCalls':2,'maxInputBoundPerCall':8192,'maxOutputTokens':512,
        'billingUnit':model.billing_unit,'upperBound':2*(8192/1000*model.input_cost_per_1k+512/1000*model.output_cost_per_1k),
        'timeoutMs':60000,'httpRetries':0,'hostTools':1,'scenario':'DSH 原生 echo 工具往返','strategy':'static'}
    if not args.execute:
        args.output.mkdir(parents=True,exist_ok=False)
        check=ModelGateway(config,args.output/'runs');check.close()
        if not next(row for row in preview(config['planningRouting'])['strategies'] if row['id']=='static')['available']:
            raise ValueError('Static 预检不可用')
        (args.output/'preflight.json').write_text(json.dumps(envelope,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'modelCalls':0,**envelope},ensure_ascii=False));return
    if json.loads((args.output/'preflight.json').read_text())!=envelope:
        raise ValueError('预检已改变，必须使用新批次')
    marker=args.output/'started';marker.open('x').close()
    class Bounded(HttpModelCaller):
        calls=0
        def guard(self,action):
            if self.calls>=2 or action['purpose']!='execute' or action['model']['model']!=model.api_model:
                raise ValueError('验收调用范围越界')
            if request_input_bound(action['messages'],action['tools'])>8192 or action['model']['maxTokens']>512:
                raise ValueError('实际输入或输出超出冻结包络')
            self.calls+=1
        def __call__(self,action,options):
            self.guard(action);return super().__call__(action,options)
        def stream(self,action,options,on_text):
            self.guard(action);return super().stream(action,options,on_text)
    caller=Bounded(config['providers']);gw=ModelGateway(config,args.output/'runs',caller)
    server=create_server(gw,port=0);Thread(target=server.serve_forever,daemon=True).start()
    try:
        result=subprocess.run(['node','--experimental-strip-types','validation/dsh/plugin/scripts/check-gateway-tools.ts',
            str(args.dsh_modules),f'http://127.0.0.1:{server.server_port}/v1','512'],text=True,capture_output=True,timeout=90)
        (args.output/'client-stdout.txt').write_text(result.stdout);(args.output/'client-stderr.txt').write_text(result.stderr)
        calls=[row for run in gw.runtime.runs.values() for row in run['budget'].records]
        summary={'success':result.returncode==0,'exitCode':result.returncode,'calls':caller.calls,'billingUnit':model.billing_unit,
            'charged':sum(row['charged'] for row in calls),'statuses':[row['status'] for row in calls],
            'userFirstTextMs':[row.get('userFirstTextMs') for row in calls], 'modelTtftMs':[row.get('ttft_ms') for row in calls],
            'toolOwner':'DSH','routerTasks':len(gw.runtime.runs),'automaticRetries':0}
        (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False))
        if not summary['success']: raise RuntimeError('真实验收未通过，保留原始证据，不自动重跑')
    finally:
        server.shutdown();server.server_close();gw.close()

if __name__=='__main__':main()
