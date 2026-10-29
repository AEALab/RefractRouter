"""pytest 进程的外网阻断与可审计计数，不影响产品传输实现。

允许回环模拟服务器。防护范围仅为本 Python 进程的 socket/DNS 接口；
Node、独立子进程及宿主工具须使用自己的模拟合同，不能宣称 OS 级断网。
"""
import ipaddress
import json
from pathlib import Path
import socket

import pytest


def is_loopback(host):
    if isinstance(host, bytes):
        try:
            host = host.decode("ascii")
        except UnicodeDecodeError:
            return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError):
        return False


class NetworkGuard:
    def __init__(self):
        self.originals = []
        self.counts = {"allowed_loopback": 0, "blocked_external": 0}

    def check(self, host):
        if not is_loopback(host):
            self.counts["blocked_external"] += 1
            raise RuntimeError("离线测试禁止外部网络与 DNS")
        self.counts["allowed_loopback"] += 1

    def replace(self, obj, name, replacement):
        self.originals.append((obj, name, getattr(obj, name)))
        setattr(obj, name, replacement)

    def install(self):
        if self.originals:
            raise RuntimeError("网络防护不能重复安装")
        resolve = socket.getaddrinfo

        def getaddrinfo(host, *args, **kwargs):
            if host is not None:  # None 仅用于本地监听地址解析。
                self.check(host)
            return resolve(host, *args, **kwargs)

        self.replace(socket, "getaddrinfo", getaddrinfo)
        for name in ("gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
            original = getattr(socket, name)

            def lookup(host, *args, _original=original, **kwargs):
                self.check(host)
                return _original(host, *args, **kwargs)

            self.replace(socket, name, lookup)
        original_nameinfo = socket.getnameinfo

        def getnameinfo(address, flags):
            self.check(address[0])
            # 数值地址无需反查；回环地址同样禁止意外反向 DNS。
            return original_nameinfo(address, flags | socket.NI_NUMERICHOST)

        self.replace(socket, "getnameinfo", getnameinfo)
        for name in ("connect", "connect_ex", "sendto", "sendmsg"):
            if not hasattr(socket.socket, name):
                continue
            original = getattr(socket.socket, name)

            def guarded(sock, *args, _name=name, _original=original, **kwargs):
                if sock.family in (socket.AF_INET, socket.AF_INET6):
                    if _name == "sendmsg":
                        address = kwargs.get("address", args[3] if len(args) > 3 else None)
                    else:
                        address = args[-1] if _name == "sendto" else args[0]
                    if address is not None:
                        self.check(address[0])
                return _original(sock, *args, **kwargs)

            self.replace(socket.socket, name, guarded)

    def restore(self):
        for obj, name, original in reversed(self.originals):
            setattr(obj, name, original)
        self.originals.clear()


def pytest_addoption(parser):
    parser.addoption("--offline-network-report", help="在新文件写入本进程网络防护计数")


def pytest_configure(config):
    guard = NetworkGuard()
    guard.install()
    config._offline_network_guard = guard


def pytest_unconfigure(config):
    guard = getattr(config, "_offline_network_guard", None)
    if guard is None:
        return
    guard.restore()
    target = config.getoption("--offline-network-report")
    if target:
        with Path(target).open("x", encoding="utf-8") as stream:
            json.dump({"schema_version": "pytest-network-guard-v1", "external_network_blocked": True,
                       "scope": "pytest-python-process", "subprocess_network_isolated": False,
                       **guard.counts}, stream, ensure_ascii=False, indent=2)
            stream.write("\n")


@pytest.fixture
def offline_guard_active(request):
    assert hasattr(request.config, "_offline_network_guard"), "缺少默认离线网络防护"
    return request.config._offline_network_guard
