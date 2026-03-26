from __future__ import annotations

from urllib.parse import urlunsplit

import pytest
from pydantic import ValidationError

from memoria.settings import Settings

HTTP_SCHEME = "http"


def _http_url(authority: str, path: str = "") -> str:
    return urlunsplit((HTTP_SCHEME, authority, path, "", ""))


@pytest.fixture(autouse=True)
def _clean_memoria_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "MEMORIA_AUTH_MODE",
        "MEMORIA_OIDC_ISSUER_URL",
        "MEMORIA_OIDC_AUDIENCE",
        "MEMORIA_OIDC_SUBJECT_CLAIM",
    ):
        monkeypatch.delenv(key, raising=False)


def test_settings_accepts_legacy_mode_defaults() -> None:
    settings = Settings(auth_mode="legacy_header")
    assert settings.auth_mode == "legacy_header"


def test_settings_require_oidc_fields_in_oidc_mode() -> None:
    with pytest.raises(ValidationError):
        Settings(auth_mode="oidc")


def test_settings_accepts_oidc_mode_with_required_fields() -> None:
    settings = Settings(
        auth_mode="oidc",
        oidc_issuer_url=_http_url("keycloak:8080", "/realms/memoria"),
        oidc_audience="memoria-mcp",
    )
    assert settings.auth_mode == "oidc"
    assert settings.oidc_subject_claim == "sub"
    assert settings.oidc_jwks_cache_ttl_seconds == 300


def test_settings_default_auth_mode_is_legacy_header() -> None:
    settings = Settings()
    assert settings.auth_mode == "legacy_header"


def test_settings_accepts_oidc_mode_configuration() -> None:
    settings = Settings(
        auth_mode="oidc",
        oidc_issuer_url=_http_url("keycloak:8080", "/realms/memoria"),
        oidc_audience="memoria-mcp",
    )
    assert settings.auth_mode == "oidc"
