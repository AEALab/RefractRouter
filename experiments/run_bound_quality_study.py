"""#52 的真实路线绑定：默认零调用；演练与开发付费运行使用独立冻结文件。"""
from copy import deepcopy
import argparse
import json
from pathlib import Path

from refractrouter.dag_study_execution import write_json
from refractrouter.openai_compatible import ChatResponse
from refractrouter.quality_calibration import parse_review
from refractrouter.quality_runtime import ROOT, FINAL_SYSTEM, prepare, execute
from refractrouter.quality_study import digest, execution_payload, load_study


class RehearsalClient:
    """仅演练协议；参考输出作为模拟服务响应，不构成真实模型能力证据。"""
    max_retries = 0

    def __init__(self, study_dir):
        _, tasks, references, *_ = load_study(study_dir)
        self.answers = {digest(execution_payload(t)): references[t['task_id']]['author_reference'] for t in tasks}
        self.messages = []

    def complete(self, model, messages, *, json_mode=False):
        self.messages.append(deepcopy(messages))
        payload = json.loads(messages[-1]['content'])
        if model.role == 'judge':
            value = {'verdict': 'pass', 'rationale': '模拟逐项通过，不是真实评审',
                'criteria': [{'criterion': c, 'verdict': 'pass', 'rationale': '模拟依据'} for c in payload['criteria']]}
            parse_review(json.dumps(value), payload['criteria'])
        elif 'allow_dag' in payload:
            value = {'model': 'mid', 'mode': 'dag' if payload['allow_dag'] else 'direct', 'reason': '模拟选择'}
        elif 'max_nodes' in payload:
            count = min(3, len(payload['task']['materials']))
            nodes = [{'id': f'part{i}', 'type': 'extraction', 'job': f'分析第{i+1}部分并保留证据。',
                      'parents': [], 'difficulty': 'low', 'risk': 'low'} for i in range(count)] if count > 1 else []
            nodes.append({'id': 'answer', 'type': 'generation', 'job': '完整回答全部要求。',
                          'parents': [n['id'] for n in nodes], 'difficulty': 'medium', 'risk': 'medium'})
            value = {'reason': '模拟根据材料数量生成不同节点数，仅检验调度。', 'nodes': nodes}
        elif messages[0]['content'] == FINAL_SYSTEM:
            value = self.answers[digest(json.loads(payload['task']))]
        else:
            return ChatResponse('模拟中间分析及证据。', 100, 50, 0, 0, 1, 1, 'stop', None)
        return ChatResponse(json.dumps(value, ensure_ascii=False), 100, 50, 0, 0, 1, 1, 'stop', None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study-dir', type=Path, default=ROOT / 'data/quality-study-v1')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--task-ids', nargs='+')
    parser.add_argument('--arms', nargs='+')
    parser.add_argument('--repeats', type=int)
    parser.add_argument('--frozen', type=Path)
    parser.add_argument('--material-reviews', type=Path)
    parser.add_argument('--purpose-review', type=Path)
    parser.add_argument('--progress', action='store_true', help='逐任务立即输出开始事件，记录服务端发出时间')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--live', action='store_true')
    mode.add_argument('--rehearse', action='store_true')
    args = parser.parse_args(argv)
    if args.live or args.rehearse:
        if args.frozen is None or args.task_ids is not None or args.arms is not None or args.repeats is not None:
            parser.error('execution requires --frozen and cannot override its selection')
        frozen = json.loads(args.frozen.read_text())
        result = execute(args.study_dir, frozen, args.output_dir,
                         client=RehearsalClient(args.study_dir) if args.rehearse else None, simulated=args.rehearse,
                         material_reviews=json.loads(args.material_reviews.read_text()) if args.material_reviews else (),
                         purpose_review=json.loads(args.purpose_review.read_text()) if args.purpose_review else None,
                         on_progress=(lambda event: print(json.dumps(event, ensure_ascii=False), flush=True)) if args.progress else None)
        summary = {k: result[k] for k in ('status', 'simulated', 'actual_model_calls', 'actual_afp')}
        summary['runs'] = len(result['runs'])
    else:
        if args.frozen is not None:
            parser.error('--frozen requires an execution mode')
        frozen = prepare(args.study_dir, task_ids=args.task_ids, arms=args.arms,
                         repeats=args.repeats if args.repeats is not None else 3)
        args.output_dir.mkdir(parents=True, exist_ok=False)
        write_json(args.output_dir / 'frozen.json', frozen)
        summary = {k: frozen[k] for k in ('max_calls', 'online_afp_ceiling', 'offline_afp_ceiling', 'human_pending')}
        summary['actual_model_calls'] = 0
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
