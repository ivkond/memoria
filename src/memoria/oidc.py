from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx
import jwt
from fastmcp.server.auth import AccessToken, TokenVerifier

INVALID_TOKEN_MESSAGE = "invalid token"


@dataclass(frozen=True)
class OidcConfig:
    issuer_url: str
    audience: str
    subject_claim: str = "sub"
    jwks_url: str | None = None
    jwks_ttl_seconds: int = 300


class JwksCache:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._keys: dict[str, Any] = {}
        self._expires_at: float = 0.0

    def get(self, kid: str) -> Any | None:
        with self._lock:
            if time.time() > self._expires_at:
                return None
            return self._keys.get(kid)

    def set_many(self, keys: dict[str, Any], ttl_seconds: int) -> None:
        with self._lock:
            self._keys = keys
            self._expires_at = time.time() + ttl_seconds


class OidcTokenValidator:
    def __init__(
        self,
        config: OidcConfig,
        get_json: Callable[[str, float], dict[str, Any]] | None = None,
    ) -> None:
        self._config = config
        self._cache = JwksCache()
        self._get_json = get_json or self._default_get_json
        self._jwks_url = config.jwks_url

    @staticmethod
    def _default_get_json(url: str, timeout_seconds: float = 5.0) -> dict[str, Any]:
        response = httpx.get(url, timeout=timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("invalid OIDC response payload")
        return payload

    def _resolve_jwks_url(self) -> str:
        if self._jwks_url:
            return self._jwks_url

        metadata_url = f"{self._config.issuer_url}/.well-known/openid-configuration"
        metadata = self._get_json(metadata_url, 5.0)
        jwks_uri = metadata.get("jwks_uri")
        if not isinstance(jwks_uri, str) or not jwks_uri:
            raise ValueError("invalid OIDC metadata")
        self._jwks_url = jwks_uri
        return jwks_uri

    def _refresh_jwks(self) -> None:
        jwks = self._get_json(self._resolve_jwks_url(), 5.0)
        parsed: dict[str, Any] = {}

        for key_entry in jwks.get("keys", []):
            if not isinstance(key_entry, dict):
                continue
            kid = key_entry.get("kid")
            if isinstance(kid, str) and kid:
                parsed[kid] = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_entry))

        if not parsed:
            raise ValueError("invalid jwks")
        self._cache.set_many(parsed, self._config.jwks_ttl_seconds)

    def _get_key_for_kid(self, kid: str) -> Any:
        key = self._cache.get(kid)
        if key is not None:
            return key

        self._refresh_jwks()
        key = self._cache.get(kid)
        if key is None:
            raise ValueError(INVALID_TOKEN_MESSAGE)
        return key

    def validate(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not isinstance(kid, str) or not kid:
                raise ValueError(INVALID_TOKEN_MESSAGE)

            key = self._get_key_for_kid(kid)
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=self._config.audience,
                issuer=self._config.issuer_url,
                # nbf is validated by PyJWT automatically when present.
                options={"require": ["exp"]},
            )
        except jwt.PyJWTError as error:
            raise ValueError(INVALID_TOKEN_MESSAGE) from error

        subject = claims.get(self._config.subject_claim)
        if not isinstance(subject, str) or not subject.strip():
            raise ValueError("invalid token claims")

        return claims


def _extract_scopes(claims: dict[str, Any]) -> list[str]:
    scope_value = claims.get("scope")
    if isinstance(scope_value, str):
        return [scope for scope in scope_value.split() if scope]

    scp_value = claims.get("scp")
    if isinstance(scp_value, list):
        return [str(scope) for scope in scp_value if str(scope).strip()]

    return []


class OidcTokenVerifier(TokenVerifier):
    def __init__(
        self,
        token_validator: OidcTokenValidator,
        *,
        required_scopes: list[str] | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(base_url=base_url, required_scopes=required_scopes)
        self._token_validator = token_validator

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = await asyncio.to_thread(self._token_validator.validate, token)
        except ValueError:
            return None

        scopes = _extract_scopes(claims)
        if self.required_scopes:
            required = set(self.required_scopes)
            if not required.issubset(set(scopes)):
                return None

        raw_client_id = claims.get("azp") or claims.get("client_id") or "unknown-client"
        client_id = str(raw_client_id)
        expires_at = claims.get("exp")
        normalized_expires_at = int(expires_at) if isinstance(expires_at, int | float) else None

        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=scopes,
            expires_at=normalized_expires_at,
            claims=claims,
        )
