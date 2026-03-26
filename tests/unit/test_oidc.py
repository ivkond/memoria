from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlunsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.utils import base64url_encode

import memoria.oidc as oidc_module
from memoria.oidc import OidcConfig, OidcTokenValidator, OidcTokenVerifier

HTTP_SCHEME = "http"


def _http_url(authority: str, path: str = "") -> str:
    return urlunsplit((HTTP_SCHEME, authority, path, "", ""))


def _make_rsa_keypair() -> tuple[Any, Any]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _jwk_from_public_key(public_key: Any, kid: str) -> dict[str, str]:
    numbers = public_key.public_numbers()
    return {
        "kty": "RSA",
        "kid": kid,
        "alg": "RS256",
        "use": "sig",
        "n": base64url_encode(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")).decode("ascii"),
        "e": base64url_encode(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")).decode("ascii"),
    }


def test_validate_token_happy_path() -> None:
    private_key, public_key = _make_rsa_keypair()
    issuer = _http_url("keycloak:8080", "/realms/memoria")
    audience = "memoria-mcp"
    kid = "k1"

    def fake_get_json(url: str, timeout_seconds: float = 5.0) -> dict[str, Any]:
        if url.endswith("/.well-known/openid-configuration"):
            return {"jwks_uri": f"{issuer}/protocol/openid-connect/certs"}
        return {"keys": [_jwk_from_public_key(public_key, kid)]}

    validator = OidcTokenValidator(
        OidcConfig(issuer_url=issuer, audience=audience, subject_claim="sub", jwks_ttl_seconds=300),
        get_json=fake_get_json,
    )
    token = jwt.encode(
        {"iss": issuer, "aud": audience, "sub": "alice-id", "iat": int(time.time()), "exp": int(time.time()) + 600},
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )

    claims = validator.validate(token)
    assert claims["sub"] == "alice-id"


def test_validate_token_rejects_wrong_audience() -> None:
    private_key, public_key = _make_rsa_keypair()
    issuer = _http_url("keycloak:8080", "/realms/memoria")
    kid = "k2"

    def fake_get_json(url: str, timeout_seconds: float = 5.0) -> dict[str, Any]:
        if url.endswith("/.well-known/openid-configuration"):
            return {"jwks_uri": f"{issuer}/protocol/openid-connect/certs"}
        return {"keys": [_jwk_from_public_key(public_key, kid)]}

    validator = OidcTokenValidator(
        OidcConfig(issuer_url=issuer, audience="memoria-mcp", subject_claim="sub", jwks_ttl_seconds=300),
        get_json=fake_get_json,
    )
    token = jwt.encode(
        {
            "iss": issuer,
            "aud": "other-audience",
            "sub": "alice-id",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )
    with pytest.raises(ValueError, match="invalid token"):
        validator.validate(token)


def test_validate_token_rejects_wrong_issuer() -> None:
    private_key, public_key = _make_rsa_keypair()
    kid = "k3"
    configured_issuer = _http_url("keycloak:8080", "/realms/memoria")

    def fake_get_json(url: str, timeout_seconds: float = 5.0) -> dict[str, Any]:
        if url.endswith("/.well-known/openid-configuration"):
            return {"jwks_uri": f"{configured_issuer}/protocol/openid-connect/certs"}
        return {"keys": [_jwk_from_public_key(public_key, kid)]}

    validator = OidcTokenValidator(
        OidcConfig(issuer_url=configured_issuer, audience="memoria-mcp", subject_claim="sub", jwks_ttl_seconds=300),
        get_json=fake_get_json,
    )
    token = jwt.encode(
        {
            "iss": _http_url("wrong-issuer", "/realms/memoria"),
            "aud": "memoria-mcp",
            "sub": "alice-id",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )
    with pytest.raises(ValueError, match="invalid token"):
        validator.validate(token)


def test_validate_token_rejects_invalid_signature() -> None:
    _, public_key_a = _make_rsa_keypair()
    private_key_b, _ = _make_rsa_keypair()
    issuer = _http_url("keycloak:8080", "/realms/memoria")
    kid = "k4"

    def fake_get_json(url: str, timeout_seconds: float = 5.0) -> dict[str, Any]:
        if url.endswith("/.well-known/openid-configuration"):
            return {"jwks_uri": f"{issuer}/protocol/openid-connect/certs"}
        return {"keys": [_jwk_from_public_key(public_key_a, kid)]}

    validator = OidcTokenValidator(
        OidcConfig(issuer_url=issuer, audience="memoria-mcp", subject_claim="sub", jwks_ttl_seconds=300),
        get_json=fake_get_json,
    )
    token = jwt.encode(
        {
            "iss": issuer,
            "aud": "memoria-mcp",
            "sub": "alice-id",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
        },
        private_key_b,
        algorithm="RS256",
        headers={"kid": kid},
    )
    with pytest.raises(ValueError, match="invalid token"):
        validator.validate(token)


def test_validate_token_rejects_missing_subject_claim() -> None:
    private_key, public_key = _make_rsa_keypair()
    issuer = _http_url("keycloak:8080", "/realms/memoria")
    kid = "k5"

    def fake_get_json(url: str, timeout_seconds: float = 5.0) -> dict[str, Any]:
        if url.endswith("/.well-known/openid-configuration"):
            return {"jwks_uri": f"{issuer}/protocol/openid-connect/certs"}
        return {"keys": [_jwk_from_public_key(public_key, kid)]}

    validator = OidcTokenValidator(
        OidcConfig(issuer_url=issuer, audience="memoria-mcp", subject_claim="sub", jwks_ttl_seconds=300),
        get_json=fake_get_json,
    )
    token = jwt.encode(
        {"iss": issuer, "aud": "memoria-mcp", "iat": int(time.time()), "exp": int(time.time()) + 600},
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )
    with pytest.raises(ValueError, match="invalid token claims"):
        validator.validate(token)


def test_validate_token_refreshes_jwks_for_unknown_kid() -> None:
    private_key, public_key = _make_rsa_keypair()
    issuer = _http_url("keycloak:8080", "/realms/memoria")
    calls = {"jwks": 0}

    def fake_get_json(url: str, timeout_seconds: float = 5.0) -> dict[str, Any]:
        if url.endswith("/.well-known/openid-configuration"):
            return {"jwks_uri": f"{issuer}/protocol/openid-connect/certs"}
        calls["jwks"] += 1
        return {"keys": [_jwk_from_public_key(public_key, "rotated-kid")]}

    validator = OidcTokenValidator(
        OidcConfig(issuer_url=issuer, audience="memoria-mcp", subject_claim="sub", jwks_ttl_seconds=300),
        get_json=fake_get_json,
    )
    token = jwt.encode(
        {
            "iss": issuer,
            "aud": "memoria-mcp",
            "sub": "alice-id",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "rotated-kid"},
    )
    claims = validator.validate(token)
    assert claims["sub"] == "alice-id"
    assert calls["jwks"] >= 1


def test_validate_token_rejects_expired_token() -> None:
    private_key, public_key = _make_rsa_keypair()
    issuer = _http_url("keycloak:8080", "/realms/memoria")
    kid = "k6"

    def fake_get_json(url: str, timeout_seconds: float = 5.0) -> dict[str, Any]:
        if url.endswith("/.well-known/openid-configuration"):
            return {"jwks_uri": f"{issuer}/protocol/openid-connect/certs"}
        return {"keys": [_jwk_from_public_key(public_key, kid)]}

    validator = OidcTokenValidator(
        OidcConfig(issuer_url=issuer, audience="memoria-mcp", subject_claim="sub", jwks_ttl_seconds=300),
        get_json=fake_get_json,
    )
    token = jwt.encode(
        {
            "iss": issuer,
            "aud": "memoria-mcp",
            "sub": "alice-id",
            "iat": int(time.time()) - 3600,
            "exp": int(time.time()) - 10,
        },
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )
    with pytest.raises(ValueError, match="invalid token"):
        validator.validate(token)


@pytest.mark.asyncio
async def test_verify_token_offloads_sync_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, Any] = {}

    class ThreadAwareValidator:
        def validate(self, token: str) -> dict[str, Any]:
            called["token"] = token
            return {
                "sub": "alice-id",
                "azp": "memoria-client",
                "scope": "read write",
                "exp": int(time.time()) + 60,
            }

    async def fake_to_thread(func: Any, /, *args: Any, **kwargs: Any) -> Any:
        called["offloaded"] = True
        return func(*args, **kwargs)

    verifier = OidcTokenVerifier(ThreadAwareValidator(), required_scopes=["read"], base_url="http://localhost:8080")
    monkeypatch.setattr(oidc_module, "asyncio", SimpleNamespace(to_thread=fake_to_thread), raising=False)

    token = await verifier.verify_token("token-1")

    assert token is not None
    assert token.client_id == "memoria-client"
    assert called == {"offloaded": True, "token": "token-1"}
