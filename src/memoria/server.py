from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlsplit

from fastmcp import Context, FastMCP
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.middleware import Middleware
from pydantic import AnyHttpUrl, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from memoria.adapter import Mem0Adapter, MemoryAdapter
from memoria.auth import LocalUserMiddleware, OidcBearerMiddleware, UserHeaderMiddleware, require_user_id
from memoria.health import HealthChecker
from memoria.oidc import OidcConfig, OidcTokenValidator, OidcTokenVerifier
from memoria.service import MemoryService
from memoria.settings import Settings

TOOL_CONTEXT_REQUIRED_MESSAGE = "Tool context is required."
MEMORY_ID_DESCRIPTION = "Memory ID."
LOGGER = logging.getLogger(__name__)


async def _require_tool_user_id(
    ctx: Context | None,
    user_header_name: str,
    *,
    allow_header_fallback: bool = True,
) -> str:
    if ctx is None:
        raise ValueError(TOOL_CONTEXT_REQUIRED_MESSAGE)
    if allow_header_fallback:
        return await require_user_id(ctx, user_header_name)
    return await require_user_id(ctx, user_header_name, allow_header_fallback=False)


def _memory_id_field() -> Any:
    return Field(description=MEMORY_ID_DESCRIPTION)


def _allow_header_fallback(settings: Settings) -> bool:
    return settings.auth_mode == "stub_auth"


def _normalized_mcp_path(raw_path: str) -> str:
    if not raw_path.startswith("/"):
        raw_path = f"/{raw_path}"
    return raw_path.rstrip("/") or "/"


def _resolve_public_base_url(settings: Settings) -> str:
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    return f"http://localhost:{settings.port}"


def _parse_required_scopes(raw_scopes: str | None) -> list[str]:
    if not raw_scopes:
        return []
    return [scope for scope in raw_scopes.split() if scope]


def _is_allowed_redirect_uri(uri: str) -> bool:
    parsed = urlsplit(uri)
    hostname = parsed.hostname
    return parsed.scheme == "http" and hostname in {"127.0.0.1", "localhost", "::1"}


def _resolve_public_oidc_issuer_url(settings: Settings) -> str:
    if settings.oidc_public_issuer_url:
        return settings.oidc_public_issuer_url.rstrip("/")
    return (settings.oidc_issuer_url or "").rstrip("/")


def _metadata_paths_for_mcp_path(mcp_path: str) -> set[str]:
    metadata_paths = {"/.well-known/oauth-authorization-server"}
    if mcp_path != "/":
        metadata_paths.add(f"/.well-known/oauth-authorization-server{mcp_path}")
        metadata_paths.add(f"{mcp_path}/.well-known/oauth-authorization-server")
    return metadata_paths


async def _oauth_registration_payload(request: Request) -> dict[str, Any]:
    try:
        candidate = await request.json()
    except Exception as error:  # noqa: BLE001
        LOGGER.debug("Ignoring invalid oauth registration payload", exc_info=error)
        return {}
    return candidate if isinstance(candidate, dict) else {}


def _oauth_registration_redirect_uris(payload: dict[str, Any]) -> list[str]:
    redirect_uris_raw = payload.get("redirect_uris", [])
    if not isinstance(redirect_uris_raw, list):
        return []
    return [uri for uri in redirect_uris_raw if isinstance(uri, str) and uri.strip()]


def _oauth_registration_response(
    settings: Settings,
    payload: dict[str, Any],
    redirect_uris: list[str],
) -> JSONResponse:
    if not redirect_uris:
        return JSONResponse(status_code=400, content={"error": "invalid_client_metadata"})
    if any(not _is_allowed_redirect_uri(uri) for uri in redirect_uris):
        return JSONResponse(status_code=400, content={"error": "invalid_redirect_uri"})

    body = {
        "client_id": settings.oidc_audience or "memoria-mcp",
        "client_id_issued_at": int(time.time()),
        "client_name": payload.get("client_name") or "Memoria MCP Client",
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "redirect_uris": redirect_uris,
    }
    return JSONResponse(status_code=201, content=body)


def _build_oidc_validator(settings: Settings) -> OidcTokenValidator:
    validation_issuer_url = _resolve_public_oidc_issuer_url(settings) or (settings.oidc_issuer_url or "")
    return OidcTokenValidator(
        OidcConfig(
            issuer_url=validation_issuer_url,
            audience=settings.oidc_audience or "",
            subject_claim=settings.oidc_subject_claim,
            jwks_url=settings.oidc_jwks_url,
            jwks_ttl_seconds=settings.oidc_jwks_cache_ttl_seconds,
        )
    )


def _build_auth_provider(
    settings: Settings,
    validator: OidcTokenValidator | None = None,
) -> RemoteAuthProvider | None:
    if settings.auth_mode != "oidc":
        return None

    public_base_url = _resolve_public_base_url(settings)
    token_validator = validator or _build_oidc_validator(settings)
    token_verifier = OidcTokenVerifier(
        token_validator,
        required_scopes=_parse_required_scopes(settings.oidc_required_scopes),
        base_url=public_base_url,
    )
    return RemoteAuthProvider(
        token_verifier=token_verifier,
        authorization_servers=[AnyHttpUrl(public_base_url)],
        base_url=public_base_url,
        resource_name="Memoria MCP",
    )


def _authorization_server_metadata(settings: Settings) -> dict[str, Any]:
    issuer_url = _resolve_public_oidc_issuer_url(settings)
    public_base_url = _resolve_public_base_url(settings)
    required_scopes = _parse_required_scopes(settings.oidc_required_scopes)

    metadata: dict[str, Any] = {
        "issuer": public_base_url,
        "authorization_endpoint": f"{issuer_url}/protocol/openid-connect/auth",
        "token_endpoint": f"{issuer_url}/protocol/openid-connect/token",
        "jwks_uri": f"{issuer_url}/protocol/openid-connect/certs",
        "registration_endpoint": f"{public_base_url}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post", "client_secret_basic"],
        "code_challenge_methods_supported": ["S256"],
        "client_id_metadata_document_supported": False,
    }
    if required_scopes:
        metadata["scopes_supported"] = required_scopes
    return metadata


def _register_oidc_oauth_routes(mcp: FastMCP, settings: Settings) -> None:
    if settings.auth_mode != "oidc":
        return

    metadata = _authorization_server_metadata(settings)
    mcp_path = _normalized_mcp_path(settings.mcp_path)

    def _build_metadata_handler() -> Any:
        def oauth_authorization_server_metadata(_: Request) -> JSONResponse:
            return JSONResponse(metadata)

        return oauth_authorization_server_metadata

    for path in _metadata_paths_for_mcp_path(mcp_path):
        mcp.custom_route(path, methods=["GET"])(_build_metadata_handler())

    @mcp.custom_route("/oauth/register", methods=["POST"])
    async def oauth_register(request: Request) -> JSONResponse:
        # This is a fixed-client helper for loopback redirects, not full dynamic client registration.
        payload = await _oauth_registration_payload(request)
        redirect_uris = _oauth_registration_redirect_uris(payload)
        return _oauth_registration_response(settings, payload, redirect_uris)


def _register_health_route(mcp: FastMCP, health_checker: HealthChecker) -> None:
    @mcp.custom_route("/health", methods=["GET"])
    async def health(_: Request) -> JSONResponse:
        response = health_checker.check()
        status_code = 200 if response.status == "ok" else 503
        return JSONResponse(status_code=status_code, content=response.model_dump())


def _register_memory_tools(
    mcp: FastMCP,
    service: MemoryService,
    app_settings: Settings,
) -> None:
    @mcp.tool(
        description=(
            "Store a memory for current user scope. "
            "If messages are omitted, text is wrapped into a single user message."
        )
    )
    async def add_memory(
        text: str = Field(description="Natural language memory payload."),
        messages: list[dict[str, str]] | None = Field(
            default=None,
            description="Optional structured role/content message list.",
        ),
        metadata: dict[str, Any] | None = Field(
            default=None,
            description="Optional metadata attached to memory items.",
        ),
        infer: bool = Field(
            default=True,
            description="Enable mem0 inference behavior.",
        ),
        memory_type: str | None = Field(
            default=None,
            description="Optional mem0 memory type.",
        ),
        prompt: str | None = Field(
            default=None,
            description="Optional custom extraction prompt.",
        ),
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        user_id = await _require_tool_user_id(
            ctx,
            app_settings.user_header_name,
            allow_header_fallback=_allow_header_fallback(app_settings),
        )
        return service.add_memory(
            user_id=user_id,
            text=text,
            messages=messages,
            metadata=metadata,
            infer=infer,
            memory_type=memory_type,
            prompt=prompt,
        )

    @mcp.tool(description="Semantic search memories for current user.")
    async def search_memories(
        query: str = Field(description="Search query."),
        limit: int = Field(default=20, ge=1, le=200),
        filters: dict[str, Any] | None = Field(default=None),
        threshold: float | None = Field(default=None),
        rerank: bool = Field(default=True),
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        user_id = await _require_tool_user_id(
            ctx,
            app_settings.user_header_name,
            allow_header_fallback=_allow_header_fallback(app_settings),
        )
        return service.search_memories(
            user_id=user_id,
            query=query,
            limit=limit,
            filters=filters,
            threshold=threshold,
            rerank=rerank,
        )

    @mcp.tool(description="Get single memory by ID.")
    async def get_memory(
        memory_id: str = _memory_id_field(),
        ctx: Context | None = None,
    ) -> dict[str, Any] | None:
        user_id = await _require_tool_user_id(
            ctx,
            app_settings.user_header_name,
            allow_header_fallback=_allow_header_fallback(app_settings),
        )
        return service.get_memory(user_id=user_id, memory_id=memory_id)

    @mcp.tool(description="List memories for current user.")
    async def get_memories(
        limit: int = Field(default=100, ge=1, le=500),
        filters: dict[str, Any] | None = Field(default=None),
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        user_id = await _require_tool_user_id(
            ctx,
            app_settings.user_header_name,
            allow_header_fallback=_allow_header_fallback(app_settings),
        )
        return service.get_memories(user_id=user_id, limit=limit, filters=filters)

    @mcp.tool(description="Update memory text by ID.")
    async def update_memory(
        memory_id: str = _memory_id_field(),
        data: str = Field(description="Updated memory text."),
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        user_id = await _require_tool_user_id(
            ctx,
            app_settings.user_header_name,
            allow_header_fallback=_allow_header_fallback(app_settings),
        )
        return service.update_memory(user_id=user_id, memory_id=memory_id, data=data)

    @mcp.tool(description="Delete memory by ID.")
    async def delete_memory(
        memory_id: str = _memory_id_field(),
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        user_id = await _require_tool_user_id(
            ctx,
            app_settings.user_header_name,
            allow_header_fallback=_allow_header_fallback(app_settings),
        )
        return service.delete_memory(user_id=user_id, memory_id=memory_id)

    @mcp.tool(description="Delete all memories for current user.")
    async def delete_all_memories(ctx: Context | None = None) -> dict[str, Any]:
        user_id = await _require_tool_user_id(
            ctx,
            app_settings.user_header_name,
            allow_header_fallback=_allow_header_fallback(app_settings),
        )
        return service.delete_all_memories(user_id=user_id)

    @mcp.tool(
        description=(
            "List graph relations for current user. "
            "Relations are available only when mem0 graph_store is enabled."
        )
    )
    async def list_entities(
        limit: int = Field(default=100, ge=1, le=500),
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        user_id = await _require_tool_user_id(
            ctx,
            app_settings.user_header_name,
            allow_header_fallback=_allow_header_fallback(app_settings),
        )
        return service.list_entities(user_id=user_id, limit=limit)

    @mcp.tool(
        description=(
            "Delete entities for current user. "
            "In mem0 OSS this is mapped to delete_all_memories for that user scope."
        )
    )
    async def delete_entities(ctx: Context | None = None) -> dict[str, Any]:
        user_id = await _require_tool_user_id(
            ctx,
            app_settings.user_header_name,
            allow_header_fallback=_allow_header_fallback(app_settings),
        )
        response = service.delete_entities(user_id=user_id)
        return response.model_dump()


def _build_middlewares(
    settings: Settings,
    validator: OidcTokenValidator | None = None,
) -> list[Middleware]:
    if settings.auth_mode == "oidc":
        token_validator = validator or _build_oidc_validator(settings)
        return [OidcBearerMiddleware(token_validator=token_validator, subject_claim=settings.oidc_subject_claim)]
    if settings.auth_mode == "local":
        return [LocalUserMiddleware(settings.local_user_id)]
    return [UserHeaderMiddleware(settings.user_header_name)]


def create_server(
    settings: Settings | None = None,
    adapter: MemoryAdapter | None = None,
    health_checker: HealthChecker | None = None,
) -> FastMCP:
    app_settings = settings or Settings()
    app_adapter = adapter or Mem0Adapter(app_settings)
    app_health = health_checker or HealthChecker(app_settings)
    service = MemoryService(app_adapter)
    oidc_validator = _build_oidc_validator(app_settings) if app_settings.auth_mode == "oidc" else None
    auth_provider = _build_auth_provider(app_settings, validator=oidc_validator)

    mcp = FastMCP(
        "memoria",
        instructions=(
            "Standalone MCP server for mem0-backed user memory. "
            "In OIDC mode every tool call requires a valid bearer token and scopes data to that user. "
            "Stub auth x-user-id header mode is temporary and should only be used behind a trusted boundary. "
            "Local mode uses a fixed configured user id for local development only."
        ),
        auth=auth_provider,
        middleware=_build_middlewares(app_settings, validator=oidc_validator),
    )

    _register_health_route(mcp, app_health)
    _register_oidc_oauth_routes(mcp, app_settings)
    _register_memory_tools(mcp, service, app_settings)

    return mcp
