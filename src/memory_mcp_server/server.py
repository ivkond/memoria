from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from memory_mcp_server.adapter import Mem0Adapter, MemoryAdapter
from memory_mcp_server.auth import UserHeaderMiddleware, require_user_id
from memory_mcp_server.health import HealthChecker
from memory_mcp_server.service import MemoryService
from memory_mcp_server.settings import Settings


def create_server(
    settings: Settings | None = None,
    adapter: MemoryAdapter | None = None,
    health_checker: HealthChecker | None = None,
) -> FastMCP:
    app_settings = settings or Settings()
    app_adapter = adapter or Mem0Adapter(app_settings)
    app_health = health_checker or HealthChecker(app_settings)
    service = MemoryService(app_adapter)

    mcp = FastMCP(
        "memory-mcp-server",
        instructions=(
            "Standalone MCP server for mem0-backed user memory. "
            "Every tool call requires x-user-id from a trusted upstream and scopes data to that user. "
            "The header is not authentication by itself."
        ),
        middleware=[UserHeaderMiddleware(app_settings.user_header_name)],
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        response = app_health.check()
        status_code = 200 if response.status == "ok" else 503
        return JSONResponse(status_code=status_code, content=response.model_dump())

    @mcp.tool(
        description=(
            "Store a memory for current user scope. "
            "If messages are omitted, text is wrapped into a single user message."
        )
    )
    def add_memory(
        text: str = Field(description="Natural language memory payload."),
        messages: list[dict[str, str]] | None = Field(
            default=None,
            description="Optional structured role/content message list.",
        ),
        metadata: dict[str, Any] | None = Field(
            default=None,
            description="Optional metadata attached to memory items.",
        ),
        infer: bool = Field(
            default=True,
            description="Enable mem0 inference behavior.",
        ),
        memory_type: str | None = Field(
            default=None,
            description="Optional mem0 memory type.",
        ),
        prompt: str | None = Field(
            default=None,
            description="Optional custom extraction prompt.",
        ),
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx is None:
            raise ValueError("Tool context is required.")
        user_id = require_user_id(ctx, app_settings.user_header_name)
        return service.add_memory(
            user_id=user_id,
            text=text,
            messages=messages,
            metadata=metadata,
            infer=infer,
            memory_type=memory_type,
            prompt=prompt,
        )

    @mcp.tool(description="Semantic search memories for current user.")
    def search_memories(
        query: str = Field(description="Search query."),
        limit: int = Field(default=20, ge=1, le=200),
        filters: dict[str, Any] | None = Field(default=None),
        threshold: float | None = Field(default=None),
        rerank: bool = Field(default=True),
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx is None:
            raise ValueError("Tool context is required.")
        user_id = require_user_id(ctx, app_settings.user_header_name)
        return service.search_memories(
            user_id=user_id,
            query=query,
            limit=limit,
            filters=filters,
            threshold=threshold,
            rerank=rerank,
        )

    @mcp.tool(description="Get single memory by ID.")
    def get_memory(
        memory_id: str = Field(description="Memory ID."),
        ctx: Context | None = None,
    ) -> dict[str, Any] | None:
        if ctx is None:
            raise ValueError("Tool context is required.")
        user_id = require_user_id(ctx, app_settings.user_header_name)
        return service.get_memory(user_id=user_id, memory_id=memory_id)

    @mcp.tool(description="List memories for current user.")
    def get_memories(
        limit: int = Field(default=100, ge=1, le=500),
        filters: dict[str, Any] | None = Field(default=None),
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx is None:
            raise ValueError("Tool context is required.")
        user_id = require_user_id(ctx, app_settings.user_header_name)
        return service.get_memories(user_id=user_id, limit=limit, filters=filters)

    @mcp.tool(description="Update memory text by ID.")
    def update_memory(
        memory_id: str = Field(description="Memory ID."),
        data: str = Field(description="Updated memory text."),
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx is None:
            raise ValueError("Tool context is required.")
        user_id = require_user_id(ctx, app_settings.user_header_name)
        return service.update_memory(user_id=user_id, memory_id=memory_id, data=data)

    @mcp.tool(description="Delete memory by ID.")
    def delete_memory(
        memory_id: str = Field(description="Memory ID."),
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx is None:
            raise ValueError("Tool context is required.")
        user_id = require_user_id(ctx, app_settings.user_header_name)
        return service.delete_memory(user_id=user_id, memory_id=memory_id)

    @mcp.tool(description="Delete all memories for current user.")
    def delete_all_memories(ctx: Context | None = None) -> dict[str, Any]:
        if ctx is None:
            raise ValueError("Tool context is required.")
        user_id = require_user_id(ctx, app_settings.user_header_name)
        return service.delete_all_memories(user_id=user_id)

    @mcp.tool(
        description=(
            "List graph relations for current user. "
            "Relations are available only when mem0 graph_store is enabled."
        )
    )
    def list_entities(
        limit: int = Field(default=100, ge=1, le=500),
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if ctx is None:
            raise ValueError("Tool context is required.")
        user_id = require_user_id(ctx, app_settings.user_header_name)
        return service.list_entities(user_id=user_id, limit=limit)

    @mcp.tool(
        description=(
            "Delete entities for current user. "
            "In mem0 OSS this is mapped to delete_all_memories for that user scope."
        )
    )
    def delete_entities(ctx: Context | None = None) -> dict[str, Any]:
        if ctx is None:
            raise ValueError("Tool context is required.")
        user_id = require_user_id(ctx, app_settings.user_header_name)
        response = service.delete_entities(user_id=user_id)
        return response.model_dump()

    return mcp
