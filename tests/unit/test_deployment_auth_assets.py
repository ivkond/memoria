from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


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


def test_readme_contains_bearer_auth_example() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "authorization" in readme
    assert "bearer <access_token>" in readme
    assert "keycloak" in readme
