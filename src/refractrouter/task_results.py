"""版本化结果视图；财务数值始终引用原逐调用账本，反馈不改变执行或费用。"""
from copy import deepcopy

from .task_outcomes import TaskOutcomeJournal, VERSION as EVENT_VERSION, digest
from .task_projection import summary as projection_summary

VERSION = "task-result-v1"
CALL_FIELDS = ("call_id", "model_id", "provider", "actual_model", "purpose", "status", "disposition",
               "host_request_id",
               "input_sha256", "output_sha256", "billing_unit", "billing_mode", "reserved", "charged",
               "reference_cost_cny", "cash_cost_cny", "cash_cost_status", "cost_basis",
               "provider_cost_confirmed", "input_tokens", "output_tokens", "cached_input_tokens",
               "cache_usage_source", "cache_usage_available", "reasoning_tokens", "latency_ms",
               "ttft_ms", "request_id", "dispatch_at", "finish_reason", "usage_type", "price_snapshot",
               "pricing_tier", "pricing_source", "pricing_checked_at")


def event(identifier, kind, *, candidate=None, source="router", actor="router", status,
          calls=(), artifacts=(), criteria="task-result-v1", reason="recorded", supersedes=None):
    return {"schemaVersion": EVENT_VERSION, "eventId": identifier, "kind": kind, "source": source,
            "actor": actor, "candidateId": candidate[0] if candidate else None,
            "candidateSha256": candidate[1] if candidate else None, "status": status,
            "supersedes": supersedes, "callIds": list(calls), "artifactSha256": list(artifacts),
            "criteriaVersion": criteria, "reasonCode": reason}


def scope_for(record):
    return digest({k: record["identity"][k] for k in ("session", "agent")})


def candidate_of(call):
    raw = call.get("response")
    if call.get("purpose") not in {"execute", "redo", "takeover"} or not isinstance(raw, dict):
        return None
    value = {"content": raw.get("content", ""), "toolCalls": raw.get("tool_calls", []),
             "finishReason": raw.get("finish_reason")}
    return (call["call_id"], digest(value))


class TaskResults:
    def __init__(self, root):
        self.journal = TaskOutcomeJournal(root)

    def sync(self, record):
        """重放已持久化的管理调用，不派发模型；事件 ID 固定，重复同步不会重复记账。"""
        scope, task = scope_for(record), record["runId"]
        if self.journal.snapshot(scope, task)["deleted"]:
            return
        candidates = {}
        pending = []
        for call in record["calls"]:
            token = call.get("call_id")
            if not token:
                continue
            projection = {k: call[k] for k in CALL_FIELDS if k in call}
            pending.append(event("call-" + digest(projection), "call-reference",
                status="unknown" if call.get("status") in {"unknown-usage", "reserved"} else "known",
                calls=[token], artifacts=[digest(projection)], criteria="financial-ledger-v1"))
            candidate = candidate_of(call)
            if candidate:
                candidates[token] = candidate
                pending.append(event("candidate-" + token, "candidate", candidate=candidate,
                    status="generated", calls=[token]))
                disposition = call.get("disposition")
                if disposition in {"accepted", "discarded"}:
                    pending.append(event("disposition-" + token + "-" + disposition,
                        "delivery", candidate=candidate, status=disposition, calls=[token],
                        criteria="router-selection-v1", reason="router-" + disposition))
        for decision in record["decisions"]:
            candidate = candidates.get(decision.get("candidateCallId"))
            if not candidate:
                continue  # 选模/进度判别不是对候选正确性的反馈。
            verdict = decision.get("reviewVerdict") or decision.get("decision", {}).get("verdict")
            status = {"APPROVE": "accepted", "REDO": "needs_revision", "UNRESOLVED": "unknown",
                      "PROCEED": "accepted", "DEFECT": "rejected", "STALL": "unknown",
                      "UNCERTAIN": "unknown"}.get(verdict, "unknown")
            pending.append(event("review-" + digest(decision), "feedback", candidate=candidate,
                source="tool" if decision.get("role") == "tool-validation" else "model-review",
                actor="router-review", status="rejected" if decision.get("role") == "tool-validation" else status,
                calls=[decision["callId"]] if decision.get("callId") else [], artifacts=[digest(decision)],
                criteria=decision.get("ruleVersion", "legacy-review"), reason="review-recorded"))
        self.journal.append_many(scope, task, pending)

    def view(self, record):
        scope, task = scope_for(record), record["runId"]
        snapshot = self.journal.snapshot(scope, task)
        rows = snapshot["events"]
        replaced = {r["event"]["supersedes"] for r in rows if r["event"]["supersedes"]}
        candidates = []
        for row in rows:
            e = row["event"]
            if e["kind"] != "candidate":
                continue
            related = [r for r in rows if r["event"]["candidateId"] == e["candidateId"]]
            deliveries = [r["event"]["status"] for r in related if r["event"]["kind"] == "delivery"]
            feedback = [r for r in related if r["event"]["kind"] == "feedback"]
            active = [r for r in feedback if r["event"]["eventId"] not in replaced]
            by_source = {source: [r for r in active if r["event"]["source"] == source]
                         for source in ("user", "hidden-evaluation", "tool", "model-review")}
            # 有矛盾或缺失一律未知；任一来源的通过都不能替其他来源背书。
            labels = {source: next(iter(values)) if len(values := {r["event"]["status"] for r in items}) == 1
                      else "unknown" for source, items in by_source.items()}
            candidates.append({"candidateId": e["candidateId"], "candidateSha256": e["candidateSha256"],
                "callIds": e["callIds"], "routerDisposition": deliveries[-1] if deliveries else "unknown",
                "transportDelivery": "unknown", "feedback": feedback, "acceptanceBySource": labels})
        calls = [{k: deepcopy(c[k]) for k in CALL_FIELDS if k in c} for c in record["calls"]]
        return {"schemaVersion": VERSION, "runId": task, "identity": deepcopy(record["identity"]),
            "parentIdentity": deepcopy(record.get("parentIdentity")),
            "parentIdentityStatus": "provided" if record.get("parentIdentity") else "not-provided",
            "coverage": "managed-agent-only", "outsideManagedCalls": "unknown",
            "status": record["status"], "strategy": record["strategy"], "configDigest": record["configDigest"],
            "taskProjection": projection_summary(record.get("state", {}).get("currentTask")),
            "costContext": deepcopy(record.get("state", {}).get("taskCostContext")),
            "classificationTaskDigest": record.get("state", {}).get("taskClassificationProjectionDigest"),
            "taskShadow": deepcopy(record.get("state", {}).get("taskShadow")),
            "stageProgressShadow": deepcopy(record.get("state", {}).get("stageProgressShadow")),
            "evidenceDigest": record.get("state", {}).get("last_evidence"),
            "models": [{"id": m["id"], "provider": m.get("provider"), "model": m.get("model"),
                        "revision": m.get("revision"), "revisionStatus": "configured" if m.get("revision") else "not-pinned"}
                       for m in record.get("configuration", {}).get("models", [])],
            "candidates": candidates, "calls": calls,
            "decisions": [{"sha256": digest(d), **{k: d[k] for k in
                ("step", "role", "model", "reason", "callId", "candidateCallId", "ruleVersion") if k in d}}
                for d in record["decisions"]],
            "costsByUnit": deepcopy(record.get("costsByUnit", {})),
            "referenceCosts": deepcopy(record.get("referenceCosts")), "timing": deepcopy(record.get("timing")),
            "financialAuthority": "original-call-ledger", "historicalEvidence": "preserved",
            "metadataStatus": "deleted" if snapshot["deleted"] else
                              "recorded" if record.get("resultSchemaVersion") == VERSION else "legacy-unknown",
            "eventHead": snapshot["head"], "deletion": snapshot["deleted"], "events": rows}
