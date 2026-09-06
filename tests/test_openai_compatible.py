from __future__ import annotations

import json
import io
import tempfile
import unittest
from pathlib import Path

from refractrouter.adapters import OpenAICompatibleAdapter
from refractrouter.openai_compatible import (
    DshStdioBridge,
    ModelInvocationError,
    OpenAICompatibleClient,
    TransportResponse,
    model_response_cost,
)
from refractrouter.schemas import ModelSpec
from tests.helpers import make_task


class SequenceTransport:
    def __init__(self, responses: list[TransportResponse]):
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def post(self, url, headers, body, timeout_seconds):
        self.calls.append(
            {
                "url": url,
                "authorization": headers["Authorization"],
                "payload": json.loads(body),
                "timeout": timeout_seconds,
            }
        )
        return self.responses.pop(0)


def real_model() -> ModelSpec:
    return ModelSpec(
        model_id="cheap",
        provider="test-provider",
        input_cost_per_1k=0.002,
        cached_input_cost_per_1k=0.0002,
        output_cost_per_1k=0.008,
        capability=0.7,
        api_model="test-model-2026-01-01",
        base_url="https://example.invalid/v1",
        api_key_env="TEST_API_KEY",
        max_output_tokens=4096,
    )


def success_response(
    content: str = '{"requirements":"ok","sections":["a"],"constraints":[],"analysis":"ok"}',
) -> TransportResponse:
    body = {
        "id": "chatcmpl-test",
        "choices": [
            {"message": {"content": content}, "finish_reason": "stop", "index": 0}
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 25,
            "prompt_tokens_details": {"cached_tokens": 40},
            "completion_tokens_details": {"reasoning_tokens": 5},
        },
    }
    return TransportResponse(200, {"X-Request-ID": "req-test"}, json.dumps(body).encode())


class OpenAICompatibleClientTests(unittest.TestCase):
    def test_parses_usage_retries_and_computes_cached_cost(self) -> None:
        transport = SequenceTransport(
            [
                TransportResponse(429, {}, b'{"error":{"message":"retry later"}}'),
                success_response(),
            ]
        )
        sleeps: list[float] = []
        client = OpenAICompatibleClient(
            transport=transport,
            environment={"TEST_API_KEY": "secret"},
            max_retries=2,
            sleep=sleeps.append,
        )

        response = client.complete(
            real_model(),
            [{"role": "user", "content": "test"}],
            json_mode=True,
        )

        self.assertEqual(response.attempts, 2)
        self.assertEqual(response.cached_input_tokens, 40)
        self.assertEqual(response.reasoning_tokens, 5)
        self.assertEqual(response.request_id, "req-test")
        self.assertEqual(sleeps, [1])
        self.assertEqual(model_response_cost(real_model(), response), 0.000328)
        self.assertEqual(transport.calls[0]["authorization"], "Bearer secret")
        self.assertEqual(
            transport.calls[0]["payload"]["response_format"], {"type": "json_object"}
        )

    def test_missing_key_fails_without_transport_call(self) -> None:
        transport = SequenceTransport([])
        client = OpenAICompatibleClient(transport=transport, environment={})

        with self.assertRaises(ModelInvocationError) as caught:
            client.complete(real_model(), [{"role": "user", "content": "test"}])

        self.assertEqual(caught.exception.failure_type, "missing-api-key")
        self.assertEqual(transport.calls, [])

    def test_direct_client_persists_prompt_free_progress(self) -> None:
        transport = SequenceTransport([success_response("secret model output")])
        with tempfile.TemporaryDirectory() as directory:
            progress_path = Path(directory) / "model-progress.ndjson"
            client = OpenAICompatibleClient(
                transport=transport,
                environment={
                    "TEST_API_KEY": "secret-api-key",
                    "REFRACTROUTER_MODEL_PROGRESS": str(progress_path),
                },
                max_retries=0,
            )

            client.complete(
                real_model(),
                [{"role": "user", "content": "secret prompt"}],
            )
            records = [
                json.loads(line)
                for line in progress_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(
            [record["event"] for record in records],
            ["request-start", "request-finish"],
        )
        self.assertEqual(
            records[0]["endpoint"],
            "https://example.invalid/v1/chat/completions",
        )
        self.assertEqual(records[0]["timeout_ms"], 120_000)
        self.assertTrue(records[1]["ok"])
        self.assertEqual(records[1]["usage"]["output_tokens"], 25)
        serialized = json.dumps(records)
        self.assertNotIn("secret prompt", serialized)
        self.assertNotIn("secret model output", serialized)
        self.assertNotIn("secret-api-key", serialized)

    def test_direct_progress_finishes_when_response_is_invalid(self) -> None:
        transport = SequenceTransport([TransportResponse(200, {}, b"{}")])
        with tempfile.TemporaryDirectory() as directory:
            progress_path = Path(directory) / "model-progress.ndjson"
            client = OpenAICompatibleClient(
                transport=transport,
                environment={
                    "TEST_API_KEY": "secret",
                    "REFRACTROUTER_MODEL_PROGRESS": str(progress_path),
                },
                max_retries=0,
            )

            with self.assertRaises(ModelInvocationError) as caught:
                client.complete(
                    real_model(),
                    [{"role": "user", "content": "test"}],
                )
            records = [
                json.loads(line)
                for line in progress_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(caught.exception.failure_type, "invalid-response")
        self.assertEqual(records[-1]["event"], "request-finish")
        self.assertFalse(records[-1]["ok"])
        self.assertEqual(records[-1]["failure_type"], "invalid-response")

    def test_adapter_records_real_telemetry(self) -> None:
        transport = SequenceTransport([success_response()])
        adapter = OpenAICompatibleAdapter(
            OpenAICompatibleClient(
                transport=transport,
                environment={"TEST_API_KEY": "secret"},
                max_retries=0,
            )
        )
        task = make_task()
        node = task.nodes[0]

        result = adapter.invoke(task, node, "Plan the task", {}, real_model())

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.input_tokens, 100)
        self.assertEqual(result.output_tokens, 25)
        self.assertEqual(result.cached_input_tokens, 40)
        self.assertEqual(result.reasoning_tokens, 5)
        self.assertEqual(result.request_id, "req-test")
        self.assertEqual(result.attempts, 1)

    def test_adapter_rejects_hallucinated_evidence_identity(self) -> None:
        content = json.dumps(
            {
                "evidence": [
                    {
                        "source_id": "source_999",
                        "title": "Invented",
                        "claim": "Invented claim",
                        "content_hash": "invented-hash",
                    }
                ]
            }
        )
        transport = SequenceTransport([success_response(content)])
        adapter = OpenAICompatibleAdapter(
            OpenAICompatibleClient(
                transport=transport,
                environment={"TEST_API_KEY": "secret"},
                max_retries=0,
            )
        )
        task = make_task()
        node = next(node for node in task.nodes if node.node_type == "extraction")

        result = adapter.invoke(task, node, "Extract evidence", {}, real_model())

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failure_type, "invalid-evidence")

    def test_dsh_bridge_model_does_not_require_key_in_child_environment(self) -> None:
        class Bridge:
            def complete(self, model, messages, *, json_mode, timeout_seconds):
                self.model = model
                self.messages = messages
                self.json_mode = json_mode
                self.timeout_seconds = timeout_seconds
                return {
                    "ok": True,
                    "content": '{"requirements":"ok","sections":[],"constraints":[],"analysis":"ok"}',
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "cached_input_tokens": 0,
                        "reasoning_tokens": 4,
                    },
                    "finish_reason": "stop",
                    "request_id": "resp-ark-test",
                }

        bridge = Bridge()
        model = ModelSpec(
            model_id="ark-cheap",
            provider="ark-plan",
            input_cost_per_1k=0.05,
            output_cost_per_1k=0.05,
            capability=0.7,
            billing_unit="AFP",
            api_model="deepseek-v4-flash",
            api_key_env="CODEX_ARK_API_KEY",
            max_output_tokens=4096,
            wire_api="dsh-llm",
        )
        response = OpenAICompatibleClient(
            environment={}, dsh_bridge=bridge, max_retries=0
        ).complete(model, [{"role": "user", "content": "test"}], json_mode=True)

        self.assertEqual(response.request_id, "resp-ark-test")
        self.assertEqual(response.reasoning_tokens, 4)
        self.assertEqual(model_response_cost(model, response), 0.006)
        self.assertTrue(bridge.json_mode)
        self.assertEqual(bridge.timeout_seconds, 120.0)

    def test_stdio_bridge_uses_bounded_request_response_envelopes(self) -> None:
        reader = io.StringIO(
            json.dumps(
                {
                    "protocol": "refractrouter-dsh-llm/v1",
                    "type": "response",
                    "id": "1",
                    "ok": False,
                    "failure_type": "rate-limit",
                    "message": "retry later",
                }
            )
            + "\n"
        )
        writer = io.StringIO()
        bridge = DshStdioBridge(reader=reader, writer=writer)
        model = ModelSpec(
            "ark-cheap",
            "ark-plan",
            0.05,
            0.05,
            0.7,
            billing_unit="AFP",
            api_model="deepseek-v4-flash",
            api_key_env="CODEX_ARK_API_KEY",
            wire_api="dsh-llm",
        )

        response = bridge.complete(
            model,
            [{"role": "user", "content": "test"}],
            json_mode=True,
            timeout_seconds=120.0,
        )
        request = json.loads(writer.getvalue())

        self.assertEqual(response["failure_type"], "rate-limit")
        self.assertEqual(request["provider"], "ark-plan")
        self.assertEqual(request["model"], "deepseek-v4-flash")
        self.assertEqual(request["timeout_ms"], 120_000)
        self.assertNotIn("CODEX_ARK_API_KEY", writer.getvalue())

    def test_stdio_bridge_persists_prompt_free_progress(self) -> None:
        reader = io.StringIO(
            json.dumps(
                {
                    "protocol": "refractrouter-dsh-llm/v1",
                    "type": "response",
                    "id": "1",
                    "ok": True,
                    "content": "secret model output",
                    "usage": {"input_tokens": 10, "output_tokens": 3},
                }
            )
            + "\n"
        )
        writer = io.StringIO()
        model = ModelSpec(
            "ark-cheap",
            "ark-plan",
            0.05,
            0.05,
            0.7,
            billing_unit="AFP",
            api_model="deepseek-v4-flash",
            api_key_env="CODEX_ARK_API_KEY",
            wire_api="dsh-llm",
        )
        with tempfile.TemporaryDirectory() as directory:
            progress_path = Path(directory) / "bridge-progress.ndjson"
            bridge = DshStdioBridge(
                reader=reader, writer=writer, progress_path=progress_path
            )
            bridge.complete(
                model,
                [{"role": "user", "content": "secret prompt"}],
                json_mode=True,
                timeout_seconds=120.0,
            )
            records = [
                json.loads(line)
                for line in progress_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(
            [record["event"] for record in records],
            ["request-start", "request-finish"],
        )
        self.assertTrue(records[1]["ok"])
        self.assertEqual(records[1]["usage"]["output_tokens"], 3)
        serialized = json.dumps(records)
        self.assertNotIn("secret prompt", serialized)
        self.assertNotIn("secret model output", serialized)


if __name__ == "__main__":
    unittest.main()
