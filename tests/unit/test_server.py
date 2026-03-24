from __future__ import annotations

import pytest

from memoria.server import (
    MEMORY_ID_DESCRIPTION,
    TOOL_CONTEXT_REQUIRED_MESSAGE,
    _memory_id_field,
    _require_tool_user_id,
)


@pytest.mark.asyncio
async def test_require_tool_user_id_raises_without_context() -> None:
    with pytest.raises(ValueError, match=TOOL_CONTEXT_REQUIRED_MESSAGE):
        await _require_tool_user_id(None, "x-user-id")


@pytest.mark.asyncio
async def test_require_tool_user_id_delegates_to_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_require_user_id(ctx: object, header_name: str) -> str:
        assert ctx == "ctx"
        assert header_name == "x-user-id"
        return "user-1"

    monkeypatch.setattr("memoria.server.require_user_id", fake_require_user_id)

    assert await _require_tool_user_id("ctx", "x-user-id") == "user-1"


def test_memory_id_field_uses_shared_description() -> None:
    field = _memory_id_field()

    assert field.description == MEMORY_ID_DESCRIPTION
