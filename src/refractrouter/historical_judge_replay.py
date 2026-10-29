"""已暴露代码研究的零调用重放；原始判词、机械转换和来源裁定分别保留。"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re

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
    return path.read_bytes().decode("utf-8")


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


def _panel(material, judgment, conversion, request):
    _require(judgment["mechanically_valid"] is True and conversion["mechanically_valid"] is True,
             "本重放不把原程序机械拒绝修成有效评审")
    messages = request["messages"]
    _require(len(messages) == 2 and messages[0]["role"] == "system" and messages[1]["role"] == "user",
             "原始评审请求结构漂移")
    original = decode(messages[1]["content"])
    _require(digest(original["candidates"]) == judgment["candidates_sha256"], "原始评审候选摘要不符")
    _require(digest(original["requirements"]) == judgment["requirements_sha256"], "原始评审要求摘要不符")
    extracted = {c["id"]: c["payload"] for c in original["candidates"]}
    _require(extracted == material["candidates"], "提取候选与实际原始评审请求不同")
    normalized_requirements = [{"id": r["id"], "text": r["text_zh"]} for r in material["requirements"]]
    _require(normalized_requirements == original["requirements"], "提取要求与实际原始评审请求不同")
    visible = original["context"]
    _require([s["source_id"] for s in material["context"]["sources"] if s["role"] == "primary"]
             == [visible["primary_source_id"]], "提取主来源身份与原请求不同")
    _require(visible["question"] == material["context"]["question"], "提取题干与原始请求不同")
    files = [{"source_id": f["source_id"], "file_id": f["file_id"], "path": f["path"],
              "text": f["numbered_source"]} for f in material["context"]["files"]]
    _require(files == visible["files"], "提取来源与实际原始评审请求不同")
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


def _bound(text, binding, *, expected_sha, require_lines=False):
    _require(text_digest(text) == expected_sha, "来源/候选全文摘要漂移")
    start, end = binding["start_codepoint"], binding["end_codepoint"]
    _require(type(start) is int and type(end) is int and 0 <= start < end <= len(text), "反例原文范围错误")
    _require(text[start:end] == binding["quote"], "反例原文与实际材料不同")
    _require(len(text[:start].encode()) == binding["start_utf8_byte"]
             and len(text[:end].encode()) == binding["end_utf8_byte"], "反例字节范围漂移")
    if require_lines or "start_line" in binding or "end_line" in binding:
        _require("start_line" in binding and "end_line" in binding, "反例来源必须提供完整行号")
        starts = [0] + [m.end() for m in re.finditer(r"\r\n|\r|\n", text) if m.end() < len(text)]
        first, last = binding["start_line"], binding["end_line"]
        _require(type(first) is int and type(last) is int and 1 <= first <= last <= len(starts),
                 "反例来源行号无效")
        lower, upper = starts[first - 1], starts[last] if last < len(starts) else len(text)
        _require(lower <= start < end <= upper and text.find(binding["quote"], lower, upper) == start
                 and text.find(binding["quote"], start + 1, upper) < 0, "反例来源行号与原文位置不符或不唯一")


def replay(directory):
    root = Path(directory)
    manifest = decode(_file(root, "manifest.json"))
    _require(manifest["schemaVersion"] == "historical-review-regression-v1", "历史回归版本无效")
    for name, provenance in manifest["originalFiles"].items():
        _require(text_digest(_file(root, name)) == provenance["sha256"], "归档原始文件漂移：" + name)
    adjudication = decode(_file(root, "source-adjudication.json"))
    cases, folds, bindings, context_ids = {}, {}, {}, {}
    for panel in manifest["panels"]:
        raw = _file(root, panel["materials"])
        _require(text_digest(raw) == panel["materialsSha256"], "完整候选/来源材料漂移")
        material = decode(raw)
        index = panel["caseIndex"]
        _require(index not in cases, "历史来源簇重复")
        cases[index] = (panel, material)
        blind = decode(_file(root, panel["blindMap"]))["task_map"]
        request_raw = _file(root, panel["request"])
        _require(text_digest(request_raw) == panel["requestSha256"], "原始评审请求摘要漂移")
        judgment = decode(_file(root, panel["judgment"]))
        context_ids[index] = judgment["context_sha256"]
        request = decode(request_raw)
        _require(request["model"] == panel["backend"]["model"] and
                 text_digest(request["messages"][0]["content"]) == panel["backend"]["templateSha256"],
                 "后端/模板身份与原始请求不同")
        labels = _panel(material, judgment, decode(_file(root, panel["conversion"])), request)
        texts, _ = _sources(material["context"])
        for source in material["context"]["sources"]:
            members = [{"path": f["path"], "file_utf8_sha256": text_digest(texts[f["source_id"], f["file_id"]])}
                       for f in material["context"]["files"] if f["source_id"] == source["source_id"]]
            members.sort(key=lambda f: f["path"])
            _require(digest({"commit": source["origin_commit"], "files": members}) == source["snapshot_sha256"],
                     "冻结来源快照摘要漂移")
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
        _require(isinstance(defect["source_bindings"], list) and 1 <= len(defect["source_bindings"]) <= 128,
                 "确定来源反例必须有非空来源绑定")
        for source in defect["source_bindings"]:
            if source["file_id"] == "question":
                _require(source["source_id"] == "question", "题干来源身份漂移")
                text, sha = material["context"]["question"], source["question_sha256"]
            else:
                metadata = next(f for f in material["context"]["files"]
                                if (f["source_id"], f["file_id"]) == (source["source_id"], source["file_id"]))
                origin = next(s for s in material["context"]["sources"] if s["source_id"] == source["source_id"])
                _require(source["path"] == metadata["path"] and source["commit"] == origin["origin_commit"]
                         and source["snapshot_sha256"] == origin["snapshot_sha256"]
                         and source["context_sha256"] == context_ids[index], "反例来源身份与冻结材料不符")
                text = texts[source["source_id"], source["file_id"]]
                sha = source["file_utf8_sha256"]
            _bound(text, source, expected_sha=sha, require_lines=True)
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
