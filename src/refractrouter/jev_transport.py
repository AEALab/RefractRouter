"""Jev 接入渠道的冻结合同；策略不依赖 HTTP 提供方。"""

from copy import deepcopy
import json

JEV_MODEL = "jev-1.13.0"
JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
JEV_INPUT_USD_PER_MILLION = 0.042

_ROUTES = {
    "typesafe": {
        "model": JEV_MODEL, "actualModel": JEV_MODEL, "endpoint": JEV_ENDPOINT,
        "credentialRef": "TYPESAFE_API_KEY", "maxInputTokens": 64000,
        "maxRequestBytes": 98304, "pricingSource": "https://docs.typesafe.ai/models",
    },
    "openrouter": {
        "model": "typesafe/jev-1.13", "actualModel": "typesafe/jev-1.13-20260917",
        "endpoint": "https://openrouter.ai/api/alpha/decisions",
        "credentialRef": "OPENROUTER_API_KEY", "maxInputTokens": 32000,
        # 字节是传输技术上限，不冒充提供方的 32k token 上下文容量。
        "maxRequestBytes": 98304,
        "pricingSource": "https://openrouter.ai/typesafe/jev-1.13",
    },
}


def route_spec(route="typesafe"):
    if not isinstance(route, str) or route not in _ROUTES:
        raise ValueError("Jev 接入方式必须是 typesafe 或 openrouter")
    return {"route": route, **deepcopy(_ROUTES[route])}


def payload_route(payload):
    for route, spec in _ROUTES.items():
        if payload.get("model") == spec["model"]:
            return route_spec(route)
    raise ValueError("未知 Jev 请求模型")


def wire_payload(state, questions, route="typesafe"):
    spec = route_spec(route)
    payload = {"state": state, "model": spec["model"], "questions": questions}
    if route == "openrouter":
        payload["provider"] = {"only": ["TypeSafe"], "allow_fallbacks": False}
    size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if size > spec["maxRequestBytes"]:
        raise ValueError(f"Jev 完整判别输入超出 {route} 本地容量（{size} 字节）；不会截断或派发")
    return payload
