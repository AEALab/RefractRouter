"""调用已安装 Hermes 原生 Agent 循环；只控制本次验收的模型与工具范围。"""
import json
import os
from pathlib import Path
import sys

root, base = sys.argv[1:3]
sys.path.insert(0, root)
if not os.environ.get('HERMES_HOME'):
    home=Path.home()/'.hermes'
    active=(home/'active_profile').read_text().strip() if (home/'active_profile').exists() else 'default'
    selected=home if active=='default' else home/'profiles'/active
    if not selected.is_dir(): raise ValueError('当前 Hermes profile 不存在')
    os.environ['HERMES_HOME']=str(selected)
from urllib.request import urlopen
with urlopen(base+'/models') as response:
    advertised=json.load(response)
entry=next(row for row in advertised['data'] if row['id']=='refract/static')
efforts=entry['refract']['acceptedReasoningEfforts']
if len(efforts)!=1: raise ValueError('本次 Hermes 验收要求一个明确冻结的推理档位')

os.environ['HERMES_STREAM_RETRIES'] = '0'
from run_agent import AIAgent

chunks=[]
agent=AIAgent(model='refract/static',base_url=base,api_key='local-router-test',
    provider='custom',api_mode='chat_completions',enabled_toolsets=['terminal'],
    reasoning_config={'effort':efforts[0]},max_iterations=3,max_tokens=256,quiet_mode=True,skip_memory=True,
    skip_background_review=True,skip_context_files=True,load_soul_identity=False,
    save_trajectories=False,run_budget_seconds=45,
    stream_delta_callback=lambda text,**kwargs:chunks.append(str(text)))
agent._api_max_retries=1
agent._auto_recovery_cycles=0
agent._fallback_chain=[]
agent._fallback_model=None
agent.client=agent.client.with_options(max_retries=0)
if hasattr(agent,'_client_kwargs'): agent._client_kwargs['max_retries']=0
result=agent.run_conversation('请用 terminal 执行 printf REFRACT_HOST_TOOL_OK 一次；收到工具结果后只回答 GATEWAY_CLIENT_OK。')
messages=result.get('messages',[])
passed='GATEWAY_CLIENT_OK' in str(result.get('final_response',''))
tools=[m for m in messages if m.get('role')=='tool']
summary={'client':'hermes','success':passed and len(tools)==1,
    'hostToolResults':len(tools),'streamCallbacks':len(chunks),'apiCalls':result.get('api_calls'),
    'error':result.get('error')}
print(json.dumps(summary,ensure_ascii=False))
if not summary['success']: raise SystemExit(1)
