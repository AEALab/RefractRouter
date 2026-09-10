"""#39/#40 正式对照入口；默认只预检，实测保留零重试与完整包络。"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

from experiments.prepare_joint_research import prepare
from experiments.rehearse_research_execution import DevelopmentClient
from refractrouter.dag_study_execution import write_json
from refractrouter.joint_research import preflight, run, historical_materials
from refractrouter.manifest import load_model_manifest
from refractrouter.openai_compatible import OpenAICompatibleClient
from refractrouter.research_protocol import digest

ROOT=Path(__file__).resolve().parents[1]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--demo',action='store_true')
    group.add_argument('--execute',action='store_true')
    parser.add_argument('--protocol-sha256')
    args=parser.parse_args(argv)
    protocol=json.loads(args.protocol.read_text())
    if digest(protocol)!=digest(prepare()): parser.error('冻结材料、协议或代码变更，请建立新版本')
    manifest=load_model_manifest(ROOT/'data/model-manifests/volcengine-agent-plan.json')
    excluded=historical_materials(ROOT,args.protocol)
    preview=preflight(protocol,manifest,excluded_materials=excluded)
    if args.execute and args.protocol_sha256!=preview['protocol_sha256']: parser.error('真实执行需绑定冻结摘要')
    if not args.demo and not args.execute:
        args.output_dir.mkdir(parents=True,exist_ok=False)
        write_json(args.output_dir/'preflight.json',preview)
        print(json.dumps({k:preview[k] for k in ('protocol_sha256','maximum_calls','budget','required_under_assumed_sd')},ensure_ascii=False))
        return 0
    if args.demo:
        with patch('socket.socket',side_effect=AssertionError('模拟禁止网络')):
            result=run(protocol,manifest,args.output_dir,DevelopmentClient(protocol['tasks']),simulated=True,excluded_materials=excluded)
    else:
        result=run(protocol,manifest,args.output_dir,OpenAICompatibleClient(max_retries=0),excluded_materials=excluded)
    print(json.dumps({'status':result['status'],'calls':len(result['calls']),'charged':result['charged'],
        'test_runs':sum(r.get('split')=='test' for r in result['runs'])},ensure_ascii=False))
    return 0 if result['status'] in ('finished','simulated') else 1


if __name__=='__main__': raise SystemExit(main())
