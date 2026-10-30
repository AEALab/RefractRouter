"""本机版本发布管理；所有命令零模型调用，不提供远程管理或在线训练接口。"""
import argparse
import hashlib
import json
from pathlib import Path

from .readonly_facts import strict_json
from .release_governance import ReleaseStore, frozen_release, HASH
from .governed_gateway import CONFIG


def read(path, expected=None):
    raw=Path(path).read_bytes()
    if len(raw)>16*1024*1024:raise ValueError('管理材料超过16MiB上限')
    if expected is not None and (HASH.fullmatch(expected) is None or hashlib.sha256(raw).hexdigest()!=expected):
        raise ValueError('管理材料原始字节摘要不符')
    return strict_json(raw,maximum_bytes=16*1024*1024)


def write(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='operation',required=True)
    freeze=sub.add_parser('freeze',help='固定配置、价格、实现与版本声明，不产生资格')
    freeze.add_argument('--config',required=True,type=Path);freeze.add_argument('--versions',required=True,type=Path)
    freeze.add_argument('--name',required=True);freeze.add_argument('--output',required=True,type=Path)
    init=sub.add_parser('init',help='显式采用已有配置为基线，不能覆盖历史')
    init.add_argument('--snapshot',required=True,type=Path);init.add_argument('--snapshot-sha256',required=True)
    init.add_argument('--gateway-config-output',required=True,type=Path)
    register=sub.add_parser('register',help='登记独立验收证据，未合格版本仍拒绝试用')
    register.add_argument('--snapshot',required=True,type=Path);register.add_argument('--snapshot-sha256',required=True)
    register.add_argument('--evidence',required=True,type=Path);register.add_argument('--evidence-sha256',required=True)
    trial=sub.add_parser('trial',help='有界、显式启用新任务试用')
    trial.add_argument('--release',required=True);trial.add_argument('--max-tasks',required=True,type=int)
    trial.add_argument('--expires',required=True);trial.add_argument('--explicit-trial',action='store_true')
    stop=sub.add_parser('stop',help='停止新任务试用，原任务和费用不变')
    rollback=sub.add_parser('rollback',help='新任务回到原基线，旧任务继续结算')
    invalidate=sub.add_parser('invalidate',help='版本漂移或其他未知使资格待复核')
    invalidate.add_argument('--release',required=True)
    history=sub.add_parser('history',help='查询保留的版本、任务归属与管理事件')
    inspect=sub.add_parser('inspect',help='读取原冻结版本，不能触发模型')
    inspect.add_argument('--release',required=True)
    monitoring=sub.add_parser('monitor',help='从原账本监控费用、完整交付、返工与独立升级裁定')
    monitoring.add_argument('--labels',type=Path);monitoring.add_argument('--labels-sha256')
    for command in (init,register,trial,stop,rollback,invalidate,history,inspect,monitoring):
        command.add_argument('--registry',required=True,type=Path)
    for command in (init,register,trial,stop,rollback,invalidate):command.add_argument('--actor',required=True)
    for command in (stop,rollback,invalidate):command.add_argument('--reason',required=True)
    args=parser.parse_args(argv)
    if args.operation=='freeze':
        result=frozen_release(read(args.config),read(args.versions),publication_id=args.name)
        write(args.output,result)
        report={'releaseSha256':result['releaseSha256'],'fileSha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),
            'nativeBudgetVerified':result['nativeBudgetVerified'],'qualified':False,'modelCalls':0}
    elif args.operation=='init':
        snapshot=read(args.snapshot,args.snapshot_sha256)
        # 先检查输出文件，不能因意外覆盖而留下一个看似没有初始化的新版本库。
        if args.gateway_config_output.exists():raise ValueError('网关配置输出已存在，禁止覆盖')
        store=ReleaseStore.create(args.registry,snapshot,actor=args.actor)
        config={'schemaVersion':CONFIG,'releaseRegistry':str(store.root)}
        auth=snapshot['configuration'].get('authTokenEnv')
        if auth:config['authTokenEnv']=auth
        write(args.gateway_config_output,config)
        report={'initialized':True,'baseline':snapshot['releaseSha256'],'modelCalls':0,'productDefaultChanged':False}
    else:
        store=ReleaseStore(args.registry)
        if args.operation=='register':
            report=store.add(read(args.snapshot,args.snapshot_sha256),read(args.evidence,args.evidence_sha256),actor=args.actor)
        elif args.operation=='trial':
            token=store.start_trial(args.release,max_tasks=args.max_tasks,expires=args.expires,
                actor=args.actor,explicit=args.explicit_trial)
            report={'trialId':token,'maxNewTasks':args.max_tasks,'modelCalls':0}
        elif args.operation=='stop':
            store.stop_trial(actor=args.actor,reason=args.reason);report={'stopped':True,'unknownUsageReleased':False}
        elif args.operation=='rollback':
            report={'baseline':store.rollback(actor=args.actor,reason=args.reason),
                'newTasksOnly':True,'oldAssignmentsChanged':False,'unknownUsageReleased':False}
        elif args.operation=='invalidate':
            store.invalidate(args.release,actor=args.actor,reason=args.reason)
            report={'qualification':'pending-revalidation','unknownUsageReleased':False}
        elif args.operation=='history':report=store.history()
        elif args.operation=='monitor':
            from .release_monitor import monitor
            if (args.labels is None)!=(args.labels_sha256 is None):raise ValueError('监控标签与原始摘要必须同时提供')
            report=monitor(store,read(args.labels,args.labels_sha256) if args.labels else None)
        else:report=store.snapshot(args.release)
    print(json.dumps(report,ensure_ascii=False,allow_nan=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
