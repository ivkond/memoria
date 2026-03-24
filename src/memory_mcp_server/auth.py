from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable

from fastmcp import Context
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import Middleware
from fastmcp.server.middleware.middleware import MiddlewareContext

USER_ID_STATE_KEY = "memory_mcp_user_id"


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class UserHeaderMiddleware(Middleware):
    def __init__(self, header_name: str):
        self._header_name = header_name.lower()

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: Callable[[MiddlewareContext[Any]], Awaitable[Any]],
    ) -> Any:
        request = get_http_request()
        user_id = request.headers.get(self._header_name)
        if user_id is None or not user_id.strip():
            raise ValueError(
                f"Missing required header `{self._header_name}`. "
                "Pass this header in MCP server connection settings."
            )

        if context.fastmcp_context is not None:
            await _maybe_await(context.fastmcp_context.set_state(USER_ID_STATE_KEY, user_id.strip()))

        return await call_next(context)


async def require_user_id(ctx: Context, header_name: str) -> str:
    user_id = await _maybe_await(ctx.get_state(USER_ID_STATE_KEY))
    if isinstance(user_id, str) and user_id.strip():
        return user_id.strip()

    request = get_http_request()
    fallback = request.headers.get(header_name.lower())
    if fallback and fallback.strip():
        return fallback.strip()

    raise ValueError(
        f"Missing required header `{header_name}`. "
        "Pass this header in MCP server connection settings."
    )
