"""官方 Jev 的结构化判别适配；复用规划路由的题目和判定规则。"""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .jev_choice_gate import VERSION as CHOICE_GATE_VERSION, evaluate_choice
from .planning_decision import (LayaDecisionAdapter, LocalDecisionCapacityError,
                                advisor_choice_feedback)
from .jev_transport import (JEV_MODEL, JEV_ENDPOINT, JEV_INPUT_USD_PER_MILLION,
                            route_spec, wire_payload)
from .jev_bridge import validate_result


class JevClient:
    """单次 HTTP 请求，不使用 SDK 的隐式重试，也不记录密钥。"""

    batch_size = 1000

    def __init__(self, api_key: str, *, timeout_seconds: float = 30, transport=None,
                 route: str = "typesafe"):
        if not api_key:
            raise ValueError("Jev API 凭证未就绪")
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._transport = transport or urlopen
        self.spec = route_spec(route)

    def predict(self, state, questions):
        if not isinstance(questions, dict) or not questions:
            raise ValueError("Jev 问题不能为空")
        payload = wire_payload(state, questions, self.spec["route"])
        request = Request(self.spec["endpoint"],
                          data=json.dumps(payload, ensure_ascii=False,
                                          separators=(",", ":")).encode("utf-8"),
                          headers={"Authorization": "Bearer " + self._api_key,
                                   "Content-Type": "application/json",
                                   "Accept": "application/json"}, method="POST")
        try:
            with self._transport(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            raise ValueError(f"Jev HTTP {exc.code}；此次调用不会自动重试") from None
        except (URLError, TimeoutError, OSError):
            raise ValueError("Jev 传输结果未确认；此次调用不会自动重试") from None
        try:
            result = json.loads(raw)
        except (TypeError, ValueError):
            raise ValueError("Jev 返回的 JSON 无效；用量待核对") from None
        validate_result(payload, result)
        return result


class JevDecisionAdapter(LayaDecisionAdapter):
    """只替换推论后端，保持同一题目与策略阈值。"""

    def __init__(self, *, api_key: str | None = None, method: str = "choice-v2",
                 timeout_seconds: float = 30, transport=None,
                 action_gate: str | None = None, route: str = "typesafe"):
        if action_gate not in (None, CHOICE_GATE_VERSION):
            raise ValueError("Jev 动作门槛版本不兼容")
        spec = route_spec(route)
        key = api_key or os.environ.get(spec["credentialRef"])
        self.agent = JevClient(key or "", timeout_seconds=timeout_seconds, transport=transport, route=route)
        self.model = spec["actualModel"]
        self.method = method
        self.action_gate = action_gate
        self.cold_start_ms = None

    def _ensure_complete(self, state, questions):
        try:
            wire_payload(state, questions, self.agent.spec["route"])
        except ValueError as exc:
            raise LocalDecisionCapacityError(str(exc)) from exc

    def decide_advisor(self, request):
        result = super().decide_advisor(request)
        if self.action_gate is None:
            return result
        gate = evaluate_choice(result.payload["raw"], strategy="advisor")
        choice = gate["rawChoice"] if gate["accepted"] else "UNRESOLVED"
        feedback = advisor_choice_feedback(choice)
        result.payload.update({"verdict": "REDO" if feedback else choice,
                               "feedback": feedback, "choiceGate": gate,
                               "ruleVersion": CHOICE_GATE_VERSION,
                               "selectedProbability": gate["selectedProbability"],
                               "choiceConfidence": gate["choiceConfidence"]})
        return result

    def decide_escalation(self, request):
        result = super().decide_escalation(request)
        if self.action_gate is None:
            return result
        gate = evaluate_choice(result.payload["raw"], strategy="escalation",
                               finish_reason=request.get("candidateFinishReason"))
        result.payload.update({"verdict": gate["rawChoice"] if gate["accepted"] else "UNCERTAIN",
                               "choiceGate": gate, "ruleVersion": CHOICE_GATE_VERSION,
                               "selectedProbability": gate["selectedProbability"],
                               "choiceConfidence": gate["choiceConfidence"]})
        return result
