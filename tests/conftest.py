"""所有确定性测试默认加载网络防护；模型接口只允许模拟或回环服务器。"""

pytest_plugins = ("tests.offline_network_guard",)
