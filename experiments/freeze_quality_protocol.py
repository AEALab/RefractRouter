"""汇总 #52 非真人条件及可复现证据；真人栏必须由真实参与者填写。"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from refractrouter.dag_study_execution import write_json
from refractrouter.quality_calibration import _messages
from refractrouter.quality_material_audit import audit
from refractrouter.quality_runtime import ARMS, ROOT, prepare
from refractrouter.quality_statistics import POLICY
from refractrouter.quality_study import digest, file_digest, load_study, material_review_packet
from refractrouter.openai_compatible import ChatResponse, model_response_cost


def calibration_coverage(study_dir):
    _, tasks, _, controls, *_ = load_study(study_dir)
    by_id = {t['task_id']: t for t in tasks}; archive = {}
    for batch in ('model-calibration-01', 'model-calibration-02'):
        path = ROOT / 'reports/quality-study-v1' / batch
        # 所有归档必须先通过索引，不把手写结果表当作真实调用证据。
        for name, sha in json.loads((path / 'artifact-index.json').read_text()).items():
            if file_digest(path / name) != sha:
                raise ValueError('calibration evidence changed')
        frozen = json.loads((path / 'frozen-plan.json').read_text())
        session = json.loads((path / 'session.json').read_text())
        records = {r['label']: r for r in session['records']}
        results = {r['request_id']: r for r in session['results']}
        for request in frozen['requests']:
            record = records[request['request_id']]
            result = results[request['request_id']]
            if request['kind'] == 'calibration' and record['status'] == 'billed' and 'review' in result:
                archive[digest(request['messages'])] = {'batch': batch, 'request_id': request['request_id'],
                                                      'verdict': result['review']['verdict']}
    rows = []
    for case in controls:
        messages, _ = _messages(by_id[case['task_id']], output=case['output'])
        evidence = archive.get(digest(messages))
        rows.append({'case_id': case['case_id'], 'author_label': case['author_semantic_label'],
                     'current_messages_sha256': digest(messages), 'evidence': evidence,
                     'matches_author_label': bool(evidence and evidence['verdict'] ==
                                                 ('pass' if case['author_semantic_label'] == 'acceptable' else 'fail'))})
    return {'controls': rows, 'covered': sum(r['evidence'] is not None for r in rows),
            'count': len(rows), 'human_disagreement': None,
            'scope': '按当前消息精确匹配历史真实开发调用；含看过结果后的开发修订，不是新的独立测试集。'}


def ledger_audit(result_path, manifest):
    result = json.loads(result_path.read_text())
    root = result_path.parent
    for index in ('artifact-index.json', 'evaluation-index.json'):
        for name, sha in json.loads((root / index).read_text()).items():
            if file_digest(root / name) != sha:
                raise ValueError('runtime evidence changed')
    models = {m.model_id: m for m in manifest.models}
    charged = {'production': 0.0, 'evaluation': 0.0}; labels = set()
    for call in result['calls']:
        if call['label'] in labels:
            raise ValueError('duplicate bill')
        labels.add(call['label'])
        if call['status'] == 'cancelled-before-dispatch':
            if call['charged'] != 0: raise ValueError('cancelled request billed')
            continue
        if call['status'] != 'billed': raise ValueError('usage unresolved')
        raw = json.loads((root / 'calls' / (hashlib.sha256(call['label'].encode()).hexdigest() + '.json')).read_text())
        if {k: v for k, v in raw.items() if k != 'label'} != call['response']:
            raise ValueError('response record changed')
        response = ChatResponse(**call['response'])
        amount = model_response_cost(models[call['model_id']], response)
        if abs(amount - call['charged']) > 1e-8 or response.attempts != 1:
            raise ValueError('charge or retry mismatch')
        if call['input_sha256'] != hashlib.sha256(json.dumps(call['request_messages'], ensure_ascii=False).encode()).hexdigest():
            raise ValueError('request hash changed')
        charged[call['category']] += amount
    if any(abs(charged[k] - result['charged_or_reserved'][k]) > 1e-8 for k in charged):
        raise ValueError('ledger totals do not reconcile')
    return {'calls': len(labels), 'recomputed_afp': charged, 'status': 'verified',
            'simulated': result['simulated']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-dir', type=Path, default=ROOT / 'data/quality-study-v1')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--rehearsal-results', type=Path, required=True)
    parser.add_argument('--live-results', type=Path, required=True)
    args = parser.parse_args(argv)
    _, tasks, refs, _, _, manifest = load_study(args.study_dir)
    selected = [t['task_id'] for t in tasks if t['split'] == 'holdout-candidate']
    frozen = prepare(args.study_dir, task_ids=selected)
    calculation = audit(args.study_dir); coverage = calibration_coverage(args.study_dir)
    rehearsal = json.loads(args.rehearsal_results.read_text())
    live = json.loads(args.live_results.read_text())
    ledger_checks = {'rehearsal': ledger_audit(args.rehearsal_results, manifest),
                     'live': ledger_audit(args.live_results, manifest)}
    if not rehearsal['simulated'] or live['simulated']:
        raise ValueError('rehearsal and real evidence must stay distinct')
    if set(r['arm'] for r in rehearsal['runs']) != set(ARMS):
        raise ValueError('not all bound arms rehearsed')
    live_known = (live['actual_model_calls'] > 0 and live['actual_afp'] is not None
                  and all(c['status'] in ('billed', 'cancelled-before-dispatch') for c in live['calls']))
    def matches_implementation(result_path):
        evidence_frozen = json.loads((result_path.parent / 'frozen.json').read_text())
        return (evidence_frozen['implementation'] == frozen['implementation']
                and digest(evidence_frozen) == json.loads(result_path.read_text())['frozen_sha256'])
    checks = {'material_reference_recalculation': calculation['reference_mismatches'] == 0,
        'current_development_controls_have_real_judge_evidence': coverage['covered'] == coverage['count'],
        'statistics_and_operating_thresholds_frozen': frozen['statistics_policy'] == POLICY,
        'all_routes_bound_and_rehearsed': all(r['status'] == 'delivered-unconfirmed' for r in rehearsal['runs']),
        'real_runner_usage_reconciled': live_known,
        'rehearsal_implementation_matches': matches_implementation(args.rehearsal_results),
        'real_implementation_matches': matches_implementation(args.live_results),
        'offline_setup_bounded': frozen['offline_setup']['training_calls'] == 0 and len(frozen['setups']) == len(selected),
        'heldout_outputs_not_used_for_tuning': all(r['task_id'] not in selected for r in live['runs'])}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    write_json(args.output_dir / 'frozen.json', frozen)
    write_json(args.output_dir / 'material-audit.json', calculation)
    write_json(args.output_dir / 'calibration-coverage.json', coverage)
    write_json(args.output_dir / 'ledger-audit.json', ledger_checks)
    write_json(args.output_dir / 'human-material-packet.json', material_review_packet(tasks, refs))
    write_json(args.output_dir / 'human-purpose-template.json', {'origin': 'human', 'reviewer': None, 'evidence': None,
               'policy_sha256': digest(POLICY), 'task_bindings': frozen['task_bindings'], 'verdict': 'pending'})
    summary = {'schema_version': 'quality-technical-readiness-v1', 'technical_checks': checks,
               'nonhuman_requirements_complete': all(checks.values()),
               'human_requirements': frozen['human_pending'], 'human_requirements_complete': False,
               'formal_run_ready': False, 'research_scope': '固定构造微任务的控制性探索；无业务总体代表性主张。',
               'evidence': {str(p.relative_to(ROOT)): file_digest(p) for p in (args.rehearsal_results.resolve(), args.live_results.resolve())}}
    write_json(args.output_dir / 'readiness.json', summary)
    write_json(args.output_dir / 'artifact-index.json', {p.name: file_digest(p) for p in sorted(args.output_dir.iterdir())})
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
