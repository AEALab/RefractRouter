"""用已归档的真实失败响应离线复现，不发起网络或付费调用。"""
from pathlib import Path
import json
from unittest.mock import patch

import pytest

from refractrouter.openai_compatible import ChatResponse, OpenAICompatibleClient
from refractrouter.task_contract_replay import load_replay, run_replay
from refractrouter.task_contracts import decode_output
from tests.test_openai_compatible import SequenceTransport, success_response

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT/'data/benchmarks/dag-handoff-replay-v3.json'


def recorded_response():
    source=ROOT/'reports/dag-decomposition/issue-32-paid-20260907/run-01/calls'
    raw=json.loads(next(source.glob('*-response.json')).read_text())
    raw.pop('label')
    return ChatResponse(**raw)


def test_replay_preflight_preserves_original_task_and_complete_three_model_budget():
    with patch('socket.socket', side_effect=AssertionError('禁止网络')):
        raw, manifest, messages, contract, preflight = load_replay(PROTOCOL)
    original=json.loads((PROTOCOL.parent/raw['source_request_path']).read_text())
    assert messages[-1] == original['messages'][-1]
    assert messages[0] != original['messages'][0]
    assert preflight['maximum_calls'] == 3 and preflight['real_model_calls'] == 0
    assert preflight['max_production_cost'] == pytest.approx(20.8896)
    assert preflight['max_evaluation_cost'] == 0
    assert [m.model_id for m in manifest.candidates] == ['cheap','mid','strong']


def test_recorded_fence_is_still_rejected_and_failure_stops_after_one_call(tmp_path):
    loaded=load_replay(PROTOCOL)
    class Recorded:
        max_retries=0
        calls=0
        def complete(self, model, messages, *, json_mode=False):
            self.calls+=1
            assert json_mode
            return recorded_response()
    client=Recorded()
    with patch('socket.socket', side_effect=AssertionError('禁止网络')):
        result=run_replay(loaded,tmp_path/'replay',client=client,production_limit=20.8896)
    assert result['status']=='failed' and client.calls==1
    assert result['calls'][0]['status']=='billed'
    assert result['charged']['production']==pytest.approx(.0275)
    assert result['charged']['evaluation']==0 and result['evaluation'] is None
    assert result['nodes']==[]
    assert '```json' in result['calls'][0]['response_output']
    content=recorded_response().content
    with pytest.raises(ValueError,match='expected JSON object'):
        decode_output(content,loaded[3])
    # 只做取证诊断；运行时没有去围栏或修复后重判成功的路径。
    inner=content.removeprefix('```json\n').removesuffix('\n```')
    assert set(decode_output(inner,loaded[3]))=={'result','evidence','assumptions'}


def test_reconstructed_http_request_includes_json_object_hint_without_network():
    _, manifest, messages, contract, _=load_replay(PROTOCOL)
    transport=SequenceTransport([success_response(recorded_response().content)])
    client=OpenAICompatibleClient(transport=transport,environment={'CODEX_ARK_API_KEY':'测试凭证'},max_retries=0)
    with patch('socket.socket',side_effect=AssertionError('禁止网络')):
        response=client.complete(manifest.candidates[0],messages,json_mode=True)
    assert transport.calls[0]['payload']['response_format']=={'type':'json_object'}
    assert transport.calls[0]['url']=='https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions'
    with pytest.raises(ValueError):
        decode_output(response.content,contract)


def test_all_valid_replay_has_no_judge_or_semantic_success_claim(tmp_path):
    loaded=load_replay(PROTOCOL)
    class Valid:
        max_retries=0
        def complete(self, model, messages, *, json_mode=False):
            assert model.role=='candidate' and json_mode
            return ChatResponse(json.dumps({k:'模拟文本' for k in loaded[3]['output']['fields']}),100,100,0,0,10,1,'stop',None)
    result=run_replay(loaded,tmp_path/'pass',client=Valid(),production_limit=20.8896)
    assert result['status']=='contract-valid' and len(result['calls'])==3
    assert result['evaluation'] is None and result['charged']['evaluation']==0
    assert all(n['semantic_status']=='not-evaluated' for n in result['nodes'])
    with pytest.raises(FileExistsError):
        run_replay(loaded,tmp_path/'pass',client=Valid(),production_limit=20.8896)


@pytest.mark.parametrize('extra',[['--execute-paid-run'],['--max-production-cost','20.8896']])
def test_replay_cli_rejects_missing_authorization_before_client_creation(tmp_path,monkeypatch,extra):
    from experiments import replay_text_node_contract
    monkeypatch.setattr('sys.argv',['replay','--protocol',str(PROTOCOL),'--output-dir',str(tmp_path/'out'),*extra])
    with patch.object(replay_text_node_contract,'OpenAICompatibleClient',side_effect=AssertionError('不应创建真实客户端')):
        with pytest.raises(SystemExit) as error:
            replay_text_node_contract.main()
    assert error.value.code==2 and not (tmp_path/'out').exists()


def test_real_unescaped_quote_failure_remains_strictly_rejected():
    import hashlib
    root=ROOT/'reports/dag-decomposition/issue-32-subscription-20260907/study-v2'
    result=json.loads((root/'study-result.json').read_text())
    label=result['calls'][-1]['label']
    response=json.loads((root/'calls'/(hashlib.sha256(label.encode()).hexdigest()+'-response.json')).read_text())
    assert response['finish_reason']=='stop' and not response['content'].startswith('```')
    with pytest.raises(json.JSONDecodeError):
        json.loads(response['content'])
    with pytest.raises(ValueError,match='expected JSON object'):
        decode_output(response['content'],load_replay(PROTOCOL)[3])


def test_real_extra_metadata_failure_remains_rejected_without_releasing_child():
    loaded = load_replay(PROTOCOL)
    source = json.loads((PROTOCOL.parent / loaded[0]['source_result_path']).read_text())
    failed = next(node for node in source['nodes'] if node['node_id'] == 'risk')
    decoded = json.loads(failed['output'])
    assert set(decoded) == {'result', 'evidence', 'assumptions', 'covers'}
    assert decoded['covers'] == [1]
    with pytest.raises(ValueError, match='exact nonempty string fields'):
        decode_output(failed['output'], loaded[3])
    assert source['execution']['not_started'] == ['answer']
    assert all(call['status'] == 'billed' for call in source['calls'])
    assert source['final_output'] == '' and source['evaluation'] is None
    # 提示词消除「包含全部」可附加元数据的歧义；解析器仍然拒绝历史响应。
    assert '键集合必须恰好等于 contract.output.fields' in loaded[2][0]['content']
