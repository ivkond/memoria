from __future__ import annotations

from starlette.testclient import TestClient

from memoria.server import create_server
from memoria.settings import Settings


def _build_oidc_app():
    settings = Settings(
        auth_mode="oidc",
        oidc_issuer_url="http://keycloak.local/realms/memoria",
        oidc_audience="memoria-mcp",
        public_base_url="http://localhost:8080",
    )
    server = create_server(settings=settings)
    return server.http_app(path=settings.mcp_path, transport="streamable-http")


def test_oauth_metadata_uses_public_oidc_issuer_for_browser_endpoints() -> None:
    settings = Settings(
        auth_mode="oidc",
        oidc_issuer_url="http://keycloak:8080/realms/memoria",
        oidc_public_issuer_url="http://localhost:18081/realms/memoria",
        oidc_audience="memoria-mcp",
        public_base_url="http://localhost:8080",
    )
    server = create_server(settings=settings)
    app = server.http_app(path=settings.mcp_path, transport="streamable-http")

    with TestClient(app) as client:
        response = client.get("/.well-known/oauth-authorization-server")
        assert response.status_code == 200
        payload = response.json()
        assert payload["authorization_endpoint"].startswith("http://localhost:18081/")
        assert payload["token_endpoint"].startswith("http://localhost:18081/")
        assert payload["jwks_uri"].startswith("http://localhost:18081/")


def test_oauth_authorization_server_metadata_is_exposed_on_compat_routes() -> None:
    app = _build_oidc_app()
    with TestClient(app) as client:
        for path in (
            "/.well-known/oauth-authorization-server",
            "/.well-known/oauth-authorization-server/mcp",
            "/mcp/.well-known/oauth-authorization-server",
        ):
            response = client.get(path)
            assert response.status_code == 200
            payload = response.json()
            assert payload["issuer"] == "http://localhost:8080"
            assert payload["registration_endpoint"] == "http://localhost:8080/oauth/register"


def test_oauth_registration_endpoint_returns_static_public_client() -> None:
    app = _build_oidc_app()
    with TestClient(app) as client:
        response = client.post(
            "/oauth/register",
            json={
                "redirect_uris": ["http://127.0.0.1:54321/callback"],
                "client_name": "Kilo MCP Client",
            },
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["client_id"] == "memoria-mcp"
        assert payload["token_endpoint_auth_method"] == "none"
        assert payload["redirect_uris"] == ["http://127.0.0.1:54321/callback"]


def test_streamable_http_requires_bearer_and_returns_401() -> None:
    app = _build_oidc_app()
    with TestClient(app) as client:
        response = client.get("/mcp")
        assert response.status_code == 401
        assert "resource_metadata" in response.headers.get("www-authenticate", "")
