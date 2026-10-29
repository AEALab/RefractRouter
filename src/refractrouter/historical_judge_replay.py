"""已暴露代码研究的零调用重放；原始判词、机械转换和来源裁定分别保留。"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .judge_qualification import qualify
from .purpose_review import decode, digest, text_digest


VERSION = "historical-judge-replay-v1"
DIMENSIONS = {"correctness", "completeness", "scope"}
LABELS = {"pass", "fail", "unknown"}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _file(root, name):
    _require(isinstance(name, str) and Path(name).name == name, "重放文件名不合法")
    path = root / name
    _require(not path.is_symlink() and path.stat().st_size <= 1024 * 1024, "重放文件超量或是链接")
    return path.read_text(encoding="utf-8")


def _sources(context):
    texts, lines = {}, {}
    for file in context["files"]:
        key = (file["source_id"], file["file_id"])
        _require(key not in texts, "来源标识重复")
        body = []
        for index, row in enumerate(file["numbered_source"].splitlines(keepends=True), 1):
            number, separator, line = row.partition("|")
            _require(separator == "|" and number == str(index), "来源行号不连续")
            body.append(line)
        lines[key], texts[key] = body, "".join(body)
    return texts, lines


def _references(rows, lines):
    _require(isinstance(rows, list) and len(rows) <= 128, "来源引用类型或数量无效")
    for row in rows:
        _require(isinstance(row, dict) and set(row) == {"source_id", "file_id", "start_line", "end_line"},
                 "来源引用字段不完整")
        _require(isinstance(row["source_id"], str) and isinstance(row["file_id"], str), "来源标识类型错误")
        key = (row["source_id"], row["file_id"])
        _require(key in lines, "引用不在冻结材料中")
        start, end = row["start_line"], row["end_line"]
        _require(type(start) is int and type(end) is int and 1 <= start <= end <= len(lines[key]),
                 "来源引用超出冻结行范围")


def _panel(material, judgment, conversion):
    raw = judgment["raw_utf8"]
    _require(text_digest(raw) == judgment["raw_sha256"], "原始评审摘要不符")
    payload = decode(raw)
    _require(payload == judgment["payload"], "原始评审与留存 payload 不一致")
    _require(isinstance(payload, dict) and set(payload) == {"candidates"}, "历史评审根字段无效")
    _, lines = _sources(material["context"])
    expected = material["candidates"]
    expected_items = {r["id"] for r in material["requirements"]}
    _require(expected_items == {"O1", "O2", "O3", "O4"}, "历史完整交付合同发生漂移")
    rows = payload["candidates"]
    _require(isinstance(rows, list) and len(rows) == len(expected), "历史候选缺失或重复")
    results, seen = {}, set()
    for candidate in rows:
        _require(isinstance(candidate, dict) and set(candidate) == {"id", "items"}, "历史候选字段无效")
        cid = candidate["id"]
        _require(isinstance(cid, str) and cid in expected and cid not in seen, "历史候选标识无效")
        seen.add(cid)
        answers = {r["id"]: r for r in expected[cid]["items"]}
        items = candidate["items"]
        _require(isinstance(items, list) and len(items) == 4, "历史评审未覆盖四项交付")
        seen_items, labels = set(), []
        for item in items:
            _require(isinstance(item, dict) and set(item) == {
                "id", "judgement", "reason", "source_refs", "citation_audit", "faults"
            }, "历史交付评审字段无效")
            oid = item["id"]
            _require(isinstance(oid, str) and oid in expected_items and oid not in seen_items, "历史交付标识无效")
            seen_items.add(oid)
            _require(set(item["judgement"]) == DIMENSIONS, "历史评审维度不完整")
            values = list(item["judgement"].values())
            _require(all(isinstance(v, str) and v in LABELS for v in values), "历史评审标签无效")
            failed = {k for k, v in item["judgement"].items() if v == "fail"}
            _references(item["source_refs"], lines)
            audits = item["citation_audit"]
            evidence_count = len(answers[oid]["evidence"])
            _require(isinstance(audits, list) and len(audits) == evidence_count, "历史附加引用未全部审核")
            audit_ids = set()
            for audit in audits:
                _require(isinstance(audit, dict) and set(audit) == {"index", "label", "reason"}, "历史引用审核字段无效")
                index, label = audit["index"], audit["label"]
                _require(type(index) is int and 0 <= index < evidence_count and index not in audit_ids,
                         "历史引用审核重复或越界")
                _require(isinstance(label, str) and label in LABELS, "历史引用审核标签无效")
                audit_ids.add(index)
                values.append(label)
                if label == "fail":
                    failed.add(f"citation:{index}")
            faults, targets = item["faults"], set()
            _require(isinstance(faults, list), "历史缺陷不是列表")
            for fault in faults:
                _require(isinstance(fault, dict) and set(fault) == {"targets", "kind", "quote", "reason", "source_refs"},
                         "历史缺陷字段无效")
                bound = fault["targets"]
                _require(isinstance(bound, list) and bool(bound) and all(isinstance(t, str) for t in bound)
                         and len(set(bound)) == len(bound) and set(bound) <= failed, "历史缺陷目标无效")
                quote, kind = fault["quote"], fault["kind"]
                _require(isinstance(quote, str) and ((kind == "claim" and bool(quote) and quote in answers[oid]["answer"])
                         or (kind == "missing" and quote == "")), "历史缺陷未绑定真实候选")
                _references(fault["source_refs"], lines)
                _require(kind != "claim" or bool(fault["source_refs"]), "确定缺陷缺少来源引用")
                targets.update(bound)
            _require(targets == failed, "历史失败维度缺少显式缺陷，不允许自动补写")
            labels.extend(values)
        full = "fail" if "fail" in labels else "unknown" if "unknown" in labels else "pass"
        results[cid] = full
    archived = {c["id"]: c["full"] for c in conversion["candidates"]}
    _require(results == archived, "原始判词重新折合与历史程序转换不同")
    return results


def _bound(text, binding, *, expected_sha):
    _require(text_digest(text) == expected_sha, "来源/候选全文摘要漂移")
    start, end = binding["start_codepoint"], binding["end_codepoint"]
    _require(type(start) is int and type(end) is int and 0 <= start < end <= len(text), "反例原文范围错误")
    _require(text[start:end] == binding["quote"], "反例原文与实际材料不同")
    _require(len(text[:start].encode()) == binding["start_utf8_byte"]
             and len(text[:end].encode()) == binding["end_utf8_byte"], "反例字节范围漂移")


def replay(directory):
    root = Path(directory)
    manifest = decode(_file(root, "manifest.json"))
    _require(manifest["schemaVersion"] == "historical-review-regression-v1", "历史回归版本无效")
    for name, provenance in manifest["originalFiles"].items():
        _require(text_digest(_file(root, name)) == provenance["sha256"], "归档原始文件漂移：" + name)
    adjudication = decode(_file(root, "source-adjudication.json"))
    cases, folds, bindings = {}, {}, {}
    for panel in manifest["panels"]:
        raw = _file(root, panel["materials"])
        _require(text_digest(raw) == panel["materialsSha256"], "完整候选/来源材料漂移")
        material = decode(raw)
        index = panel["caseIndex"]
        _require(index not in cases, "历史来源簇重复")
        cases[index] = (panel, material)
        blind = decode(_file(root, panel["blindMap"]))["task_map"]
        labels = _panel(material, decode(_file(root, panel["judgment"])), decode(_file(root, panel["conversion"])))
        for cid, arm in blind.items():
            folds[index, arm] = labels[cid]
            bindings[index, arm] = material["candidates"][cid]
    defects = defaultdict(list)
    for defect in adjudication["confirmed_defects"]:
        index, arm = defect["case"], defect["arm"]
        material = cases[index][1]
        answer = next(i["answer"] for i in bindings[index, arm]["items"] if i["id"] == defect["item_id"])
        _bound(answer, defect, expected_sha=defect["answer_sha256"])
        texts, _ = _sources(material["context"])
        for source in defect["source_bindings"]:
            if source["file_id"] == "question":
                text, sha = material["context"]["question"], source["question_sha256"]
            else:
                text = texts[source["source_id"], source["file_id"]]
                sha = source["file_utf8_sha256"]
            _bound(text, source, expected_sha=sha)
        defects[index, arm].append(defect)
    observations = []
    for (index, arm), found in sorted(defects.items()):
        observations.append({"caseId": f"code-{index}-{arm}", "clusterId": f"code-{index}",
                             "sampleKind": "historical-regression", "purpose": "advisor-delivery",
                             "backend": cases[index][0]["backend"],
                             "prediction": {"pass": "ALLOW", "fail": "BLOCK", "unknown": "UNKNOWN"}[folds[index, arm]],
                             "adjudication": {"label": "FAIL", "method": "source-counterexample",
                                              "recordSha256": digest(found)}})
    qualification = qualify(observations, {})
    return {"contract": VERSION, "modelCalls": 0, "historicalScoresModified": False,
            "panelCount": len(cases), "candidateCount": len(folds),
            "confirmedDefectCount": sum(map(len, defects.values())), "defectiveCandidateCount": len(defects),
            "confirmedDefectiveCandidatesApproved": sum(r["prediction"] == "ALLOW" for r in observations),
            "originalProgramLabelsReproduced": True, "counterexampleQuoteBindingsVerified": True,
            "semanticReasoningAutomated": False, "observations": observations, "qualification": qualification,
            "scope": "仅重放已暴露历史反例；来源语义裁定为原归档，非新模型或独立金标"}
