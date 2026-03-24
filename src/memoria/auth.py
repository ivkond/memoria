from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable

from fastmcp import Context
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import Middleware
from fastmcp.server.middleware.middleware import MiddlewareContext

USER_ID_STATE_KEY = "memory_mcp_user_id"
_MISSING_SESSION_MESSAGE = "session_id is not available because no session exists"


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _is_missing_session_error(error: RuntimeError) -> bool:
    return _MISSING_SESSION_MESSAGE in str(error)


async def _get_user_id_from_state(ctx: Any) -> Any:
    try:
        return await _maybe_await(ctx.get_state(USER_ID_STATE_KEY))
    except RuntimeError as error:
        if _is_missing_session_error(error):
            return None
        raise


async def _store_user_id_in_state(ctx: Any, user_id: str) -> None:
    try:
        await _maybe_await(ctx.set_state(USER_ID_STATE_KEY, user_id))
    except RuntimeError as error:
        if not _is_missing_session_error(error):
            raise


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
            await _store_user_id_in_state(context.fastmcp_context, user_id.strip())

        return await call_next(context)


async def require_user_id(ctx: Context, header_name: str) -> str:
    user_id = await _get_user_id_from_state(ctx)
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
