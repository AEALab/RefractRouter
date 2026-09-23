"""规划路由 NDJSON 进程入口；不读取凭证，不自行发起网络请求。"""
import json
import sys
from .planning_runtime import PlanningRuntime, MAX_WIRE_BYTES
from .planning_config import PROTOCOL


def serve(runs_dir, input_stream=None, output_stream=None):
    runtime = PlanningRuntime(runs_dir)
    source, target = input_stream or sys.stdin, output_stream or sys.stdout
    while True:
        line = source.readline(MAX_WIRE_BYTES + 1)
        if not line:
            break
        request = {}
        try:
            if len(line.encode()) > MAX_WIRE_BYTES or not line.endswith("\n"):
                raise ValueError("规划路由消息超过上限")
            request = json.loads(line)
            if request.get("protocol") != PROTOCOL or not isinstance(request.get("id"), str):
                raise ValueError("无效规划路由协议")
            result = runtime.handle(request)
            reply = {"protocol": PROTOCOL, "id": request["id"], "ok": True, "result": result}
        except Exception as exc:
            reply = {"protocol": PROTOCOL, "id": request.get("id"), "ok": False,
                     "error": str(exc) if isinstance(exc, ValueError) else type(exc).__name__}
        target.write(json.dumps(reply, ensure_ascii=False) + "\n")
        target.flush()
    for run in runtime.runs.values():
        if run["status"] == "running":
            runtime.stop(run, "interrupted")
