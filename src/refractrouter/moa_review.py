"""本地 CLI 多模型共识（MoA）评审：初审两位、分歧升级两位，逐 criterion 投票。

调用 codex CLI 与 claude CLI 执行外部模型评审，不经过 Ark 账本；所有记录 origin=model，
不宣称真人签署。确定性检查仍在调用方先行，其 fail 不可被 MoA 覆盖。
"""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import time

from .quality_calibration import DELIVERY_CHECKS, SYSTEM, parse_review
from .quality_study import MATERIAL_CRITERIA, digest, execution_payload


MOA_POLICY = {
    'schema_version': 'moa-review-policy-v1',
    'primary': [
        {'reviewer_id': 'codex-gpt-5.6', 'cli': 'codex', 'model': 'gpt-5.6', 'thinking_effort': 'high'},
        {'reviewer_id': 'claude-opus', 'cli': 'claude', 'model': 'opus', 'thinking_effort': 'high'},
    ],
    'escalation': [
        {'reviewer_id': 'codex-gpt-astra', 'cli': 'codex', 'model': 'gpt-6-astra', 'thinking_effort': 'high'},
        {'reviewer_id': 'claude-fable', 'cli': 'claude', 'model': 'fable', 'thinking_effort': 'high'},
    ],
    'timeout_seconds': 240,
    'output_cap_tokens': 4096,
    'zero_retries': True,
    'voting_rule': '两位一致则采用；任一 criterion 不一致则升级两位重审；升级后一致则采用，否则 pending。',
    'origin': 'model',
    'reviewer_identity_verified': False,
    'scope': '跨 provider 多模型共识质量判定；不构成真人审查，也不证明真实用户接受度。',
}

PURPOSE_CRITERIA = ('研究用途与质量、非劣、样本量和失败标准相符',)

REVIEW_SCHEMA = {
    'type': 'object',
    'required': ['verdict', 'rationale', 'criteria'],
    'properties': {
        'verdict': {'enum': ['pass', 'fail', 'pending']},
        'rationale': {'type': 'string', 'minLength': 1},
        'criteria': {
            'type': 'array',
            'items': {
                'type': 'object',
                'required': ['criterion', 'verdict', 'rationale'],
                'properties': {
                    'criterion': {'type': 'string'},
                    'verdict': {'enum': ['pass', 'fail', 'pending']},
                    'rationale': {'type': 'string', 'minLength': 1},
                },
                'additionalProperties': False,
            },
        },
    },
    'additionalProperties': False,
}


def codex_command(reviewer, output_file, schema_file):
    """构造 codex CLI 非交互评审命令；prompt 由 stdin 传入，最后一条消息写入文件。"""
    return ['codex', 'exec', '--skip-git-repo-check', '--ephemeral', '--sandbox', 'read-only',
            '--model', reviewer['model'],
            '-c', f'model_reasoning_effort={reviewer["thinking_effort"]}',
            '--output-schema', str(schema_file),
            '--output-last-message', str(output_file), '-']


def claude_command(reviewer, schema_file):
    """构造 claude CLI 非交互评审命令；禁止工具、不询问权限，输出 JSON。"""
    return ['claude', '-p', '--model', reviewer['model'], '--effort', reviewer['thinking_effort'],
            '--output-format', 'json', '--json-schema', str(schema_file),
            '--tools', '', '--permission-mode', 'dontAsk', '--no-session-persistence', '-']


def default_invoke(reviewer, messages, schema=None):
    """真实 CLI 调用。返回 (exit_code, stdout, stderr, wall_time_ms, cli_version)。"""
    prompt = json.dumps(messages, ensure_ascii=False)
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='moa-review-') as directory:
            root = Path(directory)
            schema_file = root / 'review-schema.json'
            schema_file.write_text(json.dumps(schema or REVIEW_SCHEMA, ensure_ascii=False), encoding='utf-8')
            output_file = root / 'last-message.txt'
            command = (codex_command(reviewer, output_file, schema_file) if reviewer['cli'] == 'codex'
                       else claude_command(reviewer, schema_file))
            completed = subprocess.run(command, input=prompt, capture_output=True, text=True,
                                       timeout=MOA_POLICY['timeout_seconds'], check=False)
            stdout = completed.stdout
            if reviewer['cli'] == 'codex' and output_file.is_file():
                stdout = output_file.read_text(encoding='utf-8')
            return completed.returncode, stdout, completed.stderr, (time.monotonic() - started) * 1000, None
    except subprocess.TimeoutExpired as error:
        return 124, '', f'timeout: {error}', (time.monotonic() - started) * 1000, None


def _parse(content, criteria):
    try:
        return parse_review(content, criteria), None
    except (ValueError, TypeError) as error:
        return None, f'{type(error).__name__}: {error}'


def judge(reviewer, messages, criteria, invoke=default_invoke):
    """单次评审调用并归档证据。失败、超时或不合规输出记录 failed 并给 pending。"""
    exit_code, stdout, stderr, elapsed_ms, cli_version = invoke(reviewer, messages, REVIEW_SCHEMA)
    parsed, parse_error = _parse(stdout, criteria)
    record = {
        'reviewer_id': reviewer['reviewer_id'], 'cli': reviewer['cli'],
        'model': reviewer['model'], 'thinking_effort': reviewer['thinking_effort'],
        'origin': 'model', 'exit_code': exit_code, 'wall_time_ms': round(elapsed_ms, 3),
        'cli_version': cli_version, 'prompt_sha256': digest(messages),
        'response_sha256': digest(stdout) if stdout else None,
        'raw_response': stdout if stdout else None, 'stderr': stderr or None,
    }
    if exit_code != 0 or parse_error:
        record.update(status='failed', verdict='pending', error=parse_error or 'cli-exit-nonzero',
                      review=None)
    else:
        record.update(status='reviewed', verdict=parsed['verdict'], review=parsed)
    return record


def criterion_rows(records, criterion):
    """提取每个评审者在指定 criterion 上的判定；无效评审者不参与。"""
    result = {}
    for record in records:
        review = record.get('review')
        if not review:
            continue
        for row in review['criteria']:
            if row['criterion'] == criterion:
                result[record['reviewer_id']] = row['verdict']
    return result


def criterion_consensus(primary_records, escalation_records, criteria):
    """逐 criterion 聚合两位初审，分歧时使用两位升级；仍分歧为 pending。"""
    rows = []
    for criterion in criteria:
        primary = criterion_rows(primary_records, criterion)
        if len(primary) == 2 and len(set(primary.values())) == 1:
            verdict = next(iter(set(primary.values())))
            escalated = False
            escalation = {}
        elif len(primary) == 2 and len(set(primary.values())) > 1:
            escalated = True
            escalation = criterion_rows(escalation_records, criterion)
            if len(escalation) == 2 and len(set(escalation.values())) == 1:
                verdict = next(iter(set(escalation.values())))
            else:
                verdict = 'pending'
        else:
            # 初审存在无效输出时不升级：零重试，记 pending。
            escalated = False
            escalation = {}
            verdict = 'pending'
        rows.append({'criterion': criterion, 'verdict': verdict, 'primary': primary,
                     'escalated': escalated, 'escalation': escalation})
    return rows


def aggregate(primary_records, escalation_records, criteria):
    """返回 criterion 级共识、总体判定与分歧统计。"""
    rows = criterion_consensus(primary_records, escalation_records, criteria)
    verdicts = {row['verdict'] for row in rows}
    overall = 'fail' if 'fail' in verdicts else 'pending' if 'pending' in verdicts else 'pass'
    return {'criteria': rows, 'overall': overall,
            'escalated_criteria': sum(r['escalated'] for r in rows),
            'failed_records': sum(r['status'] != 'reviewed' for r in primary_records + escalation_records),
            'primary_disagreements': sum(len(set(r['primary'].values())) > 1 for r in rows)}


def run_review_target(messages, criteria, invoke=default_invoke):
    """同一评审目标：两位初审；存在分歧则两位升级重审；返回证据与共识。"""
    primary = [judge(reviewer, messages, criteria, invoke) for reviewer in MOA_POLICY['primary']]
    escalation = []
    rows = criterion_consensus(primary, [], criteria)
    if any(row['escalated'] for row in rows):
        escalation = [judge(reviewer, messages, criteria, invoke) for reviewer in MOA_POLICY['escalation']]
    consensus = aggregate(primary, escalation, criteria)
    return {'primary': primary, 'escalation': escalation, 'consensus': consensus,
            'policy_sha256': digest(MOA_POLICY)}


def material_messages(task, reference):
    payload = {'mode': '材料独立评审', 'task': deepcopy(task), 'reference': deepcopy(reference),
               'criteria': list(MATERIAL_CRITERIA),
               'scope': '逐项核对材料、参考事实与语义验收；证据不足保留 pending，不得编造验证。'}
    return [{'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]


def output_messages(task, output):
    criteria = list(DELIVERY_CHECKS) + task['semantic_criteria']
    payload = {'mode': '交付结果评审', 'task': execution_payload(task), 'candidate_output': output,
               'criteria': criteria}
    return [{'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}], criteria


def purpose_messages(policy_sha256, task_bindings):
    payload = {'mode': '研究用途确认', 'policy_sha256': policy_sha256,
               'task_bindings': task_bindings, 'criteria': list(PURPOSE_CRITERIA)}
    return [{'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]


def material_review(tasks, references, invoke=default_invoke):
    """对全部任务材料运行 MoA 评审；返回每任务记录与共识。"""
    results = []
    for task in tasks:
        messages = material_messages(task, references[task['task_id']])
        record = run_review_target(messages, list(MATERIAL_CRITERIA), invoke)
        record.update(task_id=task['task_id'], task_sha256=task['task_sha256'],
                      reference_sha256=digest(references[task['task_id']]))
        results.append(record)
    return results


def output_review(tasks, references, rows, invoke=default_invoke):
    """对交付输出运行 MoA 评审；绑定任务与输出哈希。"""
    by_id = {t['task_id']: t for t in tasks}
    results = []
    for row in rows:
        task = by_id[row['task_id']]
        messages, criteria = output_messages(task, row['output'])
        record = run_review_target(messages, criteria, invoke)
        record.update(task_id=task['task_id'], task_sha256=task['task_sha256'],
                      output_sha256=digest(row['output']), run_id=row['run_id'])
        results.append(record)
    return results


def purpose_review(policy_sha256, task_bindings, invoke=default_invoke):
    messages = purpose_messages(policy_sha256, task_bindings)
    record = run_review_target(messages, list(PURPOSE_CRITERIA), invoke)
    record.update(policy_sha256=policy_sha256, task_bindings=task_bindings)
    return record


def final_quality_status(deterministic_status, consensus_overall):
    """确定性 fail 一票否决；否则采用 MoA 共识。"""
    if deterministic_status == 'fail':
        return 'fail'
    return consensus_overall if consensus_overall in ('pass', 'fail', 'pending') else 'pending'


def preflight_envelope(kind, targets):
    """零调用的冻结包络：调用数、超时之和与策略哈希。"""
    calls = len(targets) * (len(MOA_POLICY['primary']) + len(MOA_POLICY['escalation']))
    return {'kind': kind, 'targets': len(targets), 'maximum_calls': calls,
            'timeout_sum_seconds': calls * MOA_POLICY['timeout_seconds'],
            'policy_sha256': digest(MOA_POLICY), 'real_model_calls': 0}

