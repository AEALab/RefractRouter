"""文本 DAG 的版本化节点契约；结构校验不替代语义评审。"""
from __future__ import annotations

import json
import re


PLAN_VERSION = "text-task-plan-v2"


def nonempty(value, name, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} requires nonempty text of at most {limit} characters")
    return value


def exact(raw, keys, name):
    if not isinstance(raw, dict) or set(raw) != set(keys):
        raise ValueError(f"invalid {name} fields")


def string_list(raw, name, maximum=10):
    if not isinstance(raw, list) or not 1 <= len(raw) <= maximum:
        raise ValueError(f"invalid {name}")
    values = [nonempty(v, name, 1000) for v in raw]
    if len(set(values)) != len(values):
        raise ValueError(f"duplicate {name}")
    return values


def integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"invalid {name}")


def validate_contract(raw, node, criterion_count):
    exact(raw, {"objective", "inputs", "output", "capability", "checks", "covers",
                "execution", "failure_policy"}, "node contract")
    nonempty(raw["objective"], "objective")
    if raw["execution"] != "text-model" or raw["failure_policy"] != "stop":
        raise ValueError("only text-model execution and stop failure policy are supported")
    inputs = raw["inputs"]
    if not isinstance(inputs, dict) or set(inputs) != set(node.parents):
        raise ValueError("contract inputs must match parents exactly")
    for value in inputs.values():
        exact(value, {"fields", "reason"}, "input contract")
        string_list(value["fields"], "input fields", 8)
        nonempty(value["reason"], "dependency reason")
    output = raw["output"]
    exact(output, {"format", "fields"}, "output contract")
    if output["format"] not in ("text", "json") or not isinstance(output["fields"], dict):
        raise ValueError("invalid output format")
    if not 1 <= len(output["fields"]) <= 8:
        raise ValueError("output requires 1..8 fields")
    if output["format"] == "text" and set(output["fields"]) != {"text"}:
        raise ValueError("text output requires the text field only")
    for key, description in output["fields"].items():
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", key):
            raise ValueError("invalid output field name")
        nonempty(description, "output field description", 1000)
    capability = raw["capability"]
    exact(capability, {"difficulty", "risk", "input_budget_tokens", "expected_output_tokens"}, "capability")
    if capability["difficulty"] not in ("low", "medium", "high") or capability["risk"] not in ("low", "medium", "high"):
        raise ValueError("invalid difficulty/risk")
    integer(capability["input_budget_tokens"], "input_budget_tokens", 256, 131072)
    integer(capability["expected_output_tokens"], "expected_output_tokens", 1, 8192)
    string_list(raw["checks"], "node checks")
    covers = raw["covers"]
    if not isinstance(covers, list) or len(covers) > criterion_count:
        raise ValueError("invalid criterion coverage")
    for index in covers:
        integer(index, "criterion index", 0, criterion_count - 1)
    if len(set(covers)) != len(covers):
        raise ValueError("duplicate criterion coverage")


def validate_handoffs(contracts, nodes, criteria):
    for node in nodes:
        validate_contract(contracts[node.node_id], node, len(criteria))
    coverage = set()
    for contract in contracts.values():
        coverage.update(contract["covers"])
        for parent, value in contract["inputs"].items():
            if not set(value["fields"]) <= set(contracts[parent]["output"]["fields"]):
                raise ValueError("input references an undeclared parent output field")
    if coverage != set(range(len(criteria))):
        raise ValueError("every acceptance criterion must have an owning node")


def decode_output(content, contract):
    """所有 JSON 交接字段为非空字符串；不支持未声明的任意嵌套 schema。"""
    if contract["output"]["format"] == "text":
        nonempty(content, "node output", 1000000)
        return {"text": content}
    try:
        value = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise ValueError("node-output-contract-invalid: expected JSON object") from exc
    fields = contract["output"]["fields"]
    if (not isinstance(value, dict) or set(value) != set(fields)
            or any(not isinstance(v, str) or not v.strip() for v in value.values())):
        raise ValueError("node-output-contract-invalid: expected exact nonempty string fields")
    return value
