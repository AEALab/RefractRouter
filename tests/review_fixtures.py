"""其他功能测试的合成审核回执；不用于证明真实模型的语义判断质量。"""


def mock_grounding_checks(payload):
    if 'evidence_catalog' in payload:
        claims = payload['evidence_catalog']['claim_refs']
        return [({'check_id': key, 'status': 'PASS', 'answer_ref': claims[key],
                  'source_refs': [], 'claim_kind': 'CONDITIONAL', 'rationale': '合成判定；不证明语义质量。'}
                 if key in claims else {'check_id': key, 'status': 'NOT_APPLICABLE', 'answer_ref': None,
                                        'source_refs': [], 'rationale': '合成不适用判定。'})
                for key in payload['grounding_check_ids']]
    claims = {row['check_id']:row['quote'] for row in payload.get('source_state_claims', [])}
    return [({'check_id': key, 'status': 'PASS', 'answer_quote': claims[key],
             'source_quote': None, 'claim_kind':'CONDITIONAL',
             'rationale':'合成调用回执；不证明真实断言为条件或准确。'} if key in claims else
            {'check_id': key, 'status': 'NOT_APPLICABLE', 'answer_quote': None,
             'source_quote': None, 'rationale': '此处是合成模型回执；来源语义在专项案例中验证。'}
            ) for key in payload.get('grounding_check_ids', [])]
