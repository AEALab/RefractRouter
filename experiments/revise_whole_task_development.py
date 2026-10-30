"""只允许一次有依据的开发提示修订；保留原答卷、评分与未知预留。"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil


def sha(raw): return hashlib.sha256(raw).hexdigest()


def wire(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode() + b'\n'


def revise(source, run, output):
    source, run, output = map(Path, (source, run, output))
    manifest_raw = (source/'manifest.json').read_bytes(); manifest = json.loads(manifest_raw)
    ledger_raw = (run/'ledger.json').read_bytes(); ledger = json.loads(ledger_raw)
    generation_raw = (run/'generation-summary.json').read_bytes(); generation = json.loads(generation_raw)
    if (manifest.get('developmentRevision', 0) != 0 or generation['manifestSha256'] != sha(manifest_raw)
            or ledger['manifestSha256'] != sha(manifest_raw) or generation['stopReason'] != 'unknown-usage'
            or any(r['status'] == 'reserved' for r in ledger['calls'])):
        raise ValueError('只接受已停止且无在途的新旧批次，不允许第二次开发修订')
    if not any(r.get('candidate', '').startswith('```json') for r in ledger['results'] if r.get('candidate')):
        raise ValueError('必须保留明确的格式违约原文作为修订依据')
    if output.exists(): raise ValueError('必须使用全新版本目录')
    previous_raw = Path(manifest['funding']['sourcePath']).read_bytes()
    if sha(previous_raw) != manifest['funding']['sourceSha256']:
        raise ValueError('前序财务承接身份不符')
    prior = json.loads(previous_raw)
    known = sum(Decimal(str(c['charged'])) for c in ledger['calls'] if c['status'] == 'billed')
    unknown = sum(Decimal(str(c['charged'])) for c in ledger['calls'] if c['status'] == 'unknown-usage')
    if abs(known+unknown-Decimal(str(ledger['chargedStandardAFPIncludingUnknownReserves']))) > Decimal('1e-8'):
        raise ValueError('本批关闭账本不平')
    financial = {k: prior[k] for k in ('cash_limit_cny', 'cumulative_cash_protected_cny',
        'historical_unknown_cash_retained_cny', 'plan_no_overage_is_user_declared')}
    financial.update(time_utc=datetime.now(timezone.utc).isoformat(),
        cumulative_known_standard_afp=str(Decimal(prior['cumulative_known_standard_afp_lower'])+known),
        cumulative_unknown_reserved_standard_afp=str(Decimal(prior['cumulative_unknown_reserved_standard_afp'])+unknown),
        conditional_cash_headroom_cny=str(Decimal(prior['cash_limit_cny'])-Decimal(prior['cumulative_cash_protected_cny'])),
        batch_closed_no_inflight=True, outstanding_unknown_preserved=True,
        all_current_calls_settled=False, unknown_reserves_released=False,
        actual_account_debit_verified=False, new_cash_conditional_cny='0',
        previous_source_sha256=sha(previous_raw), closed_ledger_sha256=sha(ledger_raw),
        closed_generation_sha256=sha(generation_raw), new_known_standard_afp=str(known),
        new_unknown_reserved_standard_afp=str(unknown))
    financial['cumulative_known_standard_afp_lower'] = financial.pop('cumulative_known_standard_afp')
    output.mkdir(parents=True)
    finance_path = output/'financial-before.json'; finance_path.write_bytes(wire(financial))
    for task in manifest['tasks']:
        shutil.copytree(source/task['root'], output/task['root'])
        host = json.loads((source/task['host']).read_bytes())
        host['root'] = str((output/task['root']).resolve())
        (output/task['host']).write_bytes(wire(host))
        task['hostSha256'] = sha((output/task['host']).read_bytes())
        task['criteria']['contract'] += (' 输出必须直接为 JSON 对象，禁止 Markdown 代码块、'
            '禁止 ``` 或 ```json 包装，禁止对象前后的说明文字。只输出从 { 到 } 的 JSON。')
        task['criteriaSha256'] = sha(json.dumps(task['criteria'], ensure_ascii=False, sort_keys=True).encode())
    oracles = json.loads((source/'isolated-evaluation/oracles.json').read_bytes())
    original = deepcopy(oracles)
    for task in manifest['tasks']:
        oracles[task['taskId']]['oracle']['criteriaSha256'] = task['criteriaSha256']
    for key in oracles:
        a, b = deepcopy(oracles[key]), deepcopy(original[key])
        del a['oracle']['criteriaSha256']; del b['oracle']['criteriaSha256']
        if a != b: raise ValueError('禁止借提示修订修改评分答案、证据或补丁要求')
    (output/'isolated-evaluation').mkdir()
    (output/'isolated-evaluation/oracles.json').write_bytes(wire(oracles))
    shutil.copyfile(source/'source-provenance.json', output/'source-provenance.json')
    manifest['developmentRevision'] = 1
    manifest['revision'] = {'previousManifestSha256': sha(manifest_raw),
        'previousLedgerSha256': sha(ledger_raw), 'reason': '多份原始答卷使用Markdown代码块，明确违约；仅统一强调直接JSON。',
        'scoringSemanticsChanged': False, 'previousResultsRegraded': False, 'newIndependentTasks': 0,
        'networkCause': f'前批第{len(ledger["calls"])}次请求传输失败，未取得响应，具体底层原因未知；HEAD只证明当前连通。'}
    manifest['funding'].update(sourcePath=str(finance_path.resolve()), sourceSha256=sha(finance_path.read_bytes()),
        priorKnownStandardAFP=financial['cumulative_known_standard_afp_lower'],
        priorUnknownStandardAFP=financial['cumulative_unknown_reserved_standard_afp'],
        sourceTimeUTC=financial['time_utc'], laterResearchCallsBeforeThisBatch=len(ledger['calls']))
    (output/'manifest.json').write_bytes(wire(manifest))
    return {'manifestSha256': sha((output/'manifest.json').read_bytes()),
        'oracleSha256': sha((output/'isolated-evaluation/oracles.json').read_bytes()), 'modelCalls': 0,
        'preservedUnknownStandardAFP': str(unknown), 'developmentRevision': 1}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True); parser.add_argument('--run', required=True)
    parser.add_argument('--output', required=True); args = parser.parse_args()
    print(json.dumps(revise(args.source, args.run, args.output), ensure_ascii=False))
