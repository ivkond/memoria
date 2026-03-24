from __future__ import annotations

import pytest

from memory_mcp_server.adapter import Mem0Adapter
from memory_mcp_server.settings import Settings


def test_build_config_includes_memgraph_when_enabled() -> None:
    settings = Settings(
        mem0_enable_graph=True,
        mem0_graph_provider="memgraph",
        mem0_graph_url="bolt://memgraph:7687",
        mem0_graph_username="memgraph",
        mem0_graph_password="memgraph",
    )
    adapter = Mem0Adapter(settings)

    config = adapter._build_config()

    assert "graph_store" in config
    assert config["graph_store"]["provider"] == "memgraph"
    assert config["graph_store"]["config"]["url"] == "bolt://memgraph:7687"


def test_build_config_raises_when_graph_credentials_missing() -> None:
    settings = Settings(
        mem0_enable_graph=True,
        mem0_graph_provider="memgraph",
        mem0_graph_url="",
        mem0_graph_username="",
        mem0_graph_password="",
    )
    adapter = Mem0Adapter(settings)

    with pytest.raises(ValueError, match="Graph memory is enabled"):
        adapter._build_config()


def test_build_config_uses_split_api_keys_when_provided() -> None:
    settings = Settings(
        mem0_api_key="common-key",
        mem0_llm_api_key="llm-key",
        mem0_embedder_api_key="embedder-key",
    )
    adapter = Mem0Adapter(settings)

    config = adapter._build_config()

    assert config["llm"]["config"]["api_key"] == "llm-key"
    assert config["embedder"]["config"]["api_key"] == "embedder-key"


def test_build_config_falls_back_to_common_api_key() -> None:
    settings = Settings(
        mem0_api_key="common-key",
        mem0_llm_api_key=None,
        mem0_embedder_api_key=None,
    )
    adapter = Mem0Adapter(settings)

    config = adapter._build_config()

    assert config["llm"]["config"]["api_key"] == "common-key"
    assert config["embedder"]["config"]["api_key"] == "common-key"


def test_add_memory_wraps_api_connection_error() -> None:
    class APIConnectionError(Exception):
        pass

    class BrokenMemory:
        def add(self, *_args, **_kwargs):
            raise APIConnectionError("connection error")

    adapter = Mem0Adapter(Settings())
    adapter._memory = BrokenMemory()  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="Cannot reach configured LLM/embedder endpoint"):
        adapter.add_memory([{"role": "user", "content": "hello"}], user_id="U1")
