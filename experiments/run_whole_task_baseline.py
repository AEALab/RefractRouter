"""记录完整确定性测试基线；无付费模式，不接收模型凭证或样本答案。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def test_environment(environment):
    """剔除继承的认证变量；不声称这是子进程/宿主文件的 OS 级隔离。"""
    result = {key: value for key, value in environment.items()
              if not key.startswith("PYTEST_") and key not in {"PYTHONPATH", "PYTHONHOME"}
              and re.search(r"(?:TOKEN|PASSWORD|SECRET|CREDENTIAL|API_?KEY|ACCESS_?KEY)", key, re.I) is None}
    result.update(UV_OFFLINE="1", LANGSMITH_TRACING="false", REFRACT_TEST_OFFLINE="1")
    return result


def describe_environment(environment):
    def output(command):
        result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True)
        return {"exitCode": result.returncode, "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip()}

    listed = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            cwd=ROOT, env=environment, capture_output=True, text=True, check=True)
    snapshot = snapshot_files(ROOT, set(listed.stdout.rstrip("\0").split("\0")) - {""})
    return {"python": sys.version, "platform": platform.platform(), "sourceSnapshot": snapshot,
            "sourceRevision": output(["git", "rev-parse", "HEAD"]),
            "sourceStatus": output(["git", "status", "--porcelain"]),
            "uv": output(["uv", "--version"]), "node": output(["node", "--version"]),
            "npm": output(["npm", "--version"]), "credentialVariablesForwarded": False,
            "dependencyPolicy": "uv-frozen-and-npm-lock-installed-before-test"}


def snapshot_files(root, names):
    """记录Git所列源码的字节身份，包括未提交文件；不跟随指向外部的符号链接。"""
    result = {}
    for name in sorted(names):
        path = root / name
        if path.is_symlink():
            raw, kind = os.readlink(path).encode(), "symlink"
        elif path.is_file():
            raw, kind = path.read_bytes(), "file"
        else:
            result[name] = {"kind": "missing", "sha256": None}
            continue
        result[name] = {"kind": kind, "sha256": hashlib.sha256(raw).hexdigest()}
    return result


def summarize_junit(path):
    if not path.exists():
        return None
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    return {key: sum(int(suite.get(key, "0")) for suite in suites)
            for key in ("tests", "failures", "errors", "skipped")}


def collection_complete(network, junit):
    counts = network.get("collection", {}) if isinstance(network, dict) else {}
    if (set(counts) != {"collected", "selected", "deselected", "executed"}
            or any(type(value) is not int or value < 0 for value in counts.values())):
        return False
    return (counts["collected"] == counts["selected"] == counts["executed"] > 0
            and counts["deselected"] == 0 and junit is not None and junit["tests"] >= counts["executed"])


def run(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = test_environment(os.environ)
    environment = describe_environment(env)
    write_json(output / "environment.json", environment)
    command = ["uv", "run", "pytest", "tests", "-o", "addopts=", "--junitxml=" + str(output / "junit.xml"),
               "--offline-network-report=" + str(output / "network.json")]
    write_json(output / "command.json", command)
    started = time.monotonic()
    with (output / "pytest.log").open("x", encoding="utf-8") as log:
        completed = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    network = json.loads((output / "network.json").read_text()) if (output / "network.json").exists() else None
    junit = summarize_junit(output / "junit.xml")
    before = environment.get("sourceSnapshot", {})
    after = snapshot_files(ROOT, before)
    changes = [name for name in before if before[name] != after[name]]
    write_json(output / "source-after.json", after)
    passed = (completed.returncode == 0 and junit is not None and junit["tests"] > 0
              and junit["failures"] == junit["errors"] == junit["skipped"] == 0
              and network is not None and network.get("external_network_blocked") is True
              and collection_complete(network, junit) and not changes)
    result = {"schemaVersion": "whole-task-baseline-v1", "testExitCode": completed.returncode,
              "passed": passed, "seconds": time.monotonic() - started, "junit": junit,
              "network": network, "paidExecutionRequested": False,
              "scope": "完整pytest及其调用的模拟宿主合同；Python网络防护不是OS级子进程隔离",
              "sourceChangesAfterRun": changes}
    write_json(output / "result.json", result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if passed else completed.returncode or 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, help="全新证据目录，不覆盖已有运行")
    args = parser.parse_args(argv)
    return run(args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
