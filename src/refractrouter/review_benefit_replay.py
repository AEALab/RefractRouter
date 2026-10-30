"""只以固定回执重放真实核心，保存审计轨迹；没有真实模型执行模式。"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

from .planning_config import compile_config
from .planning_runtime import PlanningRuntime
from .review_benefit import compare
from .task_outcomes import digest
from .task_results import event


def execute_fixture(root, config, *, strategy, script, task, case_id, criteria):
    """所有返回值都是构造夹具；独立标签只在执行脚本结束后追加，不参与选模。"""
    runtime = PlanningRuntime(root)
    run_id = None
    expected = {}
    try:
        started = runtime.handle({'op': 'begin', 'config': deepcopy(config), 'strategy': strategy,
            'identity': {'session': case_id, 'agent': 'fixture-' + strategy, 'turn': 1}})
        run_id = started['runId']
        messages = [
            {'role': 'system', 'content': '遵守只读工具权限；不声称执行未运行的动作。'},
            {'role': 'user', 'content': task}]
        tools = [{'name': 'read', 'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}}}}]
        action = runtime.handle({'op': 'step', 'runId': run_id, 'messages': messages, 'tools': tools})
        for row in script:
            if row.get('newStep'):
                if action.get('action') != 'release':
                    raise ValueError('未释放候选不能伪造宿主工具续接')
                raw_candidate = next(c['response'] for c in action['record']['calls']
                                     if c.get('call_id') == action['callId'])
                blocks = [{'type': 'text', 'text': raw_candidate['content']}] if raw_candidate['content'] else []
                blocks.extend({'type': 'tool-call', **t} for t in raw_candidate.get('tool_calls', []))
                messages.append({'role': 'assistant', 'content': blocks})
                messages.append({'role': 'user', 'content': [
                    {'type': 'tool-result', 'toolCallId': t['id'], 'isError': False,
                     'content': [{'type': 'text', 'text': '构造工具结果；没有执行真实工具。'}]}
                    for t in raw_candidate.get('tool_calls', [])] or '继续完成同一任务。'})
                action = runtime.handle({'op': 'step', 'runId': run_id, 'messages': messages, 'tools': tools})
            if (set(row) - {'purpose', 'content', 'gold', 'toolCalls', 'expectedError', 'newStep'}
                    or action.get('action') != 'call' or action['purpose'] != row['purpose']):
                raise ValueError('固定脚本与实际核心派发不一致')
            call_id = action['callId']
            if row['purpose'] in {'execute', 'redo', 'takeover'}:
                if row.get('gold') not in {'PASS', 'FAIL', 'UNKNOWN'}:
                    raise ValueError('固定候选必须有构造标签')
                expected[call_id] = row['gold']
            elif row.get('gold') is not None:
                raise ValueError('模型判词不能作为独立金标')
            try:
                action = runtime.handle({'op': 'complete', 'runId': run_id, 'callId': call_id,
                    'response': {'content': row['content'], 'toolCalls': row.get('toolCalls', []),
                        'finishReason': 'tool_calls' if row.get('toolCalls') else 'stop',
                        'usageAvailable': True, 'inputTokens': 100, 'outputTokens': 20,
                        'cachedInputTokens': 0, 'cacheUsageSource': 'fixture-reported-zero',
                        'rawUsage': {'cacheWriteTokens': 0}, 'latencyMs': 10}})
            except ValueError as exc:
                if not row.get('expectedError') or row['expectedError'] not in str(exc):
                    raise
                action = {'action': 'stop'}
            else:
                if row.get('expectedError'):
                    raise ValueError('固定失败没有实际发生')
        if action.get('action') not in {'release', 'stop'}:
            raise ValueError('脚本结束时仍有未结算流程')
        if runtime.runs[run_id]['status'] == 'running':
            runtime.handle({'op': 'end', 'runId': run_id})
        identity = runtime.runs[run_id]['identity']
        request = {'op': 'outcome', 'runId': run_id, 'identity': identity}
        result = runtime.handle(request)
        labels = []
        for candidate in result['candidates']:
            token = candidate['candidateId']
            call = next(r for r in result['calls'] if r.get('call_id') == token)
            gold = expected[token]
            label = {'candidateId': token, 'candidateSha256': candidate['candidateSha256'],
                'criteriaSha256': criteria, 'scope': ('candidate-next-action' if call['finish_reason'] == 'tool_calls'
                    else 'complete-delivery-and-requirements'), 'independent': True, 'verdict': gold,
                'method': 'pending' if gold == 'UNKNOWN' else 'explicit-acceptance',
                'recordSha256': digest({'kind': 'constructed-contract', 'caseId': case_id,
                                       'scriptSha256': digest(script), 'candidateId': token, 'gold': gold})}
            labels.append(label)
            runtime.task_results.journal.append(digest({k: identity[k] for k in ('session', 'agent')}), run_id,
                event('fixture-evaluation-' + token, 'feedback', candidate=(token, candidate['candidateSha256']),
                    source='hidden-evaluation', actor='constructed-contract-oracle',
                    status={'PASS': 'accepted', 'FAIL': 'rejected', 'UNKNOWN': 'unknown'}[gold],
                    artifacts=[digest(label)], criteria=criteria))
        return runtime.handle(request), labels
    finally:
        runtime.local_service.close()


def run(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    root = Path(__file__).resolve().parents[2]
    if (not (root / 'pyproject.toml').is_file()
            or not Path(__file__).resolve().is_relative_to(root / 'src/refractrouter')):
        raise ValueError('研究重放须使用匹配的源码环境')
    if output == source.parent or source.parent in output.parents or root in output.parents or output == root:
        raise ValueError('输出须与来源及源码分开')
    raw = source.read_bytes()
    study = json.loads(raw)
    if (type(study) is not dict or set(study) != {'schemaVersion', 'kind', 'criteriaSha256', 'configuration', 'cases'}
            or study['schemaVersion'] != 'review-benefit-fixtures-v1' or study['kind'] != 'constructed-contract'
            or type(study['cases']) is not list or not study['cases']):
        raise ValueError('仅接受固定构造回执，不接受真实模型执行参数')
    cfg = study['configuration']
    compiled = compile_config(cfg)
    if (any(m.provider != 'fixture' or m.deployment != 'local' for m in compiled['models'].values())
            or any(compiled[key]['judge']['type'] != 'llm' for key in ('advisor', 'escalation'))):
        raise ValueError('重放只允许本地固定模型身份，不加载判别模型或外部服务')
    ids = [r['caseId'] for r in study['cases']]
    if len(set(ids)) != len(ids) or any(not isinstance(i, str) or not i.replace('-', '').isalnum() for i in ids):
        raise ValueError('重放案例身份无效或重复')
    paths = sorted((root / 'src/refractrouter').glob('*.py')) + [source, root / 'experiments/replay_review_benefit.py']
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    clean = not subprocess.run(['git', 'status', '--porcelain'], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    output.mkdir(parents=True, exist_ok=False)
    def save(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    save(output / 'source-before.json', before)
    pairs = []
    for case in study['cases']:
        folder = output / case['caseId']
        folder.mkdir()
        common = dict(task=case['task'], case_id=case['caseId'], criteria=study['criteriaSha256'])
        baseline, left = execute_fixture(folder / 'baseline-core', cfg,
            strategy='static', script=case['baseline'], **common)
        reviewed, right = execute_fixture(folder / 'reviewed-core', cfg,
            strategy=case['strategy'], script=case['reviewed'], **common)
        save(folder / 'baseline.json', baseline); save(folder / 'reviewed.json', reviewed)
        save(folder / 'annotations.json', {'baseline': left, 'reviewed': right})
        pair = compare(baseline, reviewed, baseline_annotations=left, reviewed_annotations=right,
                       criteria_sha256=study['criteriaSha256'])
        save(folder / 'audit.json', pair)
        pairs.append({'caseId': case['caseId'], 'strategy': case['strategy'],
            'baselineQuality': pair['baseline']['quality'], 'reviewedQuality': pair['reviewed']['quality'],
            'falseAllowed': pair['reviewed']['falseAllowed'],
            'unnecessaryInterventions': pair['reviewed']['unnecessaryInterventions'],
            'repairedKnownFailure': pair['reviewed']['repairedKnownFailure'], 'costs': pair['costs']})
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    save(output / 'source-after.json', after)
    if after != before or source.read_bytes() != raw:
        raise ValueError('重放期间来源或源码改变')
    revision_after = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    if revision_after != revision:
        raise ValueError('重放期间Git版本改变')
    summary = {'schemaVersion': 'review-benefit-replay-v1', 'kind': 'constructed-contract',
        'sourceRevision': revision, 'sourceSha256': hashlib.sha256(raw).hexdigest(), 'sourceUnchanged': True,
        'sourceTreeWasClean': clean,
        'cases': pairs, 'fixtureTaskPairs': len(pairs), 'empiricalIndependentTasks': 0,
        'actualModelBenefitProven': False, 'productionRoutingChanged': False, 'paidModelCalls': 0,
        'fixturePricesAreActualSpend': False, 'hostToolsExecuted': 0,
        'latencySource': 'fixed-fixture-and-local-replay-wall-clock', 'realModelTimingObserved': False,
        'releaseDecision': 'keep-review-changes-experimental-pending-independent-evaluation'}
    save(output / 'summary.json', summary)
    return summary
