"""仅通过 127.0.0.1 复现等待时间与错误来源；不访问供应商，不使用凭据。"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import time
from urllib.request import ProxyHandler, build_opener
from unittest.mock import patch

from refractrouter.openai_compatible import TransportFailure, UrllibTransport


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', '0')))
        if self.path == '/headers':
            time.sleep(.2)
        self.send_response(408 if self.path == '/http408' else 200)
        self.send_header('Content-Length', '2')
        self.send_header('X-Request-ID', 'local-test')
        self.end_headers()
        if self.path == '/body':
            time.sleep(.2)
        try:
            self.wfile.write(b'{}')
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    records = []
    try:
        # 明确绕过环境代理；只允许此本机服务地址。
        with patch('refractrouter.openai_compatible.urlopen', build_opener(ProxyHandler({})).open):
            for path, timeout in [('headers', .05), ('headers', 1), ('body', .05), ('http408', 1)]:
                started = time.perf_counter()
                record = {'scenario': path, 'timeout_seconds': timeout}
                try:
                    result = UrllibTransport().post(
                        f'http://127.0.0.1:{server.server_port}/{path}', {}, b'{}', timeout)
                    record.update(http_status=result.status, diagnostics=dict(result.diagnostics))
                except TransportFailure as exc:
                    record.update(failure_type=exc.failure_type, diagnostics=exc.diagnostics)
                record['latency_ms'] = round((time.perf_counter() - started) * 1000)
                records.append(record)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert records[0]['failure_type'] == records[2]['failure_type'] == 'timeout'
    assert records[0]['diagnostics']['phase'] == 'connect-or-response-headers'
    assert records[1]['http_status'] == 200
    assert records[2]['diagnostics']['phase'] == 'response-body'
    assert records[2]['diagnostics']['http_status'] == 200
    assert records[3]['http_status'] == 408
    print(json.dumps({'actual_model_calls': 0, 'records': records}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
