"""node-as-tool 三路线先导：默认冻结预检，真实运行必须精确批准摘要和 AFP 上限。"""
import argparse
import json
from pathlib import Path
from refractrouter.node_tool_study import prepare,run,write


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir",type=Path,required=True);p.add_argument("--frozen",type=Path)
    p.add_argument("--dsh-node-modules",type=Path);p.add_argument("--python",type=Path)
    p.add_argument("--prior-result",type=Path,action="append",default=[])
    p.add_argument("--resume-samples","--resume-optimization",dest="resume_optimization",type=Path,action="append",default=[])
    p.add_argument("--approved-protocol-sha256");p.add_argument("--approved-afp",type=float)
    m=p.add_mutually_exclusive_group();m.add_argument("--rehearse",action="store_true");m.add_argument("--execute-paid-run",action="store_true")
    a=p.parse_args()
    if a.rehearse or a.execute_paid_run:
        if not all((a.frozen,a.dsh_node_modules,a.python)):p.error("需要冻结文件、DSH 模块和当前 Python")
        result=run(json.loads(a.frozen.read_text()),a.output_dir,node_modules=a.dsh_node_modules,python=a.python,
            live=a.execute_paid_run,approved_hash=a.approved_protocol_sha256,approved_afp=a.approved_afp)
        print(json.dumps({k:result[k] for k in ("status","simulated","realModelCalls","actualOrReservedAfp")},ensure_ascii=False))
        return 0 if result["status"].startswith("completed") else 1
    frozen=prepare(a.prior_result,a.resume_optimization);a.output_dir.mkdir(parents=True,exist_ok=False);write(a.output_dir/"frozen.json",frozen)
    print(json.dumps({k:frozen[k] for k in ("protocolSha256","maxModelCalls","productionAfpUpperBound","budgetIncludes")},ensure_ascii=False))
    return 0


if __name__=="__main__":raise SystemExit(main())
