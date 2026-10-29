"""按用途/后端/模板隔离的离线准入门槛，不修改生产配置或历史判词。"""
from __future__ import annotations

from collections import Counter, defaultdict
import math
from statistics import NormalDist

from .purpose_review import PURPOSES, digest, wire


VERSION = "judge-qualification-v1"
IDENTITY_FIELDS = {"provider", "model", "modelRevision", "templateSha256", "contractVersion", "scoreThreshold"}
OUTCOMES = {"ALLOW", "BLOCK", "UNKNOWN", "FORMAT_REJECT"}
LABELS = {"PASS", "FAIL", "UNKNOWN"}
GOLD_METHODS = {"source-counterexample", "explicit-acceptance", "human-decision", "pending"}


def _probability(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("准入概率门槛无效")
    return float(value)


def backend_identity(value):
    if not isinstance(value, dict) or set(value) != IDENTITY_FIELDS:
        raise ValueError("必须固定评审 provider/模型/修订/模板/合同/分数阈值")
    for key in IDENTITY_FIELDS - {"scoreThreshold"}:
        if not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 256:
            raise ValueError("评审身份字段无效")
    if len(value["templateSha256"]) != 64 or any(c not in "0123456789abcdef" for c in value["templateSha256"]):
        raise ValueError("评审模板摘要无效")
    if value["scoreThreshold"] is not None:
        _probability(value["scoreThreshold"])
    wire(value)
    return value


def interval(successes, total, *, confidence=.95):
    """单侧 Wilson 上界；分母为0时未知，不能冒充零风险。"""
    if type(successes) is not int or type(total) is not int or not 0 <= successes <= total:
        raise ValueError("统计分子/分母无效")
    confidence = _probability(confidence)
    if not .5 < confidence < 1:
        raise ValueError("置信水平必须大于0.5且小于1")
    if not total:
        return {"numerator": successes, "denominator": total, "rate": None, "upper": None,
                "confidence": confidence, "method": "one-sided-wilson"}
    z = NormalDist().inv_cdf(confidence)
    p, a = successes / total, z * z / total
    upper = (p + a / 2 + z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))) / (1 + a)
    return {"numerator": successes, "denominator": total, "rate": p, "upper": min(1., upper),
            "confidence": confidence, "method": "one-sided-wilson"}


def _validate_observation(row):
    wire(row)
    if not isinstance(row, dict) or set(row) != {
        "caseId", "clusterId", "sampleKind", "purpose", "backend", "prediction", "adjudication"
    }:
        raise ValueError("准入观察字段错误")
    for key in ("caseId", "clusterId"):
        if not isinstance(row[key], str) or not row[key].strip() or len(row[key]) > 256:
            raise ValueError("样本/来源簇身份无效")
    if not isinstance(row["purpose"], str) or row["purpose"] not in PURPOSES:
        raise ValueError("准入用途无效")
    backend_identity(row["backend"])
    if not isinstance(row["sampleKind"], str) or row["sampleKind"] not in ("historical-regression", "constructed-contract", "independent-calibration"):
        raise ValueError("校准材料来源无效")
    if not isinstance(row["prediction"], str) or row["prediction"] not in OUTCOMES:
        raise ValueError("评审预测必须区分通过/阻拦/未知/格式拒绝")
    gold = row["adjudication"]
    if not isinstance(gold, dict) or set(gold) != {"label", "method", "recordSha256"}:
        raise ValueError("最终裁定须独立记录标签、来源方法和记录摘要")
    if (not isinstance(gold["label"], str) or not isinstance(gold["method"], str)
            or gold["label"] not in LABELS or gold["method"] not in GOLD_METHODS):
        raise ValueError("不能以模型多数票生成金标")
    if (gold["label"] == "UNKNOWN") != (gold["method"] == "pending"):
        raise ValueError("未决裁定不得伪装成确切金标")
    if gold["method"] == "source-counterexample" and gold["label"] != "FAIL":
        raise ValueError("源码反例只能证明失败，不能据此证明全文通过")
    sha = gold["recordSha256"]
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("最终裁定记录摘要无效")
    wire(row)


def qualify(observations, policies):
    """每个精确 group 需要显式策略。观察应由重放器构建；此函数不凭空验证裁定来源。"""
    if not isinstance(observations, list) or len(observations) > 10000 or not isinstance(policies, dict):
        raise ValueError("校准观察/策略类型错误或超量")
    groups, seen = defaultdict(list), set()
    for row in observations:
        _validate_observation(row)
        identity = {"purpose": row["purpose"], "backend": row["backend"]}
        key = digest(identity)
        sample = (key, row["caseId"])
        if sample in seen:
            raise ValueError("同一评审身份重复样本不能增加分母")
        seen.add(sample)
        groups[key].append(row)
    if set(policies) - set(groups):
        raise ValueError("准入策略包含未观察的评审身份")
    results = []
    for key, rows in sorted(groups.items()):
        counts = Counter(r["prediction"] for r in rows)
        negatives = [r for r in rows if r["adjudication"]["label"] == "FAIL"]
        positives = [r for r in rows if r["adjudication"]["label"] == "PASS"]
        false_allow = sum(r["prediction"] == "ALLOW" for r in negatives)
        false_block = sum(r["prediction"] == "BLOCK" for r in positives)
        unsupported = sum(r["prediction"] == "ALLOW" and r["adjudication"]["label"] == "UNKNOWN" for r in rows)
        independent = [r for r in rows if r["sampleKind"] == "independent-calibration"]
        independent_neg = [r for r in independent if r["adjudication"]["label"] == "FAIL"]
        independent_pos = [r for r in independent if r["adjudication"]["label"] == "PASS"]
        allow_bound = interval(sum(r["prediction"] == "ALLOW" for r in independent_neg), len(independent_neg))
        block_bound = interval(sum(r["prediction"] == "BLOCK" for r in independent_pos), len(independent_pos))
        reasons = []
        policy = policies.get(key)
        if policy is None:
            reasons.append("missing-exact-backend-purpose-policy")
        else:
            required = {"minNegative", "minPositive", "maxFalseAllowUpper", "maxFalseBlockUpper",
                        "maxUnknownRate", "maxFormatRejectRate"}
            if not isinstance(policy, dict) or set(policy) != required:
                raise ValueError("评审准入策略字段错误")
            for field in ("minNegative", "minPositive"):
                if type(policy[field]) is not int or policy[field] < 1:
                    raise ValueError("必须固定正反例最小分母")
            for field in required - {"minNegative", "minPositive"}:
                _probability(policy[field])
            if len(independent_neg) < policy["minNegative"] or len(independent_pos) < policy["minPositive"]:
                reasons.append("insufficient-independent-calibration")
            for bound, maximum, reason in (
                (allow_bound, policy["maxFalseAllowUpper"], "false-allow-upper-exceeded"),
                (block_bound, policy["maxFalseBlockUpper"], "false-block-upper-exceeded"),
            ):
                if bound["upper"] is None or bound["upper"] > maximum:
                    reasons.append(reason)
            if independent and sum(r["prediction"] == "UNKNOWN" for r in independent) / len(independent) > policy["maxUnknownRate"]:
                reasons.append("unknown-rate-exceeded")
            if independent and sum(r["prediction"] == "FORMAT_REJECT" for r in independent) / len(independent) > policy["maxFormatRejectRate"]:
                reasons.append("format-rejection-rate-exceeded")
        if false_allow:
            reasons.append("confirmed-counterexample-approved")
        if unsupported:
            reasons.append("unresolved-case-approved")
        if len({r["clusterId"] for r in independent}) != len(independent):
            reasons.append("independent-calibration-has-reused-source-cluster")
        if rows[0]["backend"]["modelRevision"].lower() in ("unknown", "unpinned", "unavailable"):
            reasons.append("model-revision-unpinned")
        results.append({"groupId": key, "identity": {"purpose": rows[0]["purpose"], "backend": rows[0]["backend"]},
                        "total": len(rows), "predictions": {k: counts[k] for k in sorted(OUTCOMES)},
                        "falseAllow": interval(false_allow, len(negatives)),
                        "falseBlock": interval(false_block, len(positives)),
                        "unsupportedAllow": unsupported,
                        "independentFalseAllow": allow_bound, "independentFalseBlock": block_bound,
                        "descriptiveIntervalsAssumeIndependentObservations": True,
                        "qualified": not reasons, "reasons": reasons,
                        "caseIds": [r["caseId"] for r in rows]})
    return {"contract": VERSION, "groups": results, "productionConfigurationChanged": False,
            "modelCalls": 0, "allObservedGroupsQualified": bool(results) and all(r["qualified"] for r in results)}
