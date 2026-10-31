"""原生上限通过实际本机HTTP与SSE，未使用真实模型。"""
from scripts.validate_native_output_budget_install import validate


def test_native_answer_reasoning_total_output_and_cancellation_over_http(tmp_path):
    assert validate(tmp_path,require_installed=False)['status']=='pass'
