"""验收助手必须约束半行回执，并清理超时或取消的祖孙进程。"""
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from scripts.validate_refractagent_install import run_process
from scripts.validate_task_shadow_worker import validate


def test_stage_fixture_crosses_real_core_process_without_real_models(tmp_path):
    result = validate(Path(sys.executable).with_name("refractagent"), tmp_path, mode="stage")
    assert result["actual_model_calls"] == ["small", "small", "large", "large", "small"]
    assert result["classification_calls"] == 0 and result["shadow_only"] is True
    assert result["modelCalls"] == 0 and result["actual_model_benefit_proven"] is False


def test_partial_response_has_deadline_and_worker_is_reaped(tmp_path):
    worker = tmp_path / "partial-worker"
    pid_file = tmp_path / "pid"
    worker.write_text("#!/usr/bin/env python3\n" +
        "import os, sys, time\nfrom pathlib import Path\n" +
        f"Path({str(pid_file)!r}).write_text(str(os.getpid()))\n" +
        "sys.stdin.readline()\nsys.stdout.write('{')\nsys.stdout.flush()\ntime.sleep(60)\n")
    worker.chmod(0o700)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="完整行回执超时"):
        validate(worker, tmp_path, response_timeout=.3)
    assert time.monotonic() - started < 5
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


@pytest.mark.parametrize("cancel,close_pipes", [(False, False), (True, False), (False, True)])
def test_outer_timeout_or_cancel_cleans_grandchild_group(tmp_path, monkeypatch, cancel, close_pipes):
    heartbeat = tmp_path / "heartbeat"
    child = ("import signal,time,os\nfrom pathlib import Path\n"
             "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
             + ("os.close(1)\nos.close(2)\n" if close_pipes else "") +
             f"p=Path({str(heartbeat)!r})\n"
             "while True:\n p.write_text(str(time.time_ns()))\n time.sleep(.02)\n")
    parent = ("import subprocess,sys,time\n" +
              f"subprocess.Popen([sys.executable,'-c',{child!r}])\n" +
              "time.sleep(60)\n")
    if cancel:
        communicate = subprocess.Popen.communicate
        first = True

        def interrupted(process, *args, **kwargs):
            nonlocal first
            if first:
                first = False
                deadline = time.monotonic() + 3
                while not heartbeat.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                raise KeyboardInterrupt
            return communicate(process, *args, **kwargs)

        monkeypatch.setattr(subprocess.Popen, "communicate", interrupted)
    expected = KeyboardInterrupt if cancel else subprocess.TimeoutExpired
    with pytest.raises(expected):
        run_process([sys.executable, "-c", parent], cwd=tmp_path, env=os.environ.copy(), timeout=.5)
    before = heartbeat.read_bytes()
    time.sleep(.1)
    assert heartbeat.read_bytes() == before
