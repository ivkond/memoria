from __future__ import annotations

from typing import Any

from memory_mcp_server.schemas import DeleteEntitiesResponse
from memory_mcp_server.service import MemoryService


class FakeAdapter:
    def __init__(self):
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def add_memory(self, messages, **kwargs):
        self.calls.append(("add_memory", (messages,), kwargs))
        return {"ok": True, "messages": messages, "kwargs": kwargs}

    def search_memories(self, query, **kwargs):
        self.calls.append(("search_memories", (query,), kwargs))
        return {"ok": True, "query": query, "kwargs": kwargs}

    def get_memory(self, memory_id):
        self.calls.append(("get_memory", (memory_id,), {}))
        return {"id": memory_id}

    def get_memories(self, **kwargs):
        self.calls.append(("get_memories", (), kwargs))
        return {"results": []}

    def update_memory(self, memory_id, data):
        self.calls.append(("update_memory", (memory_id, data), {}))
        return {"id": memory_id, "data": data}

    def delete_memory(self, memory_id):
        self.calls.append(("delete_memory", (memory_id,), {}))
        return {"id": memory_id, "deleted": True}

    def delete_all_memories(self, **kwargs):
        self.calls.append(("delete_all_memories", (), kwargs))
        return {"deleted": True}

    def list_entities(self, **kwargs):
        self.calls.append(("list_entities", (), kwargs))
        return {"relations": []}

    def delete_entities(self, **kwargs):
        self.calls.append(("delete_entities", (), kwargs))
        return DeleteEntitiesResponse(user_id=kwargs["user_id"], detail="mapped", result={"deleted": True})


def test_add_memory_wraps_text_when_messages_missing() -> None:
    adapter = FakeAdapter()
    service = MemoryService(adapter)

    response = service.add_memory(
        user_id="user-1",
        text="Remember my preferred language is Russian",
    )

    assert response["ok"] is True
    assert response["messages"] == [{"role": "user", "content": "Remember my preferred language is Russian"}]


def test_search_memories_is_user_scoped() -> None:
    adapter = FakeAdapter()
    service = MemoryService(adapter)

    service.search_memories(user_id="user-42", query="preferred language")
    _, _, kwargs = adapter.calls[0]

    assert kwargs["user_id"] == "user-42"


def test_delete_entities_returns_pydantic_response() -> None:
    adapter = FakeAdapter()
    service = MemoryService(adapter)

    response = service.delete_entities(user_id="employee-7")

    assert response.user_id == "employee-7"
    assert response.result["deleted"] is True

