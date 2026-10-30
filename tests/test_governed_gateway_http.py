"""从标准HTTP请求验收治理链路；上游仅使用本机固定回执。"""
from scripts.validate_governed_gateway_install import validate


def test_http_trial_rollback_version_observation_and_restart(tmp_path):
    result=validate(tmp_path,require_installed=False)
    assert result['status']=='pass' and result['upstream_fixture_calls']==4
    assert result['paid_model_calls']==0 and not result['actual_strategy_benefit_qualified']
