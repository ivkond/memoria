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

