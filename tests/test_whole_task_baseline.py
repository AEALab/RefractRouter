"""证据写入不覆盖，失败不得转换成通过，不泄漏认证环境变量。"""
import json
from types import SimpleNamespace

import pytest

from experiments import run_whole_task_baseline as baseline


def test_environment_removes_credentials_without_rewriting_paths():
    env = baseline.test_environment({"PATH": "/usr/bin", "HOME": "/fixture", "ARK_API_KEY": "secret",
        "VOLC_ACCESSKEY": "secret", "VOLC_SECRETKEY": "secret", "GH_TOKEN": "secret", "DEEPSEEK_API_KEY": "secret",
        "PYTEST_ADDOPTS": "-k test_loopback_addresses", "PYTEST_PLUGINS": "fixture-filter",
        "PYTHONPATH": "/old/source"})
    assert env["PATH"] == "/usr/bin" and env["HOME"] == "/fixture"
    assert not any("secret" in value for value in env.values())
    assert env["UV_OFFLINE"] == "1"
    assert not {"PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONPATH"} & env.keys()


def test_snapshot_binds_uncommitted_bytes_and_does_not_follow_symlink(tmp_path):
    file = tmp_path / "source.py"
    file.write_text("# 中文\n")
    (tmp_path / "link").symlink_to("/not-readable-outside-fixture")
    before = baseline.snapshot_files(tmp_path, ["source.py", "missing", "link"])
    file.write_text("# changed\n")
    after = baseline.snapshot_files(tmp_path, ["source.py", "missing", "link"])
    assert before["source.py"]["sha256"] != after["source.py"]["sha256"]
    assert before["link"] == after["link"] and before["link"]["kind"] == "symlink"
    assert before["missing"] == {"kind": "missing", "sha256": None}


@pytest.mark.parametrize("exit_code,failures,skips,guard,passed", [
    (0, 0, 0, True, True), (1, 1, 0, True, False), (0, 0, 1, True, False),
    (0, 0, 0, False, False), (1, 0, 0, True, False),
])
def test_actual_exit_reports_and_guard_all_required(tmp_path, monkeypatch, exit_code, failures, skips, guard, passed):
    target = tmp_path / "fresh"
    monkeypatch.setattr(baseline, "describe_environment", lambda _: {"fixture": True})

    def fake_test(command, **kwargs):
        assert command[:3] == ["uv", "run", "pytest"]
        assert command[3:6] == ["tests", "-o", "addopts="]
        (target / "junit.xml").write_text(f'<testsuites><testsuite tests="3" failures="{failures}" errors="0" skipped="{skips}"/></testsuites>')
        if guard:
            (target / "network.json").write_text(json.dumps({"external_network_blocked": True,
                "collection": {"collected": 3, "selected": 3, "deselected": 0, "executed": 3}}))
        kwargs["stdout"].write("确定性夹具日志\n")
        return SimpleNamespace(returncode=exit_code)

    monkeypatch.setattr(baseline.subprocess, "run", fake_test)
    result_code = baseline.run(target)
    result = json.loads((target / "result.json").read_text())
    assert result["passed"] is passed
    assert (result_code == 0) is passed
    assert not result["paidExecutionRequested"]
    with pytest.raises(FileExistsError):
        baseline.run(target)


def test_no_paid_or_partial_suite_switches():
    with pytest.raises(SystemExit):
        baseline.main(["--output-dir", "unused", "--execute"])
    with pytest.raises(SystemExit):
        baseline.main(["--output-dir", "unused", "--ignore", "tests"])


def test_source_modified_by_test_cannot_produce_passing_baseline(tmp_path, monkeypatch):
    source = tmp_path / "historical.json"
    source.write_text("original")
    original = baseline.snapshot_files(tmp_path, [source.name])
    monkeypatch.setattr(baseline, "ROOT", tmp_path)
    monkeypatch.setattr(baseline, "describe_environment", lambda _: {"sourceSnapshot": original})
    target = tmp_path / "new-run"

    def fake(command, **kwargs):
        source.write_text("changed")
        (target / "junit.xml").write_text('<testsuites><testsuite tests="1"/></testsuites>')
        (target / "network.json").write_text(json.dumps({"external_network_blocked": True,
            "collection": {"collected": 1, "selected": 1, "deselected": 0, "executed": 1}}))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(baseline.subprocess, "run", fake)
    assert baseline.run(target) == 1
    result = json.loads((target / "result.json").read_text())
    assert not result["passed"]
    assert result["sourceChangesAfterRun"] == [source.name]


@pytest.mark.parametrize("counts,valid", [
    ({"collected": 15, "selected": 4, "deselected": 11, "executed": 4}, False),
    ({"collected": 15, "selected": 15, "deselected": 0, "executed": 14}, False),
    ({"collected": 0, "selected": 0, "deselected": 0, "executed": 0}, False),
    ({"collected": 15, "selected": 15, "deselected": 0, "executed": 15}, True),
    ({}, False),
])
def test_partial_or_unexecuted_collection_is_not_complete(counts, valid):
    assert baseline.collection_complete({"collection": counts}, {"tests": 15}) is valid
