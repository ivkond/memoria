from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Protocol, TypeVar

import httpx
from mem0 import Memory
from openai import OpenAI

from memoria.schemas import DeleteEntitiesResponse
from memoria.settings import Settings

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")
EMBEDDER_BASE_URL_KEYS = {
    "openai": "openai_base_url",
    "vllm": "openai_base_url",
    "ollama": "ollama_base_url",
    "lmstudio": "lmstudio_base_url",
}


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
        self._memory_lock = threading.Lock()

    @property
    def memory(self) -> Memory:
        memory = self._memory
        if memory is None:
            with self._memory_lock:
                if self._memory is None:
                    instance = Memory.from_config(self._build_config())
                    if not self._settings.ssl_verify:
                        self._apply_ssl_override(instance, verify=self._settings.ssl_verify)
                    self._memory = instance
                memory = self._memory
        if memory is None:
            raise RuntimeError("mem0 memory adapter initialization failed")
        return memory

    @staticmethod
    def _apply_ssl_override(memory: Memory, *, verify: bool) -> None:
        http_client = httpx.Client(verify=verify)
        for attr_name in ("llm", "embedding_model"):
            component = getattr(memory, attr_name, None)
            if component is None:
                continue
            client = getattr(component, "client", None)
            if not isinstance(client, OpenAI):
                continue
            component.client = OpenAI(
                api_key=client.api_key,
                base_url=str(client.base_url),
                http_client=http_client,
            )
            LOGGER.info("Patched %s OpenAI client with ssl verify=%s", attr_name, verify)

    @staticmethod
    def _is_connectivity_error(error: Exception) -> bool:
        if isinstance(error, (httpx.ConnectError, httpx.TimeoutException)):
            return True
        if error.__class__.__name__ == "APIConnectionError":
            return True
        nested_error = error.__cause__ or error.__context__
        return isinstance(nested_error, Exception) and Mem0Adapter._is_connectivity_error(nested_error)

    def _run(self, operation: Callable[[], T]) -> T:
        try:
            return operation()
        except Exception as exc:  # noqa: BLE001
            if self._is_connectivity_error(exc):
                raise RuntimeError(
                    "Cannot reach configured LLM/embedder endpoint for mem0. "
                    f"Check MEMORIA_MEM0_LLM_BASE_URL={self._settings.mem0_llm_base_url} "
                    f"and MEMORIA_MEM0_EMBEDDER_BASE_URL={self._settings.mem0_embedder_base_url}. "
                    "If running in Docker on Linux and using host service, add "
                    "`extra_hosts: [\"host.docker.internal:host-gateway\"]`."
                ) from exc
            raise

    def _build_qdrant_config(self) -> dict[str, Any]:
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

        return qdrant_config

    def _build_llm_config(self) -> dict[str, Any]:
        settings = self._settings
        llm_config: dict[str, Any] = {
            "model": settings.mem0_llm_model,
            "api_key": settings.mem0_llm_api_key,
        }
        llm_base_url = settings.mem0_llm_base_url.strip()
        if llm_base_url:
            if settings.mem0_llm_provider == "vllm":
                llm_config["vllm_base_url"] = llm_base_url
            else:
                llm_config["openai_base_url"] = llm_base_url

        return llm_config

    def _build_embedder_config(self) -> dict[str, Any]:
        settings = self._settings
        embedder_config: dict[str, Any] = {
            "model": settings.mem0_embedder_model,
            "api_key": settings.mem0_embedder_api_key,
        }
        embedder_base_url = settings.mem0_embedder_base_url.strip()
        if embedder_base_url:
            embedder_base_url_key = EMBEDDER_BASE_URL_KEYS.get(settings.mem0_embedder_provider)
            if not embedder_base_url_key:
                raise ValueError(
                    "Unsupported embedder provider for base URL override: "
                    f"{settings.mem0_embedder_provider}."
                )
            embedder_config[embedder_base_url_key] = embedder_base_url

        return embedder_config

    def _build_graph_store_config(self) -> dict[str, Any] | None:
        settings = self._settings
        if not settings.mem0_enable_graph:
            return None

        if not settings.mem0_graph_url or not settings.mem0_graph_username or not settings.mem0_graph_password:
            raise ValueError(
                "Graph memory is enabled, but MemGraph credentials are incomplete. "
                "Set MEMORIA_MEM0_GRAPH_URL, MEMORIA_MEM0_GRAPH_USERNAME, "
                "and MEMORIA_MEM0_GRAPH_PASSWORD."
            )

        return {
            "provider": settings.mem0_graph_provider,
            "config": {
                "url": settings.mem0_graph_url,
                "username": settings.mem0_graph_username,
                "password": settings.mem0_graph_password,
            },
        }

    def _build_config(self) -> dict[str, Any]:
        settings = self._settings

        config: dict[str, Any] = {
            "version": settings.mem0_version,
            "history_db_path": settings.mem0_history_db_path,
            "vector_store": {
                "provider": "qdrant",
                "config": self._build_qdrant_config(),
            },
            "llm": {
                "provider": settings.mem0_llm_provider,
                "config": self._build_llm_config(),
            },
            "embedder": {
                "provider": settings.mem0_embedder_provider,
                "config": self._build_embedder_config(),
            },
        }

        graph_store_config = self._build_graph_store_config()
        if graph_store_config is not None:
            config["graph_store"] = graph_store_config

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
