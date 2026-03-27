from __future__ import annotations

import os
from typing import Literal

from pydantic import model_validator
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
    public_base_url: str | None = None
    auth_mode: Literal["local", "stub_auth", "oidc"] = "local"
    local_user_id: str = "local-user"
    user_header_name: str = "x-user-id"
    oidc_issuer_url: str | None = None
    oidc_public_issuer_url: str | None = None
    oidc_jwks_url: str | None = None
    oidc_audience: str | None = None
    oidc_subject_claim: str = "sub"
    oidc_required_scopes: str | None = None
    oidc_jwks_cache_ttl_seconds: int = 300
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
    mem0_llm_base_url: str = ""
    mem0_embedder_provider: str = "openai"
    mem0_embedder_model: str = "text-embedding-3-small"
    mem0_embedder_base_url: str = ""
    # Local OpenAI-compatible endpoints often only require a non-empty placeholder key.
    mem0_llm_api_key: str = "dummy"
    mem0_embedder_api_key: str = "dummy"
    mem0_version: str = "v1.1"
    mem0_history_db_path: str = "./data/mem0_history.db"

    mem0_enable_graph: bool = False
    mem0_graph_provider: str = "memgraph"
    mem0_graph_url: str | None = "bolt://memgraph:7687"
    mem0_graph_username: str | None = "memgraph"
    mem0_graph_password: str | None = "memgraph"

    @model_validator(mode="before")
    @classmethod
    def _reject_removed_mem0_api_key(cls, data: object) -> object:
        if isinstance(data, dict) and "mem0_api_key" in data:
            raise ValueError(
                "MEMORIA_MEM0_API_KEY has been removed. "
                "Use MEMORIA_MEM0_LLM_API_KEY and MEMORIA_MEM0_EMBEDDER_API_KEY instead."
            )
        return data

    @model_validator(mode="after")
    def _validate_auth_mode_settings(self) -> "Settings":
        if os.getenv("MEMORIA_MEM0_API_KEY"):
            raise ValueError(
                "MEMORIA_MEM0_API_KEY has been removed. "
                "Use MEMORIA_MEM0_LLM_API_KEY and MEMORIA_MEM0_EMBEDDER_API_KEY instead."
            )
        if self.auth_mode == "oidc":
            if not self.oidc_issuer_url:
                raise ValueError("MEMORIA_OIDC_ISSUER_URL is required when MEMORIA_AUTH_MODE=oidc.")
            if not self.oidc_audience:
                raise ValueError("MEMORIA_OIDC_AUDIENCE is required when MEMORIA_AUTH_MODE=oidc.")
        return self
