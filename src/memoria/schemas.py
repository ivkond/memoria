from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolMessage(BaseModel):
    role: str = Field(description="Message role, e.g. user/assistant/system.")
    content: str = Field(description="Message content.")


class HealthComponent(BaseModel):
    ok: bool
    detail: str


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, HealthComponent]


class DeleteEntitiesResponse(BaseModel):
    user_id: str
    detail: str
    result: dict[str, Any]

