"""官方 Jev 协议的无网络契约测试。"""

import io
import json
from urllib.error import HTTPError

import pytest

from refractrouter.jev_decision import JEV_ENDPOINT, JEV_MODEL, JevClient, JevDecisionAdapter
from refractrouter.planning_decision import LocalDecisionCapacityError


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self):
        return json.dumps(self.payload).encode()


def test_jev_post_pins_version_and_keeps_key_out_of_payload():
    calls = []

    def transport(request, timeout):
        calls.append((request, timeout))
        return Response({"model": JEV_MODEL, "answers": {"route": {
            "type": "choice", "choice": "EFFICIENT",
            "probabilities": {"EFFICIENT": 0.9, "CAPABLE": 0.1}, "confidence": 0.8}},
            "usage": {"input_tokens": 317, "output_tokens": 32}})

    client = JevClient("secret-for-test", transport=transport)
    questions = {"route": {"type": "choice", "instructions": "选择路线",
                            "criteria": {"EFFICIENT": "简单", "CAPABLE": "困难"}}}
    result = client.predict("一个任务", questions)
    assert result["usage"]["input_tokens"] == 317
    assert len(calls) == 1
    request, timeout = calls[0]
    assert request.full_url == JEV_ENDPOINT
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer secret-for-test"
    assert json.loads(request.data) == {"state": "一个任务", "model": JEV_MODEL,
                                        "questions": questions}
    assert b"secret-for-test" not in request.data
    assert timeout == 30


def test_jev_http_error_never_retries_or_leaks_response():
    calls = []

    def transport(request, timeout):
        calls.append(request)
        raise HTTPError(JEV_ENDPOINT, 429, "secret-for-test", {}, io.BytesIO(b"secret-for-test"))

    with pytest.raises(ValueError, match="HTTP 429.*不会自动重试") as raised:
        JevClient("secret-for-test", transport=transport).predict("state", {
            "question": {"type": "noul", "instructions": "ok?"}})
    assert len(calls) == 1
    assert "secret-for-test" not in str(raised.value)


@pytest.mark.parametrize("result", [
    {"model": "jev-other", "answers": {"q": {}}, "usage": {"input_tokens": 1, "output_tokens": 0}},
    {"model": JEV_MODEL, "answers": {}, "usage": {"input_tokens": 1, "output_tokens": 0}},
    {"model": JEV_MODEL, "answers": {"q": {}}, "usage": {"input_tokens": None, "output_tokens": 0}},
])
def test_jev_rejects_unconfirmed_model_answers_or_usage(result):
    client = JevClient("secret-for-test", transport=lambda *_args, **_kwargs: Response(result))
    with pytest.raises(ValueError):
        client.predict("state", {"q": {"type": "noul", "instructions": "ok?"}})


def test_jev_capacity_fails_before_network_call():
    called = []
    adapter = JevDecisionAdapter(api_key="secret-for-test",
        transport=lambda *_args, **_kwargs: called.append(True))
    with pytest.raises(LocalDecisionCapacityError):
        adapter._ensure_complete("x" * 99000,
            {"q": {"type": "noul", "instructions": "ok?"}})
    assert not called


def test_jev_accepts_complete_request_between_old_and_current_byte_limits():
    adapter = JevDecisionAdapter(api_key="secret-for-test",
        transport=lambda *_args, **_kwargs: None)
    adapter._ensure_complete("x" * 33000,
        {"q": {"type": "noul", "instructions": "ok?"}})
