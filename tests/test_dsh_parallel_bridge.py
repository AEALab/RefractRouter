"""验证同一宿主通道的乱序模型回执、工具回执、终止和能力协商。"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
from threading import Thread

import pytest

from refractrouter.openai_compatible import DshStdioBridge, DSH_BRIDGE_PROTOCOL, HOST_CAPABILITIES_PROTOCOL


@contextmanager
def channel():
    requests_r, requests_w = os.pipe()
    replies_r, replies_w = os.pipe()
    streams = [os.fdopen(fd, mode, buffering=1) for fd, mode in
               [(requests_r, 'r'), (requests_w, 'w'), (replies_r, 'r'), (replies_w, 'w')]]
    receive, send, read, reply = streams
    bridge = DshStdioBridge(reader=read, writer=send)
    try:
        yield bridge, receive, reply
    finally:
        bridge.close()
        for stream in streams:
            stream.close()


def respond(stream, request, **fields):
    stream.write(json.dumps({'protocol': request['protocol'], 'type': 'response',
                             'id': request['id'], **fields}) + '\n')
    stream.flush()


def test_multiple_requests_leave_before_first_reply_and_reverse_replies_match_identity():
    with channel() as (bridge, receive, reply), ThreadPoolExecutor(3) as pool:
        futures = [pool.submit(bridge.exchange, protocol, {'marker': i, 'timeout_ms': 3000})
                   for i, protocol in enumerate([DSH_BRIDGE_PROTOCOL, 'refractrouter-dsh-tool/v1', DSH_BRIDGE_PROTOCOL])]
        requests = [json.loads(receive.readline()) for _ in futures]
        assert len({r['id'] for r in requests}) == 3
        for request in reversed(requests):
            respond(reply, request, ok=True, marker=request['marker'])
        assert [future.result(4)['marker'] for future in futures] == [0, 1, 2]


def test_mismatched_reply_stops_all_inflight_requests_without_resend():
    with channel() as (bridge, receive, reply), ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(bridge.exchange, DSH_BRIDGE_PROTOCOL, {'timeout_ms': 3000}) for _ in range(2)]
        requests = [json.loads(receive.readline()) for _ in futures]
        respond(reply, {**requests[0], 'id': 'unknown'}, ok=True)
        for future in futures:
            with pytest.raises(RuntimeError, match='mismatch'):
                future.result(4)
        with pytest.raises(RuntimeError, match='stopped'):
            bridge.exchange(DSH_BRIDGE_PROTOCOL, {})
        assert bridge.request_id == 2


def test_capabilities_are_checked_before_parallel_dispatch():
    with channel() as (bridge, receive, reply):
        def host():
            request = json.loads(receive.readline())
            assert request['protocol'] == HOST_CAPABILITIES_PROTOCOL
            respond(reply, request, ok=True, capabilities={
                'multiplexModelCalls': True, 'maxParallelModelCalls': 3, 'serializedTools': True})
        thread = Thread(target=host)
        thread.start()
        assert bridge.capabilities()['maxParallelModelCalls'] == 3
        thread.join(4)
        assert not thread.is_alive()
