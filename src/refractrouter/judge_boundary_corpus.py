"""构造语义边界的输入/期望分离；数据可复用，不把协议探针计作评审成功。"""
from collections import Counter

from .purpose_review import packet


VERSION = "judge-boundary-corpus-v1"


def prepare(corpus):
    if (not isinstance(corpus, dict) or corpus.get("schemaVersion") != "review-semantic-boundaries-v1"
            or corpus.get("sampleKind") != "constructed-contract"):
        raise ValueError("评审语义边界必须声明为构造回归")
    cases = corpus.get("cases")
    if not isinstance(cases, list) or not cases or len(cases) > 256:
        raise ValueError("边界回归案例数量无效")
    inputs, expected, seen = [], [], set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {
            "id", "purpose", "task", "requirements", "candidate", "sources", "expected", "reason_zh"
        }:
            raise ValueError("边界案例字段错误")
        key = case["id"]
        if not isinstance(key, str) or not key.strip() or key in seen:
            raise ValueError("边界案例标识缺失或重复")
        if (case["expected"] not in ("PASS", "FAIL", "UNKNOWN") or not isinstance(case["reason_zh"], str)
                or not case["reason_zh"].strip()):
            raise ValueError("边界期望或理由无效")
        value = packet(case["purpose"], case["task"], case["requirements"], case["candidate"], case["sources"])
        inputs.append({"caseId": key, "packet": value})
        expected.append({"caseId": key, "packetSha256": value["packetSha256"],
                         "expected": case["expected"], "reason_zh": case["reason_zh"],
                         "sampleKind": "constructed-contract"})
        seen.add(key)
    purposes = Counter(c["packet"]["purpose"] for c in inputs)
    return {"contract": VERSION, "inputs": inputs, "adjudications": expected,
            "summary": {"total": len(inputs), "byPurpose": dict(purposes),
                        "sampleKind": "constructed-contract", "independentCalibrationCount": 0,
                        "newJudgeOutputs": 0, "modelCalls": 0}}
