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
    "unexpected-evidence",
})


def _object(properties):
    return {"type": "object", "required": list(properties), "properties": properties,
            "additionalProperties": False}


def _array(items, minimum=0):
    return {"type": "array", "items": items, "minItems": minimum}


def output_schema(node_type, version="v0.3"):
    if version not in {"v0.3", "v0.4"}:
        raise ValueError(f"Unknown output contract: {version}")
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
    if version == "v0.4" and node_type in {"synthesis", "generation"}:
        schema = schemas[node_type]
        schema["required"].remove("evidence")
        del schema["properties"]["evidence"]
    return schemas[node_type]


def prompt_contract_snapshot(version="v0.3"):
    contracts = {kind: output_schema(kind, version) for kind in (
        "planning", "extraction", "synthesis", "generation", "rendering", "verification")}
    return {"version": version, "schema_sha256": hashlib.sha256(
        json.dumps(contracts, sort_keys=True).encode()).hexdigest(),
        "enforcement": "prompt description and local checks; no provider schema guarantee"}
