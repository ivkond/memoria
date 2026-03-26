from __future__ import annotations

import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.utils import base64url_encode

from memoria.oidc import OidcConfig, OidcTokenValidator


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
    issuer = "http://keycloak:8080/realms/memoria"
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
    issuer = "http://keycloak:8080/realms/memoria"
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
    configured_issuer = "http://keycloak:8080/realms/memoria"

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
            "iss": "http://wrong-issuer/realms/memoria",
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
    private_key_a, public_key_a = _make_rsa_keypair()
    private_key_b, _ = _make_rsa_keypair()
    issuer = "http://keycloak:8080/realms/memoria"
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
    issuer = "http://keycloak:8080/realms/memoria"
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
    issuer = "http://keycloak:8080/realms/memoria"
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
    issuer = "http://keycloak:8080/realms/memoria"
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
