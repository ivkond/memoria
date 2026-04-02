from __future__ import annotations

import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from qdrant_client import QdrantClient

from memoria.schemas import HealthComponent, HealthResponse
from memoria.settings import Settings


class HealthChecker:
    def __init__(self, settings: Settings):
        self._settings = settings

    def _probe_http_endpoint(self, *, name: str, base_url: str) -> HealthComponent:
        if not base_url.strip():
            return HealthComponent(ok=False, detail=f"{name} base url is empty")

        probe_url = f"{base_url.rstrip('/')}/models"
        request = Request(probe_url, method="GET")
        ssl_context: ssl.SSLContext | None = None
        if not self._settings.ssl_verify:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        try:
            with urlopen(request, timeout=2, context=ssl_context) as response:
                return HealthComponent(ok=True, detail=f"{name} reachable via {probe_url} (HTTP {response.status})")
        except HTTPError as exc:
            if 200 <= exc.code < 400:
                return HealthComponent(ok=True, detail=f"{name} reachable via {probe_url} (HTTP {exc.code})")
            return HealthComponent(ok=False, detail=f"{name} unavailable via {probe_url}: HTTP {exc.code}")
        except URLError as exc:
            return HealthComponent(ok=False, detail=f"{name} unavailable via {probe_url}: {exc.reason}")
        except Exception as exc:  # noqa: BLE001
            return HealthComponent(ok=False, detail=f"{name} unavailable via {probe_url}: {exc}")

    def check_qdrant(self) -> HealthComponent:
        try:
            if self._settings.qdrant_url:
                client = QdrantClient(
                    url=self._settings.qdrant_url,
                    api_key=self._settings.qdrant_api_key,
                )
            else:
                client = QdrantClient(
                    host=self._settings.qdrant_host,
                    port=self._settings.qdrant_port,
                )
            client.get_collections()
            return HealthComponent(ok=True, detail="qdrant reachable")
        except Exception as exc:  # noqa: BLE001
            return HealthComponent(ok=False, detail=f"qdrant unavailable: {exc}")

    def check_memgraph(self) -> HealthComponent:
        if not self._settings.mem0_enable_graph:
            return HealthComponent(ok=True, detail="graph disabled")
        if self._settings.mem0_graph_provider.lower() != "memgraph":
            return HealthComponent(ok=True, detail=f"graph provider {self._settings.mem0_graph_provider} not checked")

        url = self._settings.mem0_graph_url
        if not url:
            return HealthComponent(ok=False, detail="memgraph url is empty")

        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or 7687
        if not host:
            return HealthComponent(ok=False, detail=f"invalid memgraph url: {url}")

        try:
            with socket.create_connection((host, port), timeout=2):
                return HealthComponent(ok=True, detail="memgraph bolt reachable")
        except Exception as exc:  # noqa: BLE001
            return HealthComponent(ok=False, detail=f"memgraph unavailable: {exc}")

    def check_llm(self) -> HealthComponent:
        return self._probe_http_endpoint(name="llm", base_url=self._settings.mem0_llm_base_url)

    def check_embedder(self) -> HealthComponent:
        return self._probe_http_endpoint(name="embedder", base_url=self._settings.mem0_embedder_base_url)

    def check(self) -> HealthResponse:
        checks = {
            "qdrant": self.check_qdrant(),
            "memgraph": self.check_memgraph(),
            "llm": self.check_llm(),
            "embedder": self.check_embedder(),
        }
        is_ok = all(component.ok for component in checks.values())
        return HealthResponse(status="ok" if is_ok else "degraded", checks=checks)
