"""真实阻断接口与回环往返；没有外部数据或模型调用。"""
import socket
from threading import Thread

import pytest

from tests.offline_network_guard import is_loopback


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", b"127.0.0.1"])
def test_loopback_addresses(host):
    assert is_loopback(host)


@pytest.mark.parametrize("host", ["127.0.0.1.evil.test", "api.example.test", "8.8.8.8",
                                 "0.0.0.0", b"\xff", None])
def test_external_or_invalid_addresses(host):
    assert not is_loopback(host)


def test_external_dns_blocked_before_resolution(offline_guard_active):
    before = offline_guard_active.counts["blocked_external"]
    for lookup in (socket.getaddrinfo, socket.gethostbyname, socket.gethostbyname_ex,
                   socket.gethostbyaddr):
        with pytest.raises(RuntimeError, match="禁止外部"):
            lookup("api.example.test", *([443] if lookup is socket.getaddrinfo else []))
    assert offline_guard_active.counts["blocked_external"] == before + 4


@pytest.mark.parametrize("method", ["connect", "connect_ex", "sendto"])
def test_direct_ip_cannot_bypass_dns_guard(offline_guard_active, method):
    with socket.socket(type=socket.SOCK_DGRAM if method == "sendto" else socket.SOCK_STREAM) as sock:
        with pytest.raises(RuntimeError, match="禁止外部"):
            if method == "sendto":
                sock.sendto(b"not-sent", ("192.0.2.1", 443))
            else:
                getattr(sock, method)(("192.0.2.1", 443))


def test_loopback_server_remains_usable(offline_guard_active):
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()

        def serve():
            with server.accept()[0] as peer:
                assert peer.recv(8) == b"fixture"
                peer.sendall(b"ok")

        thread = Thread(target=serve, daemon=True)
        thread.start()
        with socket.create_connection(server.getsockname(), timeout=2) as client:
            client.sendall(b"fixture")
            assert client.recv(2) == b"ok"
        thread.join(timeout=2)
        assert not thread.is_alive()
