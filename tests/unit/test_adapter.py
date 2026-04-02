from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from openai import OpenAI

from memoria.adapter import Mem0Adapter
from memoria.settings import Settings


def test_settings_defaults_do_not_embed_insecure_http_urls() -> None:
    settings = Settings()

    assert settings.mem0_llm_base_url == ""
    assert settings.mem0_embedder_base_url == ""


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
        mem0_llm_api_key="llm-key",
        mem0_embedder_api_key="embedder-key",
    )
    adapter = Mem0Adapter(settings)

    config = adapter._build_config()

    assert config["llm"]["config"]["api_key"] == "llm-key"
    assert config["embedder"]["config"]["api_key"] == "embedder-key"


def test_build_config_uses_default_dummy_api_keys() -> None:
    settings = Settings()
    adapter = Mem0Adapter(settings)

    config = adapter._build_config()

    assert config["llm"]["config"]["api_key"] == "dummy"
    assert config["embedder"]["config"]["api_key"] == "dummy"


def test_build_config_omits_empty_base_urls() -> None:
    settings = Settings(
        mem0_llm_base_url="",
        mem0_embedder_base_url="",
    )
    adapter = Mem0Adapter(settings)

    config = adapter._build_config()

    assert "vllm_base_url" not in config["llm"]["config"]
    assert "openai_base_url" not in config["embedder"]["config"]


def test_build_config_uses_provider_specific_embedder_base_url_key() -> None:
    settings = Settings(
        mem0_embedder_provider="ollama",
        mem0_embedder_base_url="http://localhost:11434",
    )
    adapter = Mem0Adapter(settings)

    config = adapter._build_config()

    assert config["embedder"]["config"]["ollama_base_url"] == "http://localhost:11434"
    assert "openai_base_url" not in config["embedder"]["config"]


def test_build_config_maps_vllm_embedder_base_url_to_openai_key() -> None:
    settings = Settings(
        mem0_embedder_provider="vllm",
        mem0_embedder_base_url="http://localhost:8000/v1",
    )
    adapter = Mem0Adapter(settings)

    config = adapter._build_config()

    assert config["embedder"]["config"]["openai_base_url"] == "http://localhost:8000/v1"


def test_build_config_rejects_unsupported_embedder_base_url_provider() -> None:
    settings = Settings(
        mem0_embedder_provider="huggingface",
        mem0_embedder_base_url="http://localhost:9999",
    )
    adapter = Mem0Adapter(settings)

    with pytest.raises(ValueError, match="Unsupported embedder provider"):
        adapter._build_config()


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


@pytest.mark.parametrize("error", [httpx.ConnectError("connect"), httpx.TimeoutException("timeout")])
def test_add_memory_wraps_httpx_connectivity_errors(error: Exception) -> None:
    class BrokenMemory:
        def add(self, *_args, **_kwargs):
            raise error

    adapter = Mem0Adapter(Settings())
    adapter._memory = BrokenMemory()  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="Cannot reach configured LLM/embedder endpoint"):
        adapter.add_memory([{"role": "user", "content": "hello"}], user_id="U1")


def test_patch_ssl_verify_replaces_openai_clients() -> None:
    class FakeEmbedder:
        client = OpenAI(api_key="emb-key", base_url="https://emb.local/v1")

    class FakeLLM:
        client = OpenAI(api_key="llm-key", base_url="https://llm.local/v1")

    class FakeMemory:
        llm = FakeLLM()
        embedding_model = FakeEmbedder()

    memory = FakeMemory()
    Mem0Adapter._patch_ssl_verify(memory)  # type: ignore[arg-type]

    assert memory.llm.client.api_key == "llm-key"
    assert str(memory.llm.client.base_url) == "https://llm.local/v1/"
    assert memory.llm.client._client._transport._pool._ssl_context.verify_mode.name == "CERT_NONE"

    assert memory.embedding_model.client.api_key == "emb-key"
    assert str(memory.embedding_model.client.base_url) == "https://emb.local/v1/"
    assert memory.embedding_model.client._client._transport._pool._ssl_context.verify_mode.name == "CERT_NONE"


def test_patch_ssl_verify_skips_non_openai_client() -> None:
    class CustomClient:
        pass

    class FakeLLM:
        client = CustomClient()

    class FakeMemory:
        llm = FakeLLM()
        embedding_model = None

    memory = FakeMemory()
    original_client = memory.llm.client
    Mem0Adapter._patch_ssl_verify(memory)  # type: ignore[arg-type]

    assert memory.llm.client is original_client


def test_memory_property_calls_patch_when_ssl_verify_false(monkeypatch: pytest.MonkeyPatch) -> None:
    patched_calls: list[object] = []

    def fake_from_config(_config: object) -> object:
        return object()

    def fake_patch(memory: object) -> None:
        patched_calls.append(memory)

    monkeypatch.setattr("memoria.adapter.Memory.from_config", fake_from_config)
    monkeypatch.setattr(Mem0Adapter, "_patch_ssl_verify", staticmethod(fake_patch))

    adapter = Mem0Adapter(Settings(ssl_verify=False))
    _ = adapter.memory

    assert len(patched_calls) == 1


def test_memory_property_skips_patch_when_ssl_verify_true(monkeypatch: pytest.MonkeyPatch) -> None:
    patched_calls: list[object] = []

    def fake_from_config(_config: object) -> object:
        return object()

    def fake_patch(memory: object) -> None:
        patched_calls.append(memory)

    monkeypatch.setattr("memoria.adapter.Memory.from_config", fake_from_config)
    monkeypatch.setattr(Mem0Adapter, "_patch_ssl_verify", staticmethod(fake_patch))

    adapter = Mem0Adapter(Settings(ssl_verify=True))
    _ = adapter.memory

    assert len(patched_calls) == 0


def test_memory_property_initializes_single_instance_under_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    created_objects: list[object] = []
    created_lock = threading.Lock()

    def fake_from_config(_config: object) -> object:
        time.sleep(0.05)
        instance = object()
        with created_lock:
            created_objects.append(instance)
        return instance

    monkeypatch.setattr("memoria.adapter.Memory.from_config", fake_from_config)
    adapter = Mem0Adapter(Settings())

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: adapter.memory, range(8)))

    assert len(created_objects) == 1
    assert all(item is created_objects[0] for item in results)
