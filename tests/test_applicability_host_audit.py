"""私有通信诊断不得复制凭证、任务正文或任意响应字段；不访问网络。"""
from pathlib import Path
import subprocess


def test_host_diagnostics_are_bounded_and_redact_credentials():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(['node', '--experimental-strip-types',
                    str(root/'validation/dsh/applicability_audit.test.ts')],
                   cwd=root, check=True, capture_output=True, text=True)


def test_wire_diagnostics_preserve_stream_without_recording_payload():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(['node', '--experimental-strip-types',
                    str(root/'validation/dsh/responses_wire_audit.test.ts')],
                   cwd=root, check=True, capture_output=True, text=True)
