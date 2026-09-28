"""客户端适配器仅在可核对的宿主结果上产生失败证据。"""
from refractrouter.client_tool_evidence import from_codex_hook, from_hermes_hook
from refractrouter.client_tool_evidence import EVIDENCE_VERSION as CLIENT_EVIDENCE_VERSION
from refractrouter.host_evidence import EVIDENCE_VERSION
from validation.codex.evidence_events import CodexEvidenceEvents


def hook(call_id, command='false', output=''):
    return {'hook_event_name':'PostToolUse', 'tool_name':'Bash',
            'tool_use_id':call_id, 'tool_input':{'command':command},
            'tool_response':output}


def completed(command='false', output='', code=1):
    return {'type':'item.completed', 'item':{'type':'command_execution',
        'command':"/bin/zsh -lc '" + command + "'", 'aggregated_output':output,
        'exit_code':code, 'status':'completed'}}


def test_codex_pairs_call_id_and_structured_cli_exit():
    assert CLIENT_EVIDENCE_VERSION == EVIDENCE_VERSION
    evidence = CodexEvidenceEvents()
    evidence.observe_hook(hook('a'))
    evidence.observe_json_event(completed())
    facts = evidence.facts_for(['a'], timeout=0)
    assert len(facts) == 1 and facts[0]['status'] == 'failed'
    assert evidence.facts_for(['a'], timeout=0) == facts
    assert from_codex_hook(hook('a')) is None


def test_codex_rejects_ambiguous_or_mismatched_events():
    evidence = CodexEvidenceEvents()
    evidence.observe_hook(hook('a'))
    evidence.observe_hook(hook('b'))
    evidence.observe_json_event(completed())
    assert evidence.facts_for(['a', 'b'], timeout=0) == []
    other = CodexEvidenceEvents()
    other.observe_hook(hook('a', 'printf DIFFERENT', ''))
    other.observe_json_event(completed())
    assert other.facts_for(['a'], timeout=0) == []


def test_hermes_only_uses_terminal_json_envelope():
    event = {'tool_name':'terminal', 'tool_call_id':'c',
             'args':{'command':'false'},
             'result':'{"output":"failure","exit_code":1,"error":null}'}
    assert from_hermes_hook(event)['status'] == 'failed'
    assert from_hermes_hook({**event, 'result':'failure'}) is None
    assert from_hermes_hook({**event, 'result':
        '{"output":"","exit_code":-1,"error":"blocked","status":"blocked"}'})['status'] == 'denied'
    assert from_hermes_hook({**event, 'result':
        '{"output":"","exit_code":null,"error":null,"status":"yielded_to_background"}'})['status'] == 'unconfirmed'
