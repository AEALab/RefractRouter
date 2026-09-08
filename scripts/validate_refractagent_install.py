"""Install both distributions in isolation and run all three native DSH models.

No provider credential is needed. Demo output is never reported as live acceptance.
This deliberately runs outside the checkout, using an installed wheel and tgz.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--packages-dir', type=Path, help='可选：在新目录保留本次验收的安装包')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('use a fresh output directory')
    if args.packages_dir is not None and args.packages_dir.exists():
        parser.error('use a fresh packages directory')
    output = args.output.resolve()
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix='refractagent-package-check-') as temporary:
        base = Path(temporary)
        workspace = base/'workspace'
        workspace.mkdir()
        env = os.environ.copy()
        for key in list(env):
            if key.endswith(('API_KEY','API_TOKEN')) or key in {'PYTHONPATH','PYTHONHOME','VIRTUAL_ENV'}:
                env.pop(key,None)
        env.update(DSH_HOME=str(base/'dsh'), UV_TOOL_DIR=str(base/'tools'),
                   UV_TOOL_BIN_DIR=str(base/'bin'), npm_config_cache=str(base/'npm-cache'))
        commands = []
        def run(command, cwd=workspace):
            result = subprocess.run([str(x) for x in command], cwd=cwd, env=env,
                text=True, capture_output=True, timeout=180)
            commands.append({'command':[str(x) for x in command], 'exit_code':result.returncode})
            if result.returncode:
                raise RuntimeError(f'{command[0]} failed: {result.stderr[-5000:]}\n{result.stdout[-1000:]}')
            return result.stdout
        run(['uv','build','--wheel','--out-dir',base/'packages'],ROOT)
        wheel = next((base/'packages').glob('*.whl'))
        packed = json.loads(run(['npm','pack',ROOT/'validation/dsh/plugin','--pack-destination',base/'packages','--json'],ROOT))
        tgz = base/'packages'/packed[0]['filename']
        run(['uv','tool','install',wheel])
        executable = base/'bin/refractagent'
        catalog = json.loads(run([executable,'models']))
        assert [m['id'] for m in catalog['models']] == ['economy','balanced','quality']
        run(['dsh','plugin','--profile','headless','add',tgz])
        runs = workspace/'runs'
        expected = {'economy':'deepseek-v4-flash','balanced':'minimax-m3','quality':'deepseek-v4-pro'}
        results = []
        for strategy, physical in expected.items():
            patch = workspace/f'{strategy}.json'
            run([executable,'dsh-config','--output',patch,'--runs-dir',runs,'--mode','demo','--strategy',strategy])
            composed = run(['dsh','--profile','headless','--patch',patch,'--dump-config'])
            assert 'name: dsh-refractrouter-validation/agent' in composed
            assert 'provider: refractagent' in composed
            task = '请用两句话比较小规模试点和全面推广。'
            answer = run(['dsh','--profile','headless','--patch',patch,task])
            assert '[SIMULATED]' in answer
            candidates = [json.loads(p.read_text()) for p in runs.glob('*/summary.json')]
            summary = next(r for r in candidates if r['strategy']==strategy)
            assert summary['status']=='simulated' and summary['simulated']
            assert summary['models']=={'answer':physical}
            request = json.loads((Path(summary['run_dir'])/'request.json').read_text())
            assert request['mode']=='demo'
            assert request['payload']['task']==task
            assert task in summary['answer']
            assert 'You are an AI agent' in request['payload']['context']
            # Preserve compact acceptance results, not temporary input/system-prompt dumps.
            results.append({k:summary[k] for k in ('strategy','models','status','simulated','costs')})
        evidence = {'status':'pass','scope':'installed-wheel-and-tgz-native-dsh-demo',
            'paid_model_calls':0,'live_acceptance':False,'catalog':catalog,'results':results,
            'versions':{'dsh':run(['dsh','--version']).strip(),'node':run(['node','--version']).strip()},
            'artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (wheel,tgz)},
            'commands':commands}
        (output/'acceptance.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        if args.packages_dir is not None:
            args.packages_dir.mkdir(parents=True)
            for package in (wheel,tgz):
                shutil.copy2(package,args.packages_dir/package.name)
        print(json.dumps({'status':'pass','strategies':list(expected),'paid_model_calls':0,'evidence':str(output/'acceptance.json')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
