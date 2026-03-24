from __future__ import annotations

from memory_mcp_server.health import HealthChecker
from memory_mcp_server.schemas import HealthComponent
from memory_mcp_server.settings import Settings


def test_health_status_ok_when_all_checks_pass(monkeypatch) -> None:
    checker = HealthChecker(Settings())
    monkeypatch.setattr(checker, "check_qdrant", lambda: HealthComponent(ok=True, detail="ok"))
    monkeypatch.setattr(checker, "check_memgraph", lambda: HealthComponent(ok=True, detail="ok"))
    monkeypatch.setattr(checker, "check_llm", lambda: HealthComponent(ok=True, detail="ok"))
    monkeypatch.setattr(checker, "check_embedder", lambda: HealthComponent(ok=True, detail="ok"))

    response = checker.check()

    assert response.status == "ok"
    assert response.checks["qdrant"].ok is True
    assert response.checks["memgraph"].ok is True
    assert "postgres" not in response.checks


def test_health_status_degraded_when_any_check_fails(monkeypatch) -> None:
    checker = HealthChecker(Settings())
    monkeypatch.setattr(checker, "check_qdrant", lambda: HealthComponent(ok=False, detail="down"))
    monkeypatch.setattr(checker, "check_memgraph", lambda: HealthComponent(ok=True, detail="ok"))
    monkeypatch.setattr(checker, "check_llm", lambda: HealthComponent(ok=True, detail="ok"))
    monkeypatch.setattr(checker, "check_embedder", lambda: HealthComponent(ok=True, detail="ok"))

    response = checker.check()

    assert response.status == "degraded"
    assert response.checks["qdrant"].ok is False


def test_memgraph_check_skips_when_disabled() -> None:
    checker = HealthChecker(Settings(mem0_enable_graph=False))

    response = checker.check_memgraph()

    assert response.ok is True
    assert response.detail == "graph disabled"


def test_health_status_degraded_when_llm_or_embedder_unavailable(monkeypatch) -> None:
    checker = HealthChecker(Settings())
    monkeypatch.setattr(checker, "check_qdrant", lambda: HealthComponent(ok=True, detail="ok"))
    monkeypatch.setattr(checker, "check_memgraph", lambda: HealthComponent(ok=True, detail="ok"))
    monkeypatch.setattr(checker, "check_llm", lambda: HealthComponent(ok=False, detail="down"))
    monkeypatch.setattr(checker, "check_embedder", lambda: HealthComponent(ok=True, detail="ok"))

    response = checker.check()

    assert response.status == "degraded"
    assert response.checks["llm"].ok is False
    assert response.checks["embedder"].ok is True
