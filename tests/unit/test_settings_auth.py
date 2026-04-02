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
        "MEMORIA_LOCAL_USER_ID",
        "MEMORIA_OIDC_ISSUER_URL",
        "MEMORIA_OIDC_AUDIENCE",
        "MEMORIA_OIDC_SUBJECT_CLAIM",
        "MEMORIA_MEM0_API_KEY",
        "MEMORIA_MEM0_LLM_API_KEY",
        "MEMORIA_MEM0_EMBEDDER_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def test_settings_accepts_stub_auth_mode() -> None:
    settings = Settings(auth_mode="stub_auth")
    assert settings.auth_mode == "stub_auth"


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


def test_settings_default_auth_mode_is_local() -> None:
    settings = Settings()
    assert settings.auth_mode == "local"
    assert settings.local_user_id == "local-user"


def test_settings_accepts_local_mode_configuration() -> None:
    settings = Settings(auth_mode="local", local_user_id="developer")
    assert settings.auth_mode == "local"
    assert settings.local_user_id == "developer"


def test_settings_rejects_blank_local_user_id_in_local_mode() -> None:
    with pytest.raises(ValidationError, match="MEMORIA_LOCAL_USER_ID must be non-empty"):
        Settings(auth_mode="local", local_user_id="   ")


def test_settings_accepts_oidc_mode_configuration() -> None:
    settings = Settings(
        auth_mode="oidc",
        oidc_issuer_url=_http_url("keycloak:8080", "/realms/memoria"),
        oidc_audience="memoria-mcp",
    )
    assert settings.auth_mode == "oidc"


def test_settings_reject_removed_mem0_api_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEMORIA_MEM0_API_KEY", "legacy-key")

    with pytest.raises(ValidationError, match="MEMORIA_MEM0_API_KEY has been removed"):
        Settings()


def test_settings_reject_removed_mem0_api_key_kwarg() -> None:
    with pytest.raises(ValidationError, match="MEMORIA_MEM0_API_KEY has been removed"):
        Settings(mem0_api_key="legacy-key")


def test_settings_ssl_verify_defaults_to_true() -> None:
    settings = Settings()
    assert settings.ssl_verify is True


def test_settings_ssl_verify_can_be_disabled() -> None:
    settings = Settings(ssl_verify=False)
    assert settings.ssl_verify is False


def test_settings_warn_when_dummy_keys_used_with_openai_providers(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("WARNING", logger="memoria.settings")

    Settings(
        mem0_llm_provider="openai",
        mem0_llm_api_key="dummy",
        mem0_llm_base_url="",
        mem0_embedder_provider="openai",
        mem0_embedder_api_key="dummy",
        mem0_embedder_base_url="",
    )

    assert "MEMORIA_MEM0_LLM_API_KEY uses default 'dummy'" in caplog.text
    assert "MEMORIA_MEM0_EMBEDDER_API_KEY uses default 'dummy'" in caplog.text
