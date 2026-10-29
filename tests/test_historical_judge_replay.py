"""真实历史文本只作零调用回归；不得反向修改既有判词来通过测试。"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from refractrouter.historical_judge_replay import replay, _panel
from experiments.replay_purpose_judges import run, validate_output


DATA = Path(__file__).resolve().parents[1] / "data/judge-regression-v1"


def test_actual_historical_misses_are_exposed_and_backend_remains_unqualified():
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.iterdir()}
    result = replay(DATA)
    assert result["panelCount"] == 2
    assert result["candidateCount"] == 6
    assert result["confirmedDefectCount"] == 4
    assert result["defectiveCandidateCount"] == 3
    assert result["confirmedDefectiveCandidatesApproved"] == 2
    assert result["historicalScoresModified"] is False
    assert result["modelCalls"] == 0
    assert result["originalProgramLabelsReproduced"] is True
    assert result["counterexampleQuoteBindingsVerified"] is True
    assert result["semanticReasoningAutomated"] is False
    group = result["qualification"]["groups"][0]
    assert group["falseAllow"]["numerator"] == 2
    assert group["falseAllow"]["denominator"] == 3
    assert group["falseBlock"]["denominator"] == 0
    assert group["falseBlock"]["upper"] is None
    assert group["independentFalseAllow"]["denominator"] == 0
    assert group["qualified"] is False
    assert "confirmed-counterexample-approved" in group["reasons"]
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.iterdir()}


def test_any_archived_original_response_change_is_detected_before_scoring(tmp_path):
    copied = tmp_path / "history"
    shutil.copytree(DATA, copied)
    path = copied / "case-0-judgment.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="原始文件漂移"):
        replay(copied)


def test_material_drift_cannot_be_silently_accepted(tmp_path):
    copied = tmp_path / "history"
    shutil.copytree(DATA, copied)
    path = copied / "case-1-materials.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="来源材料漂移"):
        replay(copied)


@pytest.mark.parametrize("change", ["omit-item", "invent-citation", "alter-raw", "rewrite-conversion"])
def test_archived_program_conversion_is_reproduced_from_full_raw_judgment(change):
    material = json.loads((DATA / "case-0-materials.json").read_bytes())
    judgment = json.loads((DATA / "case-0-judgment.json").read_bytes())
    conversion = json.loads((DATA / "case-0-conversion.json").read_bytes())
    request = json.loads((DATA / "case-0-request.json").read_bytes())
    if change == "omit-item":
        judgment["payload"]["candidates"][0]["items"].pop()
    elif change == "invent-citation":
        judgment["payload"]["candidates"][0]["items"][0]["source_refs"][0]["file_id"] = "hidden-answer"
    elif change == "alter-raw":
        judgment["raw_utf8"] += "\n"
    else:
        conversion["candidates"][0]["full"] = "fail"
    if change in ("omit-item", "invent-citation"):
        # 重新摘要也不能通过结构/引用检查，测试不会把它写回原历史文件。
        judgment["raw_utf8"] = json.dumps(judgment["payload"], ensure_ascii=False)
        judgment["raw_sha256"] = hashlib.sha256(judgment["raw_utf8"].encode()).hexdigest()
    with pytest.raises(ValueError):
        _panel(material, judgment, conversion, request)


def test_runner_preserves_inputs_and_refuses_to_reuse_or_mix_output_directory(tmp_path):
    out = tmp_path / "replay"
    assert run(DATA, out)["confirmedDefectiveCandidatesApproved"] == 2
    assert (out / "inputs-before.json").read_bytes() == (out / "inputs-after.json").read_bytes()
    with pytest.raises(FileExistsError):
        run(DATA, out)
    with pytest.raises(ValueError, match="混入"):
        run(DATA, DATA / "new-output")


def test_byte_only_line_ending_change_cannot_hide_behind_text_decoding(tmp_path):
    copied = tmp_path / "history"
    shutil.copytree(DATA, copied)
    path = copied / "case-0-judgment.json"
    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    path.write_bytes(raw[:-1] + b"\r\n")
    with pytest.raises(ValueError, match="原始文件漂移"):
        replay(copied)


def test_self_consistent_new_container_hash_does_not_override_original_request(tmp_path):
    copied = tmp_path / "history"
    shutil.copytree(DATA, copied)
    path = copied / "case-1-materials.json"
    value = json.loads(path.read_bytes())
    cid = next(c for c in value["candidates"] if c.startswith("v-659"))
    for row in value["candidates"][cid]["items"]:
        row["answer"] = "这是一份转录错误的答卷。"
    path.write_text(json.dumps(value, ensure_ascii=False))
    manifest = json.loads((copied / "manifest.json").read_bytes())
    manifest["panels"][1]["materialsSha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (copied / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    with pytest.raises(ValueError, match="提取候选"):
        replay(copied)


@pytest.mark.parametrize("field,value", [
    ("start_line", 999999), ("end_line", 999999), ("path", "wrong.py"),
    ("commit", "0" * 40), ("snapshot_sha256", "0" * 64), ("context_sha256", "0" * 64),
])
def test_changed_source_identity_or_line_range_is_rejected_even_after_new_manifest_pin(tmp_path, field, value):
    copied = tmp_path / "history"
    shutil.copytree(DATA, copied)
    path = copied / "source-adjudication.json"
    adjudication = json.loads(path.read_bytes())
    adjudication["confirmed_defects"][0]["source_bindings"][0][field] = value
    path.write_text(json.dumps(adjudication, ensure_ascii=False))
    manifest = json.loads((copied / "manifest.json").read_bytes())
    manifest["originalFiles"][path.name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (copied / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    with pytest.raises(ValueError, match="反例来源"):
        replay(copied)


def test_source_binding_requires_both_line_fields_even_when_candidate_binding_does_not(tmp_path):
    copied = tmp_path / "history"
    shutil.copytree(DATA, copied)
    path = copied / "source-adjudication.json"
    adjudication = json.loads(path.read_bytes())
    source = adjudication["confirmed_defects"][0]["source_bindings"][0]
    del source["start_line"], source["end_line"]
    path.write_text(json.dumps(adjudication, ensure_ascii=False))
    manifest = json.loads((copied / "manifest.json").read_bytes())
    manifest["originalFiles"][path.name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (copied / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    with pytest.raises(ValueError, match="完整行号"):
        replay(copied)


def test_empty_source_list_cannot_be_counted_as_verified_counterexample(tmp_path):
    copied = tmp_path / "history"
    shutil.copytree(DATA, copied)
    path = copied / "source-adjudication.json"
    adjudication = json.loads(path.read_bytes())
    adjudication["confirmed_defects"][0]["source_bindings"] = []
    path.write_text(json.dumps(adjudication, ensure_ascii=False))
    manifest = json.loads((copied / "manifest.json").read_bytes())
    manifest["originalFiles"][path.name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (copied / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    with pytest.raises(ValueError, match="非空来源绑定"):
        replay(copied)


@pytest.mark.parametrize("relative", [
    "reports/task-judge-audit-20260926/new-output", "reports/advisor-acceptance-20260928/new-output",
    "data/new-output", "src/new-output", "experiments/new-output",
])
def test_output_cannot_be_inserted_in_external_archives_or_implementation_before_mkdir(relative):
    root = Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError, match="混入历史材料"):
        validate_output(DATA, root / relative)
