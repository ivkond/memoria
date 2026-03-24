from __future__ import annotations

from typing import Any, Callable, Protocol, TypeVar

from mem0 import Memory

from memoria.schemas import DeleteEntitiesResponse
from memoria.settings import Settings

T = TypeVar("T")


class MemoryAdapter(Protocol):
    def add_memory(
        self,
        messages: list[dict[str, Any]],
        *,
        user_id: str,
        metadata: dict[str, Any] | None = None,
        infer: bool = True,
        memory_type: str | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]: ...

    def search_memories(
        self,
        query: str,
        *,
        user_id: str,
        limit: int = 20,
        filters: dict[str, Any] | None = None,
        threshold: float | None = None,
        rerank: bool = True,
    ) -> dict[str, Any]: ...

    def get_memory(self, memory_id: str) -> dict[str, Any] | None: ...

    def get_memories(
        self,
        *,
        user_id: str,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def update_memory(self, memory_id: str, data: str) -> dict[str, Any]: ...

    def delete_memory(self, memory_id: str) -> dict[str, Any]: ...

    def delete_all_memories(self, *, user_id: str) -> dict[str, Any]: ...

    def list_entities(self, *, user_id: str, limit: int = 100) -> dict[str, Any]: ...

    def delete_entities(self, *, user_id: str) -> DeleteEntitiesResponse: ...


class Mem0Adapter:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._memory: Memory | None = None

    @property
    def memory(self) -> Memory:
        if self._memory is None:
            self._memory = Memory.from_config(self._build_config())
        return self._memory

    def _run(self, operation: Callable[[], T]) -> T:
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001
            if exc.__class__.__name__ == "APIConnectionError":
                raise RuntimeError(
                    "Cannot reach configured LLM/embedder endpoint for mem0. "
                    f"Check MEMORIA_MEM0_LLM_BASE_URL={self._settings.mem0_llm_base_url} "
                    f"and MEMORIA_MEM0_EMBEDDER_BASE_URL={self._settings.mem0_embedder_base_url}. "
                    "If running in Docker on Linux and using host service, add "
                    "`extra_hosts: [\"host.docker.internal:host-gateway\"]`."
                ) from exc
            raise

    def _build_config(self) -> dict[str, Any]:
        settings = self._settings

        if settings.qdrant_url:
            qdrant_config: dict[str, Any] = {
                "url": settings.qdrant_url,
                "collection_name": settings.qdrant_collection_name,
                "embedding_model_dims": settings.qdrant_embedding_dims,
                "on_disk": settings.qdrant_on_disk,
            }
            if settings.qdrant_api_key:
                qdrant_config["api_key"] = settings.qdrant_api_key
        else:
            qdrant_config = {
                "host": settings.qdrant_host,
                "port": settings.qdrant_port,
                "collection_name": settings.qdrant_collection_name,
                "embedding_model_dims": settings.qdrant_embedding_dims,
                "on_disk": settings.qdrant_on_disk,
            }

        llm_config: dict[str, Any] = {
            "model": settings.mem0_llm_model,
            "api_key": settings.mem0_llm_api_key or settings.mem0_api_key,
        }
        if settings.mem0_llm_provider == "vllm":
            llm_config["vllm_base_url"] = settings.mem0_llm_base_url
        else:
            llm_config["openai_base_url"] = settings.mem0_llm_base_url

        embedder_config: dict[str, Any] = {
            "model": settings.mem0_embedder_model,
            "api_key": settings.mem0_embedder_api_key or settings.mem0_api_key,
            "openai_base_url": settings.mem0_embedder_base_url,
        }

        config: dict[str, Any] = {
            "version": settings.mem0_version,
            "history_db_path": settings.mem0_history_db_path,
            "vector_store": {
                "provider": "qdrant",
                "config": qdrant_config,
            },
            "llm": {
                "provider": settings.mem0_llm_provider,
                "config": llm_config,
            },
            "embedder": {
                "provider": settings.mem0_embedder_provider,
                "config": embedder_config,
            },
        }

        if settings.mem0_enable_graph:
            if not settings.mem0_graph_url or not settings.mem0_graph_username or not settings.mem0_graph_password:
                raise ValueError(
                    "Graph memory is enabled, but MemGraph credentials are incomplete. "
                    "Set MEMORIA_MEM0_GRAPH_URL, MEMORIA_MEM0_GRAPH_USERNAME, "
                    "and MEMORIA_MEM0_GRAPH_PASSWORD."
                )

            graph_config: dict[str, Any] = {
                "provider": settings.mem0_graph_provider,
                "config": {
                    "url": settings.mem0_graph_url,
                    "username": settings.mem0_graph_username,
                    "password": settings.mem0_graph_password,
                },
            }
            config["graph_store"] = graph_config

        return config

    def add_memory(
        self,
        messages: list[dict[str, Any]],
        *,
        user_id: str,
        metadata: dict[str, Any] | None = None,
        infer: bool = True,
        memory_type: str | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        return self._run(
            lambda: self.memory.add(
                messages,
                user_id=user_id,
                metadata=metadata,
                infer=infer,
                memory_type=memory_type,
                prompt=prompt,
            )
        )

    def search_memories(
        self,
        query: str,
        *,
        user_id: str,
        limit: int = 20,
        filters: dict[str, Any] | None = None,
        threshold: float | None = None,
        rerank: bool = True,
    ) -> dict[str, Any]:
        return self._run(
            lambda: self.memory.search(
                query=query,
                user_id=user_id,
                limit=limit,
                filters=filters,
                threshold=threshold,
                rerank=rerank,
            )
        )

    def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        return self._run(lambda: self.memory.get(memory_id))

    def get_memories(
        self,
        *,
        user_id: str,
        limit: int = 100,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._run(
            lambda: self.memory.get_all(
                user_id=user_id,
                limit=limit,
                filters=filters,
            )
        )

    def update_memory(self, memory_id: str, data: str) -> dict[str, Any]:
        return self._run(lambda: self.memory.update(memory_id=memory_id, data=data))

    def delete_memory(self, memory_id: str) -> dict[str, Any]:
        return self._run(lambda: self.memory.delete(memory_id=memory_id))

    def delete_all_memories(self, *, user_id: str) -> dict[str, Any]:
        return self._run(lambda: self.memory.delete_all(user_id=user_id))

    def list_entities(self, *, user_id: str, limit: int = 100) -> dict[str, Any]:
        response = self._run(lambda: self.memory.get_all(user_id=user_id, limit=limit))
        relations = response.get("relations", [])
        return {
            "user_id": user_id,
            "relations": relations,
            "supported": bool(relations),
            "detail": "Relations are returned only when graph_store is enabled in mem0.",
        }

    def delete_entities(self, *, user_id: str) -> DeleteEntitiesResponse:
        result = self._run(lambda: self.memory.delete_all(user_id=user_id))
        return DeleteEntitiesResponse(
            user_id=user_id,
            detail=(
                "mem0 OSS SDK does not expose a dedicated delete_entities method; "
                "the server maps delete_entities to delete_all_memories for the same user."
            ),
            result=result,
        )
