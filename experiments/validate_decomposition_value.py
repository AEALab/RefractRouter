"""六条冻结结构判别案例；默认零调用，真实调用须绑定预检摘要且使用新目录。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen

from refractrouter.decomposition_jev import DecompositionJevRuntime
from refractrouter.live_execution import complexity_gate

CASES = [
    ('arithmetic','分别计算方案甲12乘8和方案乙15乘6的总价，再比较差额。','skip'),
    ('definition','用一句话解释缓存命中率。','skip'),
    ('contracts','合成资料：合同甲规定交付后30天付款，延迟交付每天扣款1%；合同乙规定验收前全款支付，保修期限未约定。分别独立审查每份合同的付款、违约与保修风险，各给出修改条款，最后并列汇总。','SEPARABLE'),
    ('dependent-fix','合成开发任务：先运行测试取得当前失败堆栈，必须根据实际堆栈定位同一函数的根因，再修改该函数，最后重跑原测试确认修复。修改方案现在尚不能确定。','COUPLED'),
    ('independent-audits','合成项目：A模块负责鉴权，B模块负责日志保留，二者没有调用依赖。分别独立审查A的权限边界和B的数据保留规则，各产出问题列表与对应证据，最后合并报告。','SEPARABLE'),
    ('dependent-schema','合成数据任务：从未知格式文件提取实际schema后，才能根据发现的字段编写转换脚本；运行脚本产生结果后，再核验实际输出。没有schema不能开始脚本实现。','COUPLED'),
]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--freeze-sha256')
    args=parser.parse_args()
    runtime=DecompositionJevRuntime(args.output/'ledger')
    requests=[{'identity':'value-v3/'+cid,'task':task,'context':'',
        'config':{'jev':{'route':'openrouter'}},'maxCostCny':.01,'threshold':.65,
        'timeoutMs':30000} for cid,task,_ in CASES]
    previews=[runtime.prepare(r) for r in requests]
    frozen={'cases':[{'id':cid,'task':t,'expected':e,'preview':p} for (cid,t,e),p in zip(CASES,previews)],
        'ruleVersion':'automatic-decomposition-hybrid-v3','calls':sum(p['action']=='ready' for p in previews),
        'maximumCny':sum(p.get('maximumCostCny',0) for p in previews),'httpRetries':0,
        'sources':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                   [Path(__file__).relative_to(Path.cwd()),Path('src/refractrouter/decomposition_decision.py'),Path('src/refractrouter/decomposition_jev.py'),Path('src/refractrouter/live_execution.py')]}}
    digest=hashlib.sha256(json.dumps(frozen,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if args.execute and args.freeze_sha256!=digest:parser.error('必须绑定当前零调用预检摘要')
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'preflight.json').write_text(json.dumps({**frozen,'sha256':digest},ensure_ascii=False,indent=2)+'\n')
    if not args.execute:
        print(json.dumps({'sha256':digest,'maximumCny':frozen['maximumCny'],'calls':frozen['calls']}));return
    results=[]
    for (cid,_,expected),request in zip(CASES,requests):
        action=runtime.begin(request)
        started=time.monotonic()
        if action['action']=='jev':
            try:
                payload=json.dumps(action['payload'],ensure_ascii=False).encode()
                req=Request(action['endpoint'],data=payload,headers={'Content-Type':'application/json',
                    'Authorization':'Bearer '+os.environ[action['credentialRef']]},method='POST')
                with urlopen(req,timeout=30) as response:raw=json.load(response)
                action=runtime.complete({'callId':action['callId'],'result':raw,'latencyMs':round((time.monotonic()-started)*1000)})
            except Exception:
                runtime.stop(action['callId']);raise
        evidence=action['evidence']
        gate=complexity_gate({'task':request['task']},'',tools_allowed=True,decomposition=evidence)
        passed=(evidence.get('reason')=='trivial-workload' if expected=='skip' else evidence['verdict']==expected)
        results.append({'id':cid,'expected':expected,'matched':passed,'evidence':{k:v for k,v in evidence.items() if k!='recordPath'},'gate':{k:v for k,v in gate.items() if k!='local_decision'}})
        (args.output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'id':cid,'verdict':evidence['verdict'],'matched':passed,'costCny':evidence.get('costCny',0)},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
