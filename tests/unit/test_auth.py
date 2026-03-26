from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastmcp.server.middleware.middleware import MiddlewareContext
from starlette.requests import Request

from memoria.auth import (
    USER_ID_STATE_KEY,
    OidcBearerMiddleware,
    UserHeaderMiddleware,
    require_user_id,
)


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


class AsyncStateContext:
    def __init__(self) -> None:
        self._state: dict[str, Any] = {}

    async def set_state(self, key: str, value: Any) -> None:
        await asyncio.sleep(0)
        self._state[key] = value

    async def get_state(self, key: str) -> Any:
        await asyncio.sleep(0)
        return self._state.get(key)


class MissingSessionStateContext:
    async def set_state(self, key: str, value: Any) -> None:
        raise RuntimeError(
            "session_id is not available because no session exists. "
            "This typically means you're outside a request context."
        )

    async def get_state(self, key: str) -> Any:
        raise RuntimeError(
            "session_id is not available because no session exists. "
            "This typically means you're outside a request context."
        )


class FakeTokenValidator:
    def __init__(self, claims: dict[str, Any]) -> None:
        self._claims = claims

    def validate(self, token: str) -> dict[str, Any]:
        return self._claims


@pytest.mark.asyncio
async def test_require_user_id_reads_context_state() -> None:
    context = AsyncStateContext()
    await context.set_state(USER_ID_STATE_KEY, "user-from-state")
    assert await require_user_id(context, "x-user-id") == "user-from-state"


@pytest.mark.asyncio
async def test_require_user_id_reads_http_header(monkeypatch: pytest.MonkeyPatch) -> None:
    context = MissingSessionStateContext()
    monkeypatch.setattr(
        "memoria.auth.get_http_request",
        lambda: _request_with_headers({"x-user-id": "header-user"}),
    )

    assert await require_user_id(context, "x-user-id") == "header-user"


@pytest.mark.asyncio
async def test_require_user_id_raises_without_header(monkeypatch: pytest.MonkeyPatch) -> None:
    context = MissingSessionStateContext()
    monkeypatch.setattr(
        "memoria.auth.get_http_request",
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
async def test_require_user_id_falls_back_when_context_state_requires_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = MissingSessionStateContext()
    monkeypatch.setattr(
        "memoria.auth.get_http_request",
        lambda: _request_with_headers({"x-user-id": "header-user"}),
    )

    assert await require_user_id(context, "x-user-id") == "header-user"


@pytest.mark.asyncio
async def test_require_user_id_does_not_fallback_to_header_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = MissingSessionStateContext()
    monkeypatch.setattr(
        "memoria.auth.get_http_request",
        lambda: _request_with_headers({"x-user-id": "legacy-user"}),
    )
    with pytest.raises(ValueError, match="missing authenticated user"):
        await require_user_id(context, "x-user-id", allow_header_fallback=False)


@pytest.mark.asyncio
async def test_user_header_middleware_sets_context_state(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = UserHeaderMiddleware("x-user-id")
    context = AsyncStateContext()
    mw_context = MiddlewareContext(message=object(), fastmcp_context=context, method="tools/call")
    monkeypatch.setattr(
        "memoria.auth.get_http_request",
        lambda: _request_with_headers({"x-user-id": "employee-1"}),
    )

    async def call_next(_: MiddlewareContext[object]) -> str:
        await asyncio.sleep(0)
        return "ok"

    result = await middleware.on_call_tool(mw_context, call_next)

    assert result == "ok"
    assert await context.get_state(USER_ID_STATE_KEY) == "employee-1"


@pytest.mark.asyncio
async def test_user_header_middleware_supports_async_context_state(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = UserHeaderMiddleware("x-user-id")
    context = AsyncStateContext()
    mw_context = MiddlewareContext(message=object(), fastmcp_context=context, method="tools/call")
    monkeypatch.setattr(
        "memoria.auth.get_http_request",
        lambda: _request_with_headers({"x-user-id": "employee-2"}),
    )

    async def call_next(_: MiddlewareContext[object]) -> str:
        await asyncio.sleep(0)
        return "ok"

    result = await middleware.on_call_tool(mw_context, call_next)

    assert result == "ok"
    assert await context.get_state(USER_ID_STATE_KEY) == "employee-2"


@pytest.mark.asyncio
async def test_user_header_middleware_ignores_missing_session_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    middleware = UserHeaderMiddleware("x-user-id")
    context = MissingSessionStateContext()
    mw_context = MiddlewareContext(message=object(), fastmcp_context=context, method="tools/call")
    monkeypatch.setattr(
        "memoria.auth.get_http_request",
        lambda: _request_with_headers({"x-user-id": "employee-3"}),
    )

    async def call_next(_: MiddlewareContext[object]) -> str:
        await asyncio.sleep(0)
        return "ok"

    assert await middleware.on_call_tool(mw_context, call_next) == "ok"


@pytest.mark.asyncio
async def test_user_header_middleware_fails_without_header(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = UserHeaderMiddleware("x-user-id")
    context = AsyncStateContext()
    mw_context = MiddlewareContext(message=object(), fastmcp_context=context, method="tools/call")
    monkeypatch.setattr(
        "memoria.auth.get_http_request",
        lambda: _request_with_headers({}),
    )

    async def call_next(_: MiddlewareContext[object]) -> str:
        await asyncio.sleep(0)
        return "ok"

    with pytest.raises(ValueError, match="x-user-id"):
        await middleware.on_call_tool(mw_context, call_next)


@pytest.mark.asyncio
async def test_oidc_middleware_sets_user_id_from_sub(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = OidcBearerMiddleware(
        token_validator=FakeTokenValidator({"preferred_username": "alice-id"}),
        subject_claim="preferred_username",
    )
    context = AsyncStateContext()
    mw_context = MiddlewareContext(message=object(), fastmcp_context=context, method="tools/call")
    monkeypatch.setattr(
        "memoria.auth.get_http_request",
        lambda: _request_with_headers({"authorization": "Bearer token-1"}),
    )

    async def call_next(_: MiddlewareContext[object]) -> str:
        return "ok"

    result = await middleware.on_call_tool(mw_context, call_next)

    assert result == "ok"
    assert await context.get_state(USER_ID_STATE_KEY) == "alice-id"


@pytest.mark.asyncio
async def test_oidc_middleware_rejects_missing_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = OidcBearerMiddleware(token_validator=FakeTokenValidator({"sub": "alice-id"}))
    mw_context = MiddlewareContext(message=object(), fastmcp_context=AsyncStateContext(), method="tools/call")
    monkeypatch.setattr("memoria.auth.get_http_request", lambda: _request_with_headers({}))

    async def call_next(_: MiddlewareContext[object]) -> str:
        return "ok"

    with pytest.raises(ValueError, match="missing bearer token"):
        await middleware.on_call_tool(mw_context, call_next)
