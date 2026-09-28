"""Hermes 可选插件：采集终端工具事实，不修改工具执行或 Agent 循环。"""
import logging

from .client_tool_evidence import from_hermes_hook, post_to_router

logger = logging.getLogger(__name__)


def on_post_tool_call(**event):
    fact = from_hermes_hook(event)
    if fact is None:
        return
    try:
        post_to_router(fact)
    except Exception as exc:
        # Hermes 的观察钩子是 best-effort；Router 会将未送达的结果标为无法分类。
        logger.warning('RefractRouter 工具证据未送达：%s', exc)


def register(ctx):
    ctx.register_hook('post_tool_call', on_post_tool_call)
