"""真实阻断接口与回环往返；没有外部数据或模型调用。"""
import socket
from threading import Thread

import pytest

from tests.offline_network_guard import NetworkGuard, is_loopback


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


def test_loopback_reverse_lookup_never_calls_system_resolver(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("不允许触达系统DNS/PTR解析器")

    monkeypatch.setattr(socket, "gethostbyaddr", forbidden)
    monkeypatch.setattr(socket, "gethostbyname", forbidden)
    guard = NetworkGuard()
    guard.install()
    try:
        assert socket.gethostbyaddr("127.0.0.2") == ("localhost", [], ["127.0.0.2"])
        assert socket.gethostbyaddr("::1") == ("localhost", [], ["::1"])
        assert socket.gethostbyname("localhost") == "127.0.0.1"
    finally:
        guard.restore()


def test_localhost_getaddrinfo_is_numeric_only(monkeypatch):
    calls = []
    reverse = []

    def resolve(host, port, family, type, proto, flags):
        calls.append((host, flags))
        return []

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(socket, "getnameinfo", lambda address, flags: reverse.append((address, flags)))
    guard = NetworkGuard()
    guard.install()
    try:
        socket.getaddrinfo("localhost", 80)
        socket.getaddrinfo("localhost", 80, socket.AF_INET6)
        assert [host for host, _ in calls] == ["127.0.0.1", "::1"]
        assert all(flags & socket.AI_NUMERICHOST for _, flags in calls)
        socket.getnameinfo(("localhost", 80), 0)
        assert reverse[0][0] == ("127.0.0.1", 80)
        assert reverse[0][1] & socket.NI_NUMERICHOST
        assert reverse[0][1] & socket.NI_NUMERICSERV
    finally:
        guard.restore()


def test_direct_socket_addresses_are_numeric_before_reaching_c_layer(monkeypatch):
    calls = []
    methods = ["connect", "connect_ex", "sendto", "bind"]
    if hasattr(socket.socket, "sendmsg"):
        methods.append("sendmsg")
    for name in methods:
        def record(sock, *args, _name=name, **kwargs):
            address = (kwargs.get("address", args[3] if len(args) > 3 else None) if _name == "sendmsg"
                       else args[-1] if _name == "sendto" else args[0])
            calls.append((sock.family, _name, address))
            return 0
        monkeypatch.setattr(socket.socket, name, record)
    guard = NetworkGuard()
    guard.install()
    try:
        for family in (socket.AF_INET, socket.AF_INET6):
            with socket.socket(family, socket.SOCK_DGRAM) as sock:
                sock.connect(("localhost", 1234))
                sock.connect_ex(("localhost", 1234))
                sock.sendto(b"not-sent", ("localhost", 1234))
                sock.bind(("localhost", 1234))
                if "sendmsg" in methods:
                    sock.sendmsg([b"not-sent"], [], 0, ("localhost", 1234))
                with pytest.raises(RuntimeError, match="名称解析"):
                    sock.bind(("external.example.test", 1234))
        assert len(calls) == 2 * len(methods)
        assert all(address[0] == ("::1" if family == socket.AF_INET6 else "127.0.0.1")
                   for family, _, address in calls)
    finally:
        guard.restore()
