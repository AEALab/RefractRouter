"""本地 Judge 独立常驻进程；主路由通过可轮询 job 与它通信。"""
from __future__ import annotations

from copy import deepcopy
import multiprocessing
from queue import Empty
import time
import uuid


def _worker(requests, responses):
    from .planning_decision import LayaDecisionAdapter, LocalDecisionCapacityError
    adapters = {}
    while True:
        message = requests.get()
        job_id, operation = message["jobId"], message["operation"]
        if operation == "shutdown":
            return
        try:
            key, config = message["key"], message["config"]
            if operation == "load":
                adapters[key] = LayaDecisionAdapter(config)
                result = {"loaded": True}
            elif operation == "unload":
                adapters.pop(key, None)
                result = {"loaded": False}
            elif operation == "status":
                result = {"loaded": key in adapters}
            else:
                if key not in adapters:
                    raise ValueError("本地 Judge 尚未加载；请先在设置中加载并预热")
                adapter = adapters[key]
                if operation == "task":
                    value = adapter.decide(message["request"])
                elif operation == "escalation":
                    value = adapter.decide_escalation(message["request"])
                else:
                    raise ValueError("未知本地 Judge 操作")
                result = {"payload": value.payload, "model": value.model,
                          "coldStartMs": value.cold_start_ms, "latencyMs": value.latency_ms,
                          "usage": value.usage}
            responses.put({"jobId": job_id, "ok": True, "result": result})
        except Exception as exc:
            responses.put({"jobId": job_id, "ok": False,
                           "error": str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
                           "errorCode": "capacity" if isinstance(exc, LocalDecisionCapacityError) else "failure"})


class LocalJudgeProcess:
    """一个串行 MLX 进程；取消只让迟到结果失效，不强杀正在执行的推论。"""
    def __init__(self):
        self.context = multiprocessing.get_context("spawn")
        self.requests = self.context.Queue()
        self.responses = self.context.Queue()
        self.process = None
        self.jobs = {}
        self.cancelled = set()

    def _start(self):
        if self.process is not None and self.process.is_alive():
            return
        if self.process is not None and self.process.exitcode is not None:
            raise ValueError("本地 Judge 进程已退出；当前任务不会自动重发")
        self.process = self.context.Process(target=_worker, args=(self.requests, self.responses), daemon=True)
        self.process.start()

    def submit(self, operation, key, config, request=None):
        self._start()
        job_id = uuid.uuid4().hex
        self.jobs[job_id] = {"status": "pending", "submittedAt": time.monotonic()}
        self.requests.put({"jobId": job_id, "operation": operation, "key": key,
                           "config": deepcopy(config), "request": deepcopy(request)})
        return job_id

    def _drain(self):
        while True:
            try:
                row = self.responses.get_nowait()
            except Empty:
                break
            job_id = row["jobId"]
            if job_id in self.cancelled:
                self.jobs[job_id] = {"status": "cancelled"}
            elif row["ok"]:
                self.jobs[job_id] = {"status": "completed", "result": row["result"]}
            else:
                self.jobs[job_id] = {"status": "failed", "error": row["error"],
                                     "errorCode": row.get("errorCode", "failure")}

    def poll(self, job_id):
        self._drain()
        if self.process is not None and not self.process.is_alive() and self.jobs.get(job_id, {}).get("status") == "pending":
            self.jobs[job_id] = {"status": "failed", "error": "本地 Judge 进程异常退出"}
        if job_id not in self.jobs:
            raise ValueError("未知本地 Judge job")
        return deepcopy(self.jobs[job_id])

    def cancel(self, job_id):
        if job_id in self.jobs and self.jobs[job_id]["status"] == "pending":
            self.cancelled.add(job_id)
            self.jobs[job_id] = {"status": "cancelled"}

    def call(self, operation, key, config, *, timeout_ms=30000):
        job_id = self.submit(operation, key, config)
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            row = self.poll(job_id)
            if row["status"] == "completed":
                return row["result"]
            if row["status"] == "failed":
                raise ValueError(row["error"])
            time.sleep(.02)
        self.cancel(job_id)
        raise ValueError("本地 Judge 操作超时")

    def close(self):
        if self.process is not None and self.process.is_alive():
            self.requests.put({"jobId": uuid.uuid4().hex, "operation": "shutdown"})
            self.process.join(timeout=2)
            if self.process.is_alive():
                self.process.terminate()
