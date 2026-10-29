import socket
from pathlib import Path
def deny(*args, **kwargs):
    Path("/Users/chun-hsianglee/.codex/worktrees/planning-routing-research/RefractRouter/reports/node-as-tool-20261029-stage-01/network-guard/attempted").write_text('网络访问被拒绝')
    raise RuntimeError('离线验收禁止网络调用')
socket.socket.connect = deny
socket.socket.connect_ex = deny
