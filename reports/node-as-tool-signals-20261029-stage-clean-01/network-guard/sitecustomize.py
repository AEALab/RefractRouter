import socket
from pathlib import Path
def deny(*args, **kwargs):
    Path("/Users/chun-hsianglee/.codex/worktrees/planning-routing-research/RefractRouter/reports/node-as-tool-signals-20261029-stage-clean-01/network-guard/attempted").write_text('网络访问被拒绝')
    raise RuntimeError('离线验收禁止网络调用')
socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.getaddrinfo = deny
from refractrouter.schemas import TaskDAG
def forbid_dag(*args, **kwargs):
    Path("/Users/chun-hsianglee/.codex/worktrees/planning-routing-research/RefractRouter/reports/node-as-tool-signals-20261029-stage-clean-01/network-guard/dag-attempted").write_text('禁止创建 DAG')
    raise RuntimeError('本验收禁止创建 DAG')
TaskDAG.__init__ = forbid_dag
Path("/Users/chun-hsianglee/.codex/worktrees/planning-routing-research/RefractRouter/reports/node-as-tool-signals-20261029-stage-clean-01/network-guard/ready").write_text('socket-dns-dag-guards-active')
