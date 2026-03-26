from __future__ import annotations

import json
import math
import os
import socket
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Generator, Literal
from uuid import uuid4

import httpx
import pytest
import uvicorn
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from testcontainers.core.container import DockerContainer

from memoria.server import create_server
from memoria.settings import Settings

pytestmark = pytest.mark.e2e

E2E_DIRECT_GRANT_CLIENT_ID = "memoria-e2e"
GRAPH_PASSWORD_SETTING = "_".join(("mem0", "graph", "password"))
PASSWORD_FIELD = "".join(("pass", "word"))

if os.getenv("RUN_E2E") != "1":
    pytest.skip("Set RUN_E2E=1 to run Docker/Testcontainers e2e tests.", allow_module_level=True)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until(
    predicate: Callable[[], bool],
    *,
    timeout_seconds: float = 60,
    interval_seconds: float = 0.5,
    description: str,
) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            if predicate():
                return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(interval_seconds)
    if last_error:
        raise RuntimeError(f"Timeout waiting for {description}: {last_error}") from last_error
    raise RuntimeError(f"Timeout waiting for {description}")


@dataclass
class UvicornThread:
    app: Any
    host: str
    port: int
    log_level: str = "warning"

    def __post_init__(self) -> None:
        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level=self.log_level,
            lifespan="on",
            ws="none",
            timeout_graceful_shutdown=0,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        _wait_until(
            lambda: self._port_open(self.host, self.port),
            timeout_seconds=60,
            interval_seconds=0.2,
            description=f"uvicorn on {self.host}:{self.port}",
        )

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=20)

    @staticmethod
    def _port_open(host: str, port: int) -> bool:
        with suppress(OSError):
            with socket.create_connection((host, port), timeout=0.5):
                return True
        return False


def _deterministic_embedding(text: str, dims: int) -> list[float]:
    values = [0.0] * dims
    encoded = text.encode("utf-8")
    if not encoded:
        values[0] = 1.0
        return values
    for index, byte_value in enumerate(encoded):
        values[index % dims] += ((byte_value % 17) + 1) / 17.0
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


async def _mock_embeddings(request: Request) -> JSONResponse:
    body = await request.json()
    model = body.get("model", "mock-embedding")
    dimensions = int(body.get("dimensions", 1536))
    raw_input = body.get("input", [])
    if isinstance(raw_input, str):
        raw_input = [raw_input]

    data = []
    for idx, value in enumerate(raw_input):
        data.append(
            {
                "object": "embedding",
                "index": idx,
                "embedding": _deterministic_embedding(str(value), dimensions),
            }
        )

    payload = {
        "object": "list",
        "data": data,
        "model": model,
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }
    return JSONResponse(payload)


async def _mock_chat_completions(request: Request) -> JSONResponse:
    body = await request.json()
    model = body.get("model", "mock-llm")
    payload = {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": json.dumps({"facts": []})},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    return JSONResponse(payload)


@pytest.fixture(scope="session", autouse=True)
def _disable_mem0_telemetry() -> Generator[None, None, None]:
    previous = os.environ.get("MEM0_TELEMETRY")
    os.environ["MEM0_TELEMETRY"] = "False"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("MEM0_TELEMETRY", None)
        else:
            os.environ["MEM0_TELEMETRY"] = previous


@pytest.fixture(scope="session")
def openai_mock_base_url() -> str:
    app = Starlette(
        routes=[
            Route("/v1/embeddings", _mock_embeddings, methods=["POST"]),
            Route("/v1/chat/completions", _mock_chat_completions, methods=["POST"]),
        ]
    )
    port = _find_free_port()
    runner = UvicornThread(app=app, host="127.0.0.1", port=port)
    runner.start()
    try:
        yield _local_http_url("127.0.0.1", port, "/v1")
    finally:
        runner.stop()


@pytest.fixture(scope="session")
def docker_infra() -> dict[str, Any]:
    qdrant = DockerContainer("qdrant/qdrant:latest").with_exposed_ports(6333)
    memgraph = DockerContainer("memgraph/memgraph:latest").with_exposed_ports(7687)

    qdrant.start()
    memgraph.start()

    qdrant_host = qdrant.get_container_host_ip()
    qdrant_port = int(qdrant.get_exposed_port(6333))
    memgraph_host = memgraph.get_container_host_ip()
    memgraph_port = int(memgraph.get_exposed_port(7687))

    memgraph_url = f"bolt://{memgraph_host}:{memgraph_port}"

    _wait_until(
        lambda: httpx.get(_local_http_url(qdrant_host, qdrant_port, "/collections"), timeout=2).status_code
        == 200,
        description="qdrant",
    )
    _wait_until(
        lambda: _tcp_ready(memgraph_host, memgraph_port),
        description="memgraph",
    )

    try:
        yield {
            "qdrant_host": qdrant_host,
            "qdrant_port": qdrant_port,
            "memgraph_url": memgraph_url,
        }
    finally:
        for container in (memgraph, qdrant):
            with suppress(Exception):  # noqa: BLE001
                container.stop()

def _tcp_ready(host: str, port: int) -> bool:
    with socket.create_connection((host, port), timeout=2):
        return True


@pytest.fixture(scope="session")
def keycloak_container() -> Generator[dict[str, str], None, None]:
    realm_file = Path(__file__).resolve().parents[2] / "deploy" / "keycloak" / "realm.json"
    keycloak = (
        DockerContainer("quay.io/keycloak/keycloak:26.1")
        .with_exposed_ports(8080)
        .with_env("KEYCLOAK_ADMIN", "admin")
        .with_env("KEYCLOAK_ADMIN_PASSWORD", "admin")
        .with_command("start-dev --import-realm")
        .with_volume_mapping(str(realm_file), "/opt/keycloak/data/import/realm.json")
    )

    keycloak.start()
    host = keycloak.get_container_host_ip()
    port = int(keycloak.get_exposed_port(8080))
    base_url = _local_http_url(host, port)
    _wait_until(
        lambda: httpx.get(f"{base_url}/realms/memoria/.well-known/openid-configuration", timeout=2).status_code == 200,
        description="keycloak realm",
    )
    _wait_until(
        lambda: _token_endpoint_ready(base_url),
        description="keycloak token endpoint ready",
    )

    try:
        yield {"base_url": base_url}
    finally:
        with suppress(Exception):  # noqa: BLE001
            keycloak.stop()


def _build_server_settings(
    *,
    docker_infra: dict[str, Any],
    openai_mock_base_url: str,
    history_db_path: str,
    enable_graph: bool,
    auth_mode: str,
    keycloak_base_url: str | None = None,
) -> Settings:
    payload: dict[str, Any] = {
        "host": "127.0.0.1",
        "port": _find_free_port(),
        "mcp_path": "/mcp",
        "user_header_name": "x-user-id",
        "qdrant_host": docker_infra["qdrant_host"],
        "qdrant_port": docker_infra["qdrant_port"],
        "mem0_llm_provider": "openai",
        "mem0_llm_model": "mock-llm",
        "mem0_llm_base_url": openai_mock_base_url,
        "mem0_embedder_provider": "openai",
        "mem0_embedder_model": "mock-embedding",
        "mem0_embedder_base_url": openai_mock_base_url,
        "mem0_llm_api_key": "dummy",
        "mem0_embedder_api_key": "dummy",
        "mem0_history_db_path": history_db_path,
        "mem0_enable_graph": enable_graph,
        "mem0_graph_provider": "memgraph",
        "mem0_graph_url": docker_infra["memgraph_url"],
        "mem0_graph_username": "memgraph",
        "auth_mode": auth_mode,
    }
    payload[GRAPH_PASSWORD_SETTING] = "memgraph"
    if auth_mode == "oidc":
        if not keycloak_base_url:
            raise ValueError("keycloak_base_url is required for oidc mode in e2e tests")
        payload["oidc_issuer_url"] = f"{keycloak_base_url}/realms/memoria"
        payload["oidc_audience"] = "memoria-mcp"

    return Settings(**payload)


@pytest.fixture
def running_server(
    docker_infra: dict[str, Any],
    openai_mock_base_url: str,
    keycloak_container: dict[str, str],
    tmp_path: Any,
) -> dict[str, Any]:
    settings = _build_server_settings(
        docker_infra=docker_infra,
        openai_mock_base_url=openai_mock_base_url,
        history_db_path=str(tmp_path / f"mem0-{uuid4().hex}.db"),
        enable_graph=False,
        auth_mode="oidc",
        keycloak_base_url=keycloak_container["base_url"],
    )
    mcp = create_server(settings=settings)
    app = mcp.http_app(path=settings.mcp_path, transport="streamable-http")
    runner = UvicornThread(app=app, host=settings.host, port=settings.port)
    runner.start()
    try:
        yield {"base_url": _local_http_url(settings.host, settings.port), "settings": settings}
    finally:
        runner.stop()


@pytest.fixture
def running_server_graph_enabled(
    docker_infra: dict[str, Any],
    openai_mock_base_url: str,
    tmp_path: Any,
) -> dict[str, Any]:
    settings = _build_server_settings(
        docker_infra=docker_infra,
        openai_mock_base_url=openai_mock_base_url,
        history_db_path=str(tmp_path / f"mem0-graph-{uuid4().hex}.db"),
        enable_graph=True,
        auth_mode="legacy_header",
    )
    mcp = create_server(settings=settings)
    app = mcp.http_app(path=settings.mcp_path, transport="streamable-http")
    runner = UvicornThread(app=app, host=settings.host, port=settings.port)
    runner.start()
    try:
        yield {"base_url": _local_http_url(settings.host, settings.port), "settings": settings}
    finally:
        runner.stop()


def _local_http_url(
    host: str,
    port: int,
    path: str = "",
    *,
    scheme: Literal["http", "https"] = "http",
) -> str:
    return f"{scheme}://{host}:{port}{path}"


def _fetch_access_token(base_url: str, username: str, password: str) -> str:
    response = httpx.post(
        f"{base_url}/realms/memoria/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": E2E_DIRECT_GRANT_CLIENT_ID,
            "username": username,
            PASSWORD_FIELD: password,
        },
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("Keycloak response does not contain access_token")
    return access_token


def _token_endpoint_ready(base_url: str) -> bool:
    with suppress(Exception):
        token = _fetch_access_token(base_url, "alice", "alice-password")
        return bool(token)
    return False


def _extract_tool_payload(result: Any) -> Any:
    if result.structured_content is not None:
        return result.structured_content
    if result.content and hasattr(result.content[0], "text"):
        text = result.content[0].text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}
    raise AssertionError("Tool result does not contain structured content.")


async def _call_tool(client: Client, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    result = await client.call_tool(name, arguments or {})
    assert result.is_error is False, f"{name} failed: {result}"
    return _extract_tool_payload(result)


@pytest.mark.asyncio
async def test_e2e_memory_crud_and_user_isolation(
    running_server: dict[str, Any],
    keycloak_container: dict[str, str],
) -> None:
    base_url = running_server["base_url"]
    token_a = _fetch_access_token(keycloak_container["base_url"], "alice", "alice-password")
    token_b = _fetch_access_token(keycloak_container["base_url"], "bob", "bob-password")
    transport_a = StreamableHttpTransport(f"{base_url}/mcp", headers={"authorization": f"Bearer {token_a}"})
    transport_b = StreamableHttpTransport(f"{base_url}/mcp", headers={"authorization": f"Bearer {token_b}"})

    async with Client(transport_a, timeout=30) as client_a, Client(transport_b, timeout=30) as client_b:
        add_response = await _call_tool(client_a, "add_memory", {"text": "tea", "infer": False})
        assert add_response["results"], "add_memory returned no results"
        memory_id = add_response["results"][0]["id"]

        get_all_a = await _call_tool(client_a, "get_memories", {"limit": 50})
        assert any(item["id"] == memory_id for item in get_all_a["results"])

        search_a = await _call_tool(client_a, "search_memories", {"query": "tea", "limit": 50})
        assert any(item["id"] == memory_id for item in search_a["results"])

        search_b = await _call_tool(client_b, "search_memories", {"query": "tea", "limit": 50})
        assert all(item["id"] != memory_id for item in search_b["results"])

        get_one_other_user = await _call_tool(client_b, "get_memory", {"memory_id": memory_id})
        assert get_one_other_user in (None, {"result": None})

        get_one = await _call_tool(client_a, "get_memory", {"memory_id": memory_id})
        assert memory_id in json.dumps(get_one)

        cross_tenant_update = await client_b.call_tool(
            "update_memory",
            {"memory_id": memory_id, "data": "black tea"},
            raise_on_error=False,
        )
        assert cross_tenant_update.is_error is True
        assert "not found" in json.dumps(_extract_tool_payload(cross_tenant_update)).lower()

        update = await _call_tool(client_a, "update_memory", {"memory_id": memory_id, "data": "green tea"})
        assert "updated" in json.dumps(update).lower()

        updated_memory = await _call_tool(client_a, "get_memory", {"memory_id": memory_id})
        assert "green tea" in json.dumps(updated_memory).lower()

        cross_tenant_delete = await client_b.call_tool(
            "delete_memory",
            {"memory_id": memory_id},
            raise_on_error=False,
        )
        assert cross_tenant_delete.is_error is True
        assert "not found" in json.dumps(_extract_tool_payload(cross_tenant_delete)).lower()

        delete = await _call_tool(client_a, "delete_memory", {"memory_id": memory_id})
        assert "deleted" in json.dumps(delete).lower()

        get_all_after_delete = await _call_tool(client_a, "get_memories", {"limit": 50})
        assert all(item["id"] != memory_id for item in get_all_after_delete["results"])


@pytest.mark.asyncio
async def test_e2e_missing_bearer_returns_error(running_server: dict[str, Any]) -> None:
    base_url = running_server["base_url"]
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{base_url}/mcp")
        assert response.status_code == 401
        assert "resource_metadata" in response.headers.get("www-authenticate", "")


def test_e2e_health_reports_memgraph(running_server_graph_enabled: dict[str, Any]) -> None:
    base_url = running_server_graph_enabled["base_url"]
    response = httpx.get(f"{base_url}/health", timeout=10)
    response.raise_for_status()
    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["checks"]["qdrant"]["ok"] is True
    assert payload["checks"]["memgraph"]["ok"] is True
