"""在已安装 wheel 中验收标准HTTP接口；上游仅为本机固定夹具。"""
import argparse
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import refractrouter.model_gateway as module

TEXT = '中文🦀🚀👩🏽\u200d💻e\u0301'
PRIVATE = '仅用于同源续接的夹具思考'


def validate(workspace):
    source = Path(__file__).resolve().parents[1] / 'src'
    if Path(module.__file__).resolve().is_relative_to(source):
        raise ValueError('本验收必须使用源码目录外实际安装的wheel')
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            seen.append(body)
            rid = 'fixture-' + str(len(seen))
            content = TEXT
            tools = []
            if body['messages'][-1]['content'] == '工具探针':
                content = '准备读取'
                tools = [{'id': 'tool-' + str(len(seen)), 'type': 'function', 'function': {
                    'name': 'read', 'arguments': json.dumps({'path': TEXT + '.txt'}, ensure_ascii=False)}}]
            elif body.get('response_format'):
                content = json.dumps({'result': TEXT}, ensure_ascii=False)
            message = {'role': 'assistant', 'content': content, 'reasoning_content': PRIVATE,
                       **({'tool_calls': tools} if tools else {})}
            usage = {'prompt_tokens': 80, 'completion_tokens': 24, 'total_tokens': 104,
                     'prompt_tokens_details': {'cached_tokens': 20},
                     'completion_tokens_details': {'reasoning_tokens': 8}}
            finish = 'tool_calls' if tools else 'stop'
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream' if body['stream'] else 'application/json')
            self.end_headers()
            if body['stream']:
                for char in content:
                    frame = {'id': rid, 'choices': [{'index': 0, 'delta': {'content': char}, 'finish_reason': None}]}
                    self.wfile.write(('data: ' + json.dumps(frame, ensure_ascii=False) + '\n\n').encode())
                for frame in ({'id': rid, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]},
                              {'id': rid, 'choices': [], 'usage': usage}):
                    self.wfile.write(('data: ' + json.dumps(frame) + '\n\n').encode())
                self.wfile.write(b'data: [DONE]\n\n')
            else:
                self.wfile.write(json.dumps({'id': rid, 'choices': [{'message': message, 'finish_reason': finish}],
                                             'usage': usage}, ensure_ascii=False).encode())
    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    Thread(target=upstream.serve_forever, daemon=True).start()
    features = ('jsonObject', 'jsonSchema', 'strictTools', 'toolChoice', 'parallelToolCalls', 'promptCacheKey')
    planning = {'schemaVersion': 'refractagent-planning-v8', 'enabled': True, 'defaultStrategy': 'static',
        'billingUnit': 'CNY', 'maxProductionCostByUnit': {'CNY': 1}, 'maxCalls': 10,
        'roles': {'efficient': 'small', 'capable': 'large'},
        'models': [{'id': key, 'provider': 'fixture', 'model': key, 'deployment': 'local',
            'contextWindow': 16384, 'maxOutputTokens': 1024, 'billingUnit': 'CNY',
            'inputPer1k': .001, 'cachedInputPer1k': .0002, 'outputPer1k': .002,
            'capabilities': {'toolCalling': 'verified', 'requestFeatures': {f: 'verified' for f in features}}}
            for key in ('small', 'large')]}
    gateway = module.ModelGateway({'schemaVersion': module.GATEWAY_CONFIG_V2, 'planningRouting': planning,
        'providers': {'fixture': {'baseURL': f'http://127.0.0.1:{upstream.server_port}/v1'}}},
        Path(workspace) / 'protocol-gateway-runs')
    server = module.create_server(gateway, port=0)
    Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'
    def post(path, value):
        with urlopen(Request(base + path, data=json.dumps(value, ensure_ascii=False).encode(),
                             headers={'Content-Type': 'application/json'}), timeout=10) as response:
            return response.read()
    try:
        initial = {'model': 'refract/static', 'store': False, 'input': [{'role': 'user', 'content': '工具探针'}],
            'tools': [{'type': 'function', 'name': 'read', 'strict': True,
                       'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}}}}]}
        first = json.loads(post('/v1/responses', initial))
        assert PRIVATE not in json.dumps(first, ensure_ascii=False)
        assert first['usage']['input_tokens_details'] == {'cached_tokens': 20}
        assert first['usage']['output_tokens_details'] == {'reasoning_tokens': 8}
        call = next(v for v in first['output'] if v['type'] == 'function_call')
        assert json.loads(call['arguments'])['path'] == TEXT + '.txt'
        follow = {**initial, 'input': initial['input'] + first['output'] + [
            {'type': 'function_call_output', 'call_id': call['call_id'], 'output': '宿主固定结果'}]}
        second = json.loads(post('/v1/responses', follow))
        assert second['output'][0]['content'][0]['text'] == TEXT
        assert seen[1]['messages'][-2]['reasoning_content'] == PRIVATE
        schema = {'type': 'json_schema', 'json_schema': {'name': 'result', 'strict': True,
                  'schema': {'type': 'object', 'properties': {'result': {'type': 'string'}}}}}
        chat = {'model': 'refract/static', 'messages': [{'role': 'user', 'content': 'JSON探针'}], 'response_format': schema}
        third = json.loads(post('/v1/chat/completions', chat))
        assert json.loads(third['choices'][0]['message']['content'])['result'] == TEXT
        assert seen[-1]['response_format'] == schema
        assert third['usage']['completion_tokens_details'] == {'reasoning_tokens': 8}
        wire = post('/v1/chat/completions', {'model': 'refract/static', 'stream': True,
            'messages': [{'role': 'user', 'content': '流式探针'}], 'stream_options': {'include_usage': True}})
        assert PRIVATE.encode() not in wire and b'[DONE]' in wire
        chunks = [json.loads(line[6:]) for line in wire.decode().splitlines()
                  if line.startswith('data: ') and line != 'data: [DONE]']
        assert ''.join(c.get('choices', [{}])[0].get('delta', {}).get('content', '')
                       for c in chunks if c.get('choices')) == TEXT
        usage = next(c['usage'] for c in chunks if c.get('usage'))
        assert usage['prompt_tokens_details'] == {'cached_tokens': 20}
        assert usage['completion_tokens_details'] == {'reasoning_tokens': 8}
        gateway.planning['models'][1]['capabilities']['requestFeatures']['jsonSchema'] = 'unknown'
        rejected = {**deepcopy(chat), 'model': 'refract/stage', 'messages': [{'role': 'user', 'content': '拒绝探针'}]}
        try:
            post('/v1/chat/completions', rejected)
        except HTTPError as error:
            assert error.code == 400
            error.close()
        else:
            raise AssertionError('未验收的可能执行候选不应派发')
        assert len(seen) == 4
        return {'status': 'pass', 'scope': 'installed-wheel-http-gateway-v2', 'paid_model_calls': 0,
                'upstream_fixture_calls': len(seen), 'tool_reasoning_roundtrip': True,
                'cache_and_reasoning_details': True, 'unicode_sse': True, 'all_candidate_rejection': True,
                'actual_provider_compatibility_proven': False}
    finally:
        server.shutdown(); server.server_close()
        upstream.shutdown(); upstream.server_close(); gateway.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.workspace), ensure_ascii=False))


if __name__ == '__main__':
    main()
