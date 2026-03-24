from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MEMORIA_",
        case_sensitive=False,
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8080
    mcp_path: str = "/mcp"
    user_header_name: str = "x-user-id"
    log_level: str = "INFO"

    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection_name: str = "mem0"
    qdrant_embedding_dims: int = 1536
    qdrant_on_disk: bool = False

    mem0_llm_provider: str = "vllm"
    mem0_llm_model: str = "gpt-4o-mini"
    mem0_llm_base_url: str = "http://host.docker.internal:8000/v1"
    mem0_embedder_provider: str = "openai"
    mem0_embedder_model: str = "text-embedding-3-small"
    mem0_embedder_base_url: str = "http://host.docker.internal:8000/v1"
    mem0_api_key: str | None = "dummy"
    mem0_llm_api_key: str | None = None
    mem0_embedder_api_key: str | None = None
    mem0_version: str = "v1.1"
    mem0_history_db_path: str = "./data/mem0_history.db"

    mem0_enable_graph: bool = False
    mem0_graph_provider: str = "memgraph"
    mem0_graph_url: str | None = "bolt://memgraph:7687"
    mem0_graph_username: str | None = "memgraph"
    mem0_graph_password: str | None = "memgraph"
