"""官方 Jev 的结构化判别适配；与本地 Laya 共用规划路由问题及判定规则。"""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .planning_decision import LayaDecisionAdapter, LocalDecisionCapacityError


JEV_MODEL = "jev-1.13.0"
JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
JEV_INPUT_USD_PER_MILLION = 0.042


class JevClient:
    """单次 HTTP 请求；不安装会隐式重试的 SDK，不记录密钥。"""

    batch_size = 1000

    def __init__(self, api_key: str, *, timeout_seconds: float = 30, transport=None):
        if not api_key:
            raise ValueError("Jev API 凭证未就绪")
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds
        self._transport = transport or urlopen

    def predict(self, state, questions):
        if not isinstance(questions, dict) or not questions:
            raise ValueError("Jev 问题不能为空")
        payload = {"state": state, "model": JEV_MODEL, "questions": questions}
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(JEV_ENDPOINT, data=data, headers={
            "Authorization": "Bearer " + self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }, method="POST")
        try:
            with self._transport(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            # 服务端正文可能包含原始输入，不写进日志或异常。
            raise ValueError(f"Jev HTTP {exc.code}；此次调用不会自动重试") from None
        except (URLError, TimeoutError, OSError):
            raise ValueError("Jev 传输结果未确认；此次调用不会自动重试") from None
        try:
            result = json.loads(raw)
        except (TypeError, ValueError):
            raise ValueError("Jev 返回的 JSON 无效；用量待核对") from None
        if not isinstance(result, dict) or result.get("model") != JEV_MODEL:
            raise ValueError("Jev 实际模型版本与冻结版本不符；用量待核对")
        answers, usage = result.get("answers"), result.get("usage")
        if not isinstance(answers, dict) or set(answers) != set(questions):
            raise ValueError("Jev 判别答案不完整；用量待核对")
        if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0
                for k in ("input_tokens", "output_tokens")):
            raise ValueError("Jev 用量缺失；不得自动继续付费调用")
        return result


class JevDecisionAdapter(LayaDecisionAdapter):
    """只替换推论后端；冻结问题模板、阈值和规划策略映射。"""

    def __init__(self, *, api_key: str | None = None, method: str = "choice-v2",
                 timeout_seconds: float = 30, transport=None):
        key = api_key or os.environ.get("TYPESAFE_API_KEY")
        self.agent = JevClient(key or "", timeout_seconds=timeout_seconds, transport=transport)
        self.model = JEV_MODEL
        self.method = method
        self.cold_start_ms = None

    def _ensure_complete(self, state, questions):
        # 官方 32k state + 最长问题、64k 请求限制。按 UTF-8 字节保守阻断；不截断。
        state_bytes = len(json.dumps(state, ensure_ascii=False).encode("utf-8"))
        longest = max(len(json.dumps(item, ensure_ascii=False).encode("utf-8"))
                      for item in questions.values())
        total = len(json.dumps({"state": state, "model": JEV_MODEL, "questions": questions},
                               ensure_ascii=False).encode("utf-8"))
        if state_bytes + longest > 32000 or total > 64000:
            raise LocalDecisionCapacityError("Jev 输入超过保守容量上限；没有截断或发起调用")
