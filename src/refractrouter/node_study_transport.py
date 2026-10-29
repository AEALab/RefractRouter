"""先导专用 HTTP 取证：控制采样参数，保存原始正文，不记录认证头。"""
import hashlib
import json
import os
from pathlib import Path
from threading import RLock, local

from .openai_compatible import UrllibTransport


class StudyWireTransport:
    def __init__(self, directory, *, backend=None, temperature=0, model="deepseek-v4-flash", output_tokens=384000):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.backend = backend if backend is not None else UrllibTransport()
        self.temperature, self.model, self.output_tokens = temperature, model, output_tokens
        self.lock, self.thread, self.counter = RLock(), local(), 0

    @staticmethod
    def scrub(body):
        secret = os.environ.get("CODEX_ARK_API_KEY", "").encode()
        return body.replace(secret, "[已隐藏凭证]".encode()) if secret else body

    def post(self, url, headers, body, timeout_seconds):
        self.thread.prefix = None
        payload = json.loads(body)
        if url != "https://ark.cn-beijing.volces.com/api/plan/v3/responses":
            raise ValueError("DAG 取证拒绝未冻结端点")
        if (type(payload.get("temperature")) not in (int,float)
                or payload.get("temperature") != self.temperature or payload.get("model") != self.model
                or payload.get("max_output_tokens") != self.output_tokens):
            raise ValueError("DAG 实际请求的模型、采样或输出容量与冻结控制不符")
        with self.lock:
            self.counter += 1
            prefix = self.directory / str(self.counter).zfill(3)
        request_body = self.scrub(body)
        Path(str(prefix) + "-request.json").write_bytes(request_body)
        # 唯一一次真实 HTTP 调用；本层没有重试或另行查询用量。
        response = self.backend.post(url, headers, body, timeout_seconds)
        response_body = self.scrub(response.body)
        Path(str(prefix) + "-response.json").write_bytes(response_body)
        try:
            parsed = json.loads(response.body)
        except (ValueError, UnicodeDecodeError):
            parsed = {}
        lowered = {k.lower(): v for k, v in response.headers.items()}
        receipt = {"status": response.status, "requestId": lowered.get("x-request-id"),
                   "responseId": parsed.get("id") if isinstance(parsed, dict) else None,
                   "providerReportedModel": parsed.get("model") if isinstance(parsed, dict) else None,
                   "requestSha256": hashlib.sha256(request_body).hexdigest(),
                   "responseSha256": hashlib.sha256(response_body).hexdigest()}
        Path(str(prefix) + "-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False) + "\n")
        # complete→settle 回调在同一调用线程中执行。线程局部绑定不会混淆并发节点的响应次序。
        self.thread.prefix = "wire/" + prefix.name
        return response

    def current_prefix(self):
        prefix = getattr(self.thread, "prefix", None)
        if prefix is None:
            raise ValueError("当前调用线程缺少完整 HTTP 归档绑定")
        return prefix
