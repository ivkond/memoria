from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LLM_KEY_SENTINEL = "${MEMORIA_MEM0_LLM_API_KEY:?set MEMORIA_MEM0_LLM_API_KEY in .env or the shell environment}"
EMBEDDER_KEY_SENTINEL = (
    "${MEMORIA_MEM0_EMBEDDER_API_KEY:?set MEMORIA_MEM0_EMBEDDER_API_KEY in .env or the shell environment}"
)


def test_compose_includes_keycloak_service() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "keycloak:" in compose
    assert 'profiles: ["oidc"]' in compose
    assert "start-dev" in compose
    assert "--import-realm" in compose
    assert "deploy/keycloak/realm.json" in compose
    assert "qdrant:" in compose
    assert "memgraph:" in compose


def test_env_example_lists_oidc_variables() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "MEMORIA_AUTH_MODE=" in env_example
    assert "MEMORIA_OIDC_ISSUER_URL=" in env_example
    assert "MEMORIA_OIDC_AUDIENCE=" in env_example


def test_compose_requires_mem0_api_keys() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert LLM_KEY_SENTINEL in compose
    assert EMBEDDER_KEY_SENTINEL in compose


def test_keycloak_realm_uses_pkce_for_public_client_and_separate_direct_grants_client() -> None:
    realm = json.loads((ROOT / "deploy" / "keycloak" / "realm.json").read_text(encoding="utf-8"))
    clients = {client["clientId"]: client for client in realm["clients"]}

    public_client = clients["memoria-mcp"]
    assert public_client["standardFlowEnabled"] is True
    assert public_client["directAccessGrantsEnabled"] is False

    e2e_client = clients["memoria-e2e"]
    assert e2e_client["directAccessGrantsEnabled"] is True
    assert e2e_client["publicClient"] is True
    assert "production" in e2e_client["description"].lower()
    assert "local e2e only" in e2e_client["description"].lower()


def test_readme_contains_bearer_auth_example() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "authorization" in readme
    assert "bearer <access_token>" in readme
    assert "keycloak" in readme


def test_readme_calls_out_mcp_metadata_and_test_only_e2e_client() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "oauth metadata" in readme
    assert "issuer" in readme
    assert "memoria-e2e" in readme
    assert "local-test only" in readme
    assert "does not persist dynamic client registration" in readme
    assert "loopback" in readme
    assert "rs256" in readme
