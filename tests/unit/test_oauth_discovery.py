from __future__ import annotations

from urllib.parse import urlunsplit

from starlette.testclient import TestClient

from memoria.server import create_server
from memoria.settings import Settings

HTTP_SCHEME = "http"


def _http_url(authority: str, path: str = "") -> str:
    return urlunsplit((HTTP_SCHEME, authority, path, "", ""))


def _build_oidc_app():
    settings = Settings(
        auth_mode="oidc",
        oidc_issuer_url=_http_url("keycloak.local", "/realms/memoria"),
        oidc_audience="memoria-mcp",
        public_base_url=_http_url("localhost:8080"),
    )
    server = create_server(settings=settings)
    return server.http_app(path=settings.mcp_path, transport="streamable-http")


def test_oauth_metadata_uses_public_oidc_issuer_for_browser_endpoints() -> None:
    settings = Settings(
        auth_mode="oidc",
        oidc_issuer_url=_http_url("keycloak:8080", "/realms/memoria"),
        oidc_public_issuer_url=_http_url("localhost:18081", "/realms/memoria"),
        oidc_audience="memoria-mcp",
        public_base_url=_http_url("localhost:8080"),
    )
    server = create_server(settings=settings)
    app = server.http_app(path=settings.mcp_path, transport="streamable-http")

    with TestClient(app) as client:
        response = client.get("/.well-known/oauth-authorization-server")
        assert response.status_code == 200
        payload = response.json()
        browser_prefix = _http_url("localhost:18081", "/")
        assert payload["authorization_endpoint"].startswith(browser_prefix)
        assert payload["token_endpoint"].startswith(browser_prefix)
        assert payload["jwks_uri"].startswith(browser_prefix)


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
            assert payload["issuer"] == _http_url("localhost:8080")
            assert payload["registration_endpoint"] == _http_url("localhost:8080", "/oauth/register")


def test_oauth_registration_endpoint_returns_static_public_client() -> None:
    app = _build_oidc_app()
    with TestClient(app) as client:
        response = client.post(
            "/oauth/register",
            json={
                "redirect_uris": [_http_url("127.0.0.1:54321", "/callback")],
                "client_name": "Kilo MCP Client",
            },
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["client_id"] == "memoria-mcp"
        assert payload["token_endpoint_auth_method"] == "none"
        assert payload["redirect_uris"] == [_http_url("127.0.0.1:54321", "/callback")]


def test_oauth_registration_rejects_redirect_uri_outside_keycloak_loopback_patterns() -> None:
    app = _build_oidc_app()
    with TestClient(app) as client:
        response = client.post(
            "/oauth/register",
            json={
                "redirect_uris": [_http_url("example.com", "/callback")],
                "client_name": "Kilo MCP Client",
            },
        )
        assert response.status_code == 400
        payload = response.json()
        assert payload["error"] == "invalid_redirect_uri"


def test_oauth_registration_requires_at_least_one_redirect_uri() -> None:
    app = _build_oidc_app()
    with TestClient(app) as client:
        response = client.post(
            "/oauth/register",
            json={
                "redirect_uris": [],
                "client_name": "Kilo MCP Client",
            },
        )
        assert response.status_code == 400
        payload = response.json()
        assert payload["error"] == "invalid_client_metadata"


def test_streamable_http_requires_bearer_and_returns_401() -> None:
    app = _build_oidc_app()
    with TestClient(app) as client:
        response = client.get("/mcp")
        assert response.status_code == 401
        assert "resource_metadata" in response.headers.get("www-authenticate", "")


def test_streamable_http_rejects_invalid_bearer_with_401() -> None:
    app = _build_oidc_app()
    with TestClient(app) as client:
        response = client.get("/mcp", headers={"authorization": "Bearer invalid-token"})
        assert response.status_code == 401
        assert "invalid_token" in response.headers.get("www-authenticate", "")
