from __future__ import annotations

import asyncio

import pytest

import memoria.server as server_module
from memoria.settings import Settings


@pytest.mark.asyncio
async def test_require_tool_user_id_raises_without_context() -> None:
    with pytest.raises(ValueError, match=server_module.TOOL_CONTEXT_REQUIRED_MESSAGE):
        await server_module._require_tool_user_id(None, "x-user-id")


@pytest.mark.asyncio
async def test_require_tool_user_id_delegates_to_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_require_user_id(
        ctx: object,
        header_name: str,
        *,
        allow_header_fallback: bool = True,
    ) -> str:
        await asyncio.sleep(0)
        assert ctx == "ctx"
        assert header_name == "x-user-id"
        assert allow_header_fallback is True
        return "user-1"

    monkeypatch.setattr("memoria.server.require_user_id", fake_require_user_id)

    assert await server_module._require_tool_user_id("ctx", "x-user-id") == "user-1"


@pytest.mark.asyncio
async def test_require_tool_user_id_disables_header_fallback_in_oidc(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_require_user_id(
        ctx: object,
        header_name: str,
        *,
        allow_header_fallback: bool = True,
    ) -> str:
        await asyncio.sleep(0)
        assert ctx == "ctx"
        assert header_name == "x-user-id"
        assert allow_header_fallback is False
        return "user-from-token"

    monkeypatch.setattr("memoria.server.require_user_id", fake_require_user_id)

    result = await server_module._require_tool_user_id("ctx", "x-user-id", allow_header_fallback=False)
    assert result == "user-from-token"


def test_build_middlewares_uses_legacy_header_mode() -> None:
    settings = Settings(auth_mode="legacy_header")
    middlewares = server_module._build_middlewares(settings)
    assert len(middlewares) == 1
    assert type(middlewares[0]).__name__ == "UserHeaderMiddleware"


def test_build_middlewares_uses_oidc_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeValidator:
        def __init__(self, config: object) -> None:
            self._config = config

    monkeypatch.setattr("memoria.server.OidcTokenValidator", FakeValidator)
    settings = Settings(
        auth_mode="oidc",
        oidc_issuer_url="http://keycloak:8080/realms/memoria",
        oidc_audience="memoria-mcp",
    )
    middlewares = server_module._build_middlewares(settings)
    assert len(middlewares) == 1
    assert type(middlewares[0]).__name__ == "OidcBearerMiddleware"


def test_memory_id_field_uses_shared_description() -> None:
    field = server_module._memory_id_field()
    assert field.description == server_module.MEMORY_ID_DESCRIPTION
