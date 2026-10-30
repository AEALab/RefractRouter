"""冻结六臂异构选模协议并可执行零网络演练；没有付费模式。"""
import argparse
from pathlib import Path
import sys
from refractrouter.heterogeneous_study import prepare, rehearse, write


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--rehearse',action='store_true')
    p.add_argument('--dsh-node-modules',type=Path)
    a=p.parse_args()
    if a.rehearse and not a.dsh_node_modules:p.error('演练需要已安装DSH模块路径')
    a.output_dir.mkdir(exist_ok=False)
    frozen=prepare();write(a.output_dir/'frozen.json',frozen)
    if a.rehearse:
        result=rehearse(frozen,a.output_dir/'rehearsal',node_modules=a.dsh_node_modules,python=sys.executable)
        print(result['status'],result['realModelCalls'])
    print('maxModelCalls',frozen['maxModelCalls'],'fullCapacityAfpUpperBound',frozen['fullCapacityAfpUpperBound'])


if __name__=='__main__':main()
