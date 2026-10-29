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
        self.counts = {"allowed_loopback": 0, "allowed_numeric_bind": 0, "blocked_external": 0}

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

        def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
            if host is not None:  # None 仅用于本地监听地址解析。
                self.check(host)
                host = "::1" if host in ("localhost", b"localhost") and family == socket.AF_INET6 else (
                    "127.0.0.1" if host in ("localhost", b"localhost") else host)
                flags |= socket.AI_NUMERICHOST
            return resolve(host, port, family, type, proto, flags)

        self.replace(socket, "getaddrinfo", getaddrinfo)
        def numeric_host(host):
            self.check(host)
            if isinstance(host, bytes):
                host = host.decode("ascii")
            return "127.0.0.1" if host == "localhost" else str(ipaddress.ip_address(host))

        def gethostbyname(host):
            value = numeric_host(host)
            if ipaddress.ip_address(value).version != 4:
                raise socket.gaierror(socket.EAI_FAMILY, "gethostbyname仅支持IPv4")
            return value

        def gethostbyname_ex(host):
            value = gethostbyname(host)
            return ("localhost" if host in ("localhost", b"localhost") else value, [], [value])

        def gethostbyaddr(host):
            # 127.0.0.2等本地未登记地址也不得交给系统NSS/PTR解析器。
            return ("localhost", [], [numeric_host(host)])

        self.replace(socket, "gethostbyname", gethostbyname)
        self.replace(socket, "gethostbyname_ex", gethostbyname_ex)
        self.replace(socket, "gethostbyaddr", gethostbyaddr)
        original_nameinfo = socket.getnameinfo

        def getnameinfo(address, flags):
            address = (numeric_host(address[0]), *address[1:])
            # 数值地址无需反查；回环地址同样禁止意外反向 DNS。
            return original_nameinfo(address, flags | socket.NI_NUMERICHOST | socket.NI_NUMERICSERV)

        self.replace(socket, "getnameinfo", getnameinfo)

        def numeric_address(sock, address, binding=False):
            host = address[0]
            if binding:
                if host in ("", b""):
                    host = "::" if sock.family == socket.AF_INET6 else "0.0.0.0"
                elif host in ("localhost", b"localhost"):
                    host = "::1" if sock.family == socket.AF_INET6 else "127.0.0.1"
                try:
                    parsed = ipaddress.ip_address(host.decode("ascii") if isinstance(host, bytes) else host)
                except (ValueError, TypeError, UnicodeDecodeError):
                    self.counts["blocked_external"] += 1
                    raise RuntimeError("离线测试禁止绑定时触发名称解析") from None
                self.counts["allowed_numeric_bind"] += 1
            else:
                value = numeric_host(host)
                if host in ("localhost", b"localhost") and sock.family == socket.AF_INET6:
                    value = "::1"
                parsed = ipaddress.ip_address(value)
            expected = 6 if sock.family == socket.AF_INET6 else 4
            if parsed.version != expected:
                raise socket.gaierror(socket.EAI_FAMILY, "数值地址与socket地址族不符")
            return (str(parsed), *address[1:])

        for name in ("connect", "connect_ex", "sendto", "sendmsg", "bind"):
            if not hasattr(socket.socket, name):
                continue
            original = getattr(socket.socket, name)

            def guarded(sock, *args, _name=name, _original=original, **kwargs):
                if sock.family in (socket.AF_INET, socket.AF_INET6):
                    if _name == "sendmsg":
                        address = kwargs.get("address", args[3] if len(args) > 3 else None)
                        index = 3
                    else:
                        address = args[-1] if _name == "sendto" else args[0]
                        index = len(args) - 1 if _name == "sendto" else 0
                    if address is not None:
                        address = numeric_address(sock, address, binding=_name == "bind")
                        if _name == "sendmsg" and "address" in kwargs:
                            kwargs = {**kwargs, "address": address}
                        else:
                            args = (*args[:index], address, *args[index + 1:])
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
    guard.collection = CollectionAudit()
    config.pluginmanager.register(guard.collection, "refract-complete-collection")
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
                       "collection": guard.collection.snapshot(), **guard.counts},
                      stream, ensure_ascii=False, indent=2)
            stream.write("\n")


@pytest.fixture
def offline_guard_active(request):
    assert hasattr(request.config, "_offline_network_guard"), "缺少默认离线网络防护"
    return request.config._offline_network_guard


class CollectionAudit:
    """分别记录筛选前收集、筛选后选择及实际调用；子测试不冒充独立测试。"""
    def __init__(self):
        self.collected = 0
        self.deselected = 0
        self.selected = set()
        self.called = set()

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_collection_modifyitems(self, items):
        self.collected = len(items)
        yield

    def pytest_deselected(self, items):
        self.deselected += len(items)

    def pytest_collection_finish(self, session):
        self.selected = {item.nodeid for item in session.items}

    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            self.called.add(report.nodeid)

    def snapshot(self):
        return {"collected": self.collected, "selected": len(self.selected),
                "deselected": self.deselected, "executed": len(self.selected & self.called)}
