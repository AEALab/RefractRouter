"""Versioned output descriptions for model prompts, not provider enforcement claims."""
from __future__ import annotations

import hashlib
import json

NODE_PROMPT_VERSION = "v0.3"
EVIDENCE_FIELDS = ("source_id", "title", "content_hash", "claim")
CONTRACT_FAILURES = frozenset({
    "empty-output", "invalid-json", "invalid-html", "source-trace", "invalid-evidence",
    "invalid-planning-contract", "invalid-generation-contract", "missing-analysis",
    "incorrect-verification", "unresolved-citations",
})


def _object(properties):
    return {"type": "object", "required": list(properties), "properties": properties,
            "additionalProperties": False}


def _array(items, minimum=0):
    return {"type": "array", "items": items, "minItems": minimum}


def output_schema(node_type):
    text = {"type": "string", "minLength": 1}
    evidence = _array(_object({key: text for key in EVIDENCE_FIELDS}), 1)
    schemas = {
        "planning": _object({"requirements": text, "sections": _array(text, 1),
                             "constraints": _array(text), "analysis": text}),
        "extraction": _object({"evidence": evidence}),
        "synthesis": _object({"analysis": text, "evidence": evidence}),
        "generation": _object({"title": text, "sections": _array(_object({
            "heading": text, "paragraph": text}), 1), "evidence": evidence}),
        "verification": _object({"valid": {"type": "boolean"},
                                 "issues": _array(text), "summary": text}),
    }
    if node_type == "rendering":
        return None
    return schemas[node_type]


def prompt_contract_snapshot():
    contracts = {kind: output_schema(kind) for kind in (
        "planning", "extraction", "synthesis", "generation", "rendering", "verification")}
    return {"version": NODE_PROMPT_VERSION, "schema_sha256": hashlib.sha256(
        json.dumps(contracts, sort_keys=True).encode()).hexdigest(),
        "enforcement": "prompt description and local checks; no provider schema guarantee"}
