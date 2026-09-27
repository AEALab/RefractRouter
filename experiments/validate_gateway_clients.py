"""使用已安装客户端与独立 Base URL 的零付费功能验收。"""
import argparse
import json
from pathlib import Path
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from refractrouter.model_gateway import ModelGateway, create_server


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--client',choices=['dsh','codex'],required=True)
    parser.add_argument('--dsh-modules',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    observed=[]
    class Upstream(BaseHTTPRequestHandler):
        def log_message(self,*a): pass
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            observed.append({'model':data['model'],'tools':len(data.get('tools',[])),
                'toolResults':sum(m['role']=='tool' for m in data['messages']),'stream':data['stream']})
            names=[t['function']['name'] for t in data.get('tools',[])]
            if len(observed)>2: raise RuntimeError('超过冻结两次调用上限')
            found=any(m['role']=='tool' and 'REFRACT_HOST_TOOL_OK' in str(m.get('content')) for m in data['messages'])
            if found:
                delta={'content':'GATEWAY_CLIENT_OK'};finish='stop'
            else:
                name='refract_local_echo' if args.client=='dsh' else 'exec_command'
                if name not in names: raise ValueError('宿主工具未暴露')
                params={} if args.client=='dsh' else {'cmd':'printf REFRACT_HOST_TOOL_OK','max_output_tokens':128}
                delta={'tool_calls':[{'index':0,'id':'fixture_host_tool_1','type':'function','function':{'name':name,'arguments':json.dumps(params)}}]};finish='tool_calls'
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
            for value in ({'choices':[{'index':0,'delta':delta,'finish_reason':None}]},
                          {'choices':[{'index':0,'delta':{},'finish_reason':finish}]},
                          {'choices':[],'usage':{'prompt_tokens':100,'completion_tokens':20}}):
                self.wfile.write(b'data: '+json.dumps(value).encode()+b'\n\n');self.wfile.flush()
            self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
    up=ThreadingHTTPServer(('127.0.0.1',0),Upstream);threading.Thread(target=up.serve_forever,daemon=True).start()
    config={'schemaVersion':'refractagent-planning-v1','enabled':True,'defaultStrategy':'static',
        'maxProductionCost':10,'maxCalls':2,'timeoutMs':60000,
        'models':[{'id':'fixture','provider':'fixture','model':'fixture','contextWindow':1000000,
            'maxOutputTokens':256,'inputPer1k':.001,'outputPer1k':.002,'deployment':'local'}],
        'roles':{'efficient':'fixture'}}
    gw=ModelGateway({'planningRouting':config,'providers':{'fixture':{'baseURL':f'http://127.0.0.1:{up.server_port}/v1'}}},args.output/'runs')
    server=create_server(gw,port=0);threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}/v1'
    if args.client=='dsh':
        if not args.dsh_modules: raise ValueError('请指定实际 DSH 模块目录')
        command=['node','--experimental-strip-types','validation/dsh/plugin/scripts/check-gateway-tools.ts',str(args.dsh_modules),base]
    else:
        command=['codex','exec','--ignore-user-config','--ignore-rules','--ephemeral','--skip-git-repo-check',
            '-s','read-only','-c','web_search="disabled"','-c','model_provider="refract-fixture"',
            '-c',f'model_providers.refract-fixture={{name="Refract fixture",base_url="{base}",wire_api="responses",request_max_retries=0,stream_max_retries=0}}',
            '-m','refract/static','请执行 printf REFRACT_HOST_TOOL_OK 一次，收到标记后回答 GATEWAY_CLIENT_OK。']
    try:
        result=subprocess.run(command,text=True,capture_output=True,timeout=60)
        success=result.returncode==0 and 'GATEWAY_CLIENT_OK' in result.stdout if args.client=='codex' else result.returncode==0
        summary={'client':args.client,'success':success,'exitCode':result.returncode,'upstreamCalls':observed,'paidCalls':0,
            'routerTasks':len(gw.runtime.runs),'hostToolResultReceived':any(r['toolResults'] for r in observed)}
        (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        (args.output/'client-stdout.txt').write_text(result.stdout)
        (args.output/'client-stderr.txt').write_text(result.stderr)
        print(json.dumps(summary,ensure_ascii=False))
        if not success: raise RuntimeError('接线验收未通过，查看本地日志')
    finally:
        server.shutdown();server.server_close();up.shutdown();up.server_close();gw.close()

if __name__=='__main__':main()
