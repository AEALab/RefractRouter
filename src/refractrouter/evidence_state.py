"""Immutable, application-owned evidence for the explicit v0.4 DAG protocol."""
from dataclasses import asdict, dataclass, replace
import hashlib
import json

from .schemas import TaskDAG


def validate_evidence(task, evidence):
    known = {source.source_id: source for source in task.source_documents}
    valid = isinstance(evidence, list) and bool(evidence)
    ids, claims = set(), set()
    for item in evidence if isinstance(evidence, list) else []:
        sid = item.get("source_id") if isinstance(item, dict) else None
        source = known.get(sid) if isinstance(sid, str) else None
        if (not source or item.get("content_hash") != source.content_hash
                or item.get("title") != source.title or not isinstance(item.get("claim"), str)
                or not item["claim"].strip()):
            valid = False
        elif (sid, " ".join(item["claim"].split()).casefold()) in claims:
            valid = False
        else:
            ids.add(sid)
            claims.add((sid, " ".join(item["claim"].split()).casefold()))
    return valid, ids


@dataclass(frozen=True)
class EvidenceItem:
    source_id: str
    title: str
    content_hash: str
    claim: str


@dataclass(frozen=True)
class EvidenceArtifact:
    node_id: str
    output_sha256: str
    items: tuple[EvidenceItem, ...]

    def snapshot(self):
        return asdict(self)


def evidence_artifact(task: TaskDAG, context) -> EvidenceArtifact:
    """Read only the extraction node, never a descendant's claimed replacement."""
    nodes = [node for node in task.nodes if node.node_type == "extraction"]
    if len(nodes) != 1:
        raise ValueError("v0.4 DAG requires exactly one evidence extraction node")
    node_id = nodes[0].node_id
    raw = context.get(node_id)
    try:
        value = json.loads(raw)
        evidence = value.get("evidence") if isinstance(value, dict) else None
    except (ValueError, TypeError):
        evidence = None
    if not validate_evidence(task, evidence)[0]:
        raise ValueError("Missing or invalid application evidence")
    return EvidenceArtifact(node_id, hashlib.sha256(raw.encode()).hexdigest(), tuple(
        EvidenceItem(**{key: item[key] for key in EvidenceItem.__dataclass_fields__})
        for item in evidence))


def uses_evidence_state(task):
    return task.output_contract_version == "v0.4" and task.execution_mode == "dag"


def with_evidence_state(task: TaskDAG) -> TaskDAG:
    extractions = [node.node_id for node in task.nodes if node.node_type == "extraction"]
    if len(extractions) != 1:
        raise ValueError("v0.4 DAG requires exactly one extraction node")
    owner = extractions[0]
    nodes = tuple(replace(node, parents=tuple(dict.fromkeys((*node.parents, owner))))
                  if node.node_type in {"synthesis", "generation", "rendering", "verification"}
                  else node for node in task.nodes)
    return replace(task, nodes=nodes, output_contract_version="v0.4", execution_mode="dag")
