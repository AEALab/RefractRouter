"""校验真人填写的复核包，不生成或替代人的判断。"""
import argparse
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
FIELDS={'reviewer','reviewed_at','decomposition_appropriate','original_delivery_covered',
    'dependencies_correct','parallelism_appropriate','handoff_risks','overall_passed','rationale'}
BOOLS={'decomposition_appropriate','original_delivery_covered','dependencies_correct','parallelism_appropriate','overall_passed'}


def validate(original,filled):
    if filled.get('reviewer_attestation')!='本人已阅读材料并独立填写，以下记录为真人复核。':
        raise ValueError('缺少真人复核声明；模型评审不能替代')
    originals={r['review_id']:r for r in original['rows']}
    if not originals or len(originals)!=len(original['rows']):
        raise ValueError('原始复核包为空或包含重复编号')
    rows=filled.get('rows',[])
    if len(rows)!=len(originals) or {r['review_id'] for r in rows}!=set(originals):
        raise ValueError('复核记录缺漏、重复或包含未知编号')
    for row in rows:
        baseline=originals[row['review_id']]
        if {k:v for k,v in row.items() if k not in FIELDS}!={k:v for k,v in baseline.items() if k not in FIELDS}:
            raise ValueError('原始复核材料被改动')
        if any(type(row.get(k)) is not bool for k in BOOLS):
            raise ValueError('判断字段必须填写 true 或 false')
        if any(not isinstance(row.get(k),str) or not row[k].strip() for k in FIELDS-BOOLS):
            raise ValueError('身份、日期、交接风险或理由未填写')
        if row['overall_passed'] and not all(row[k] for k in BOOLS-{'overall_passed'}):
            raise ValueError('总体判断与分项判断矛盾')
    return {'schema_version':'joint-human-review-v1','human_attested':True,'sample_count':len(rows),
        'passed':sum(r['overall_passed'] for r in rows),'reviewers':sorted({r['reviewer'] for r in rows}),
        'limits':'检查格式、覆盖和声明，不独立验证填写者身份；不改变模型成绩或收益判定。'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('filled',type=Path);args=parser.parse_args()
    raw=args.filled.read_bytes();original=(HERE/'human-review-packet.json').read_bytes()
    result=validate(json.loads(original),json.loads(raw))
    result.update(original_sha256=hashlib.sha256(original).hexdigest(),filled_sha256=hashlib.sha256(raw).hexdigest())
    out=HERE/'human-review-receipt.json'
    with out.open('x') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
