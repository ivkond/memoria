from __future__ import annotations

from typing import Any

from memory_mcp_server.adapter import MemoryAdapter
from memory_mcp_server.schemas import DeleteEntitiesResponse


class MemoryService:
    def __init__(self, adapter: MemoryAdapter):
        self._adapter = adapter

    def add_memory(
        self,
        *,
        user_id: str,
        text: str,
        messages: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        infer: bool = True,
        memory_type: str | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        payload_messages = messages or [{"role": "user", "content": text}]
        return self._adapter.add_memory(
            payload_messages,
            user_id=user_id,
            metadata=metadata,
            infer=infer,
            memory_type=memory_type,
            prompt=prompt,
        )

    def search_memories(
        self,
        *,
        user_id: str,
        query: str,
        limit: int = 20,
        filters: dict[str, Any] | None = None,
        threshold: float | None = None,
        rerank: bool = True,
    ) -> dict[str, Any]:
        return self._adapter.search_memories(
            query=query,
            user_id=user_id,
            limit=limit,
            filters=filters,
            threshold=threshold,
            rerank=rerank,
        )

    def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        return self._adapter.get_memory(memory_id)

    def get_memories(
        self,
        *,
        user_id: str,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._adapter.get_memories(
            user_id=user_id,
            limit=limit,
            filters=filters,
        )

    def update_memory(self, memory_id: str, data: str) -> dict[str, Any]:
        return self._adapter.update_memory(memory_id=memory_id, data=data)

    def delete_memory(self, memory_id: str) -> dict[str, Any]:
        return self._adapter.delete_memory(memory_id=memory_id)

    def delete_all_memories(self, *, user_id: str) -> dict[str, Any]:
        return self._adapter.delete_all_memories(user_id=user_id)

    def list_entities(self, *, user_id: str, limit: int = 100) -> dict[str, Any]:
        return self._adapter.list_entities(user_id=user_id, limit=limit)

    def delete_entities(self, *, user_id: str) -> DeleteEntitiesResponse:
        return self._adapter.delete_entities(user_id=user_id)

