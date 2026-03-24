from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Context, FastMCP
from fastmcp.server.middleware.middleware import MiddlewareContext
from starlette.requests import Request

from memory_mcp_server.auth import USER_ID_STATE_KEY, UserHeaderMiddleware, require_user_id


def _request_with_headers(headers: dict[str, str]) -> Request:
    raw_headers = [(key.lower().encode("utf-8"), value.encode("utf-8")) for key, value in headers.items()]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/mcp",
        "raw_path": b"/mcp",
        "query_string": b"",
        "headers": raw_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8080),
    }
    return Request(scope)


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


class AsyncStateContext:
    def __init__(self) -> None:
        self._state: dict[str, Any] = {}

    async def set_state(self, key: str, value: Any) -> None:
        self._state[key] = value

    async def get_state(self, key: str) -> Any:
        return self._state.get(key)


@pytest.mark.asyncio
async def test_require_user_id_reads_context_state() -> None:
    context = Context(FastMCP("test"))
    await _maybe_await(context.set_state(USER_ID_STATE_KEY, "user-from-state"))
    assert await require_user_id(context, "x-user-id") == "user-from-state"


@pytest.mark.asyncio
async def test_require_user_id_reads_http_header(monkeypatch: pytest.MonkeyPatch) -> None:
    context = Context(FastMCP("test"))
    monkeypatch.setattr(
        "memory_mcp_server.auth.get_http_request",
        lambda: _request_with_headers({"x-user-id": "header-user"}),
    )

    assert await require_user_id(context, "x-user-id") == "header-user"


@pytest.mark.asyncio
async def test_require_user_id_raises_without_header(monkeypatch: pytest.MonkeyPatch) -> None:
    context = Context(FastMCP("test"))
    monkeypatch.setattr(
        "memory_mcp_server.auth.get_http_request",
        lambda: _request_with_headers({}),
    )

    with pytest.raises(ValueError, match="x-user-id"):
        await require_user_id(context, "x-user-id")


@pytest.mark.asyncio
async def test_require_user_id_supports_async_context_state() -> None:
    context = AsyncStateContext()
    await context.set_state(USER_ID_STATE_KEY, "async-user")

    assert await require_user_id(context, "x-user-id") == "async-user"


@pytest.mark.asyncio
async def test_user_header_middleware_sets_context_state(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = UserHeaderMiddleware("x-user-id")
    context = Context(FastMCP("test"))
    mw_context = MiddlewareContext(message=object(), fastmcp_context=context, method="tools/call")
    monkeypatch.setattr(
        "memory_mcp_server.auth.get_http_request",
        lambda: _request_with_headers({"x-user-id": "employee-1"}),
    )

    async def call_next(_: MiddlewareContext[object]) -> str:
        return "ok"

    result = await middleware.on_call_tool(mw_context, call_next)

    assert result == "ok"
    assert await _maybe_await(context.get_state(USER_ID_STATE_KEY)) == "employee-1"


@pytest.mark.asyncio
async def test_user_header_middleware_supports_async_context_state(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = UserHeaderMiddleware("x-user-id")
    context = AsyncStateContext()
    mw_context = MiddlewareContext(message=object(), fastmcp_context=context, method="tools/call")
    monkeypatch.setattr(
        "memory_mcp_server.auth.get_http_request",
        lambda: _request_with_headers({"x-user-id": "employee-2"}),
    )

    async def call_next(_: MiddlewareContext[object]) -> str:
        return "ok"

    result = await middleware.on_call_tool(mw_context, call_next)

    assert result == "ok"
    assert await context.get_state(USER_ID_STATE_KEY) == "employee-2"


@pytest.mark.asyncio
async def test_user_header_middleware_fails_without_header(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = UserHeaderMiddleware("x-user-id")
    context = Context(FastMCP("test"))
    mw_context = MiddlewareContext(message=object(), fastmcp_context=context, method="tools/call")
    monkeypatch.setattr(
        "memory_mcp_server.auth.get_http_request",
        lambda: _request_with_headers({}),
    )

    async def call_next(_: MiddlewareContext[object]) -> str:
        return "ok"

    with pytest.raises(ValueError, match="x-user-id"):
        await middleware.on_call_tool(mw_context, call_next)
