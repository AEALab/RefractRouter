"""安装夹具遵守Linux沙箱的临时目录可见范围，不改产品权限。"""
from pathlib import Path

from scripts.validate_refractagent_install import isolated_environment


def test_uv_interpreter_and_entrypoint_live_under_bound_workspace():
    base = Path('/tmp/fixture-install')
    workspace = base / 'workspace'
    inherited = {'PATH': '/usr/bin', 'API_KEY': 'secret', 'PYTHONPATH': '/old-source',
                 'VIRTUAL_ENV': '/old-venv'}
    env = isolated_environment(base, workspace, inherited)
    # bwrap tmpfs隐藏/tmp兄弟目录，仅显式绑定workspace；两项须在该范围内。
    assert Path(env['UV_TOOL_DIR']).is_relative_to(workspace)
    assert Path(env['UV_TOOL_BIN_DIR']).is_relative_to(workspace)
    assert not Path(env['UV_TOOL_DIR']).is_relative_to(base / 'tools')
    assert env['DSH_HOME'] == str(base / 'dsh')
    assert env['PATH'] == inherited['PATH']
    assert not {'API_KEY', 'PYTHONPATH', 'VIRTUAL_ENV'} & env.keys()
    assert inherited['API_KEY'] == 'secret'  # 不修改调用方环境。
