from __future__ import annotations

from urllib.error import HTTPError

from memoria.health import HealthChecker
from memoria.schemas import HealthComponent
from memoria.settings import Settings


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


def test_probe_http_endpoint_marks_unauthorized_as_unavailable(monkeypatch) -> None:
    def fake_urlopen(*_args, **_kwargs):
        raise HTTPError(url="http://llm.local/models", code=401, msg="Unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr("memoria.health.urlopen", fake_urlopen)
    checker = HealthChecker(Settings())

    response = checker._probe_http_endpoint(name="llm", base_url="http://llm.local")

    assert response.ok is False
    assert "HTTP 401" in response.detail


def test_probe_http_endpoint_uses_insecure_ssl_context_when_verify_disabled(monkeypatch) -> None:
    captured_kwargs: dict = {}

    def fake_urlopen(*_args, **kwargs):
        captured_kwargs.update(kwargs)
        raise HTTPError(url="https://llm.local/models", code=200, msg="OK", hdrs=None, fp=None)

    monkeypatch.setattr("memoria.health.urlopen", fake_urlopen)
    checker = HealthChecker(Settings(ssl_verify=False))

    checker._probe_http_endpoint(name="llm", base_url="https://llm.local")

    import ssl
    ctx = captured_kwargs.get("context")
    assert ctx is not None
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_probe_http_endpoint_uses_default_ssl_when_verify_enabled(monkeypatch) -> None:
    captured_kwargs: dict = {}

    def fake_urlopen(*_args, **kwargs):
        captured_kwargs.update(kwargs)
        raise HTTPError(url="https://llm.local/models", code=200, msg="OK", hdrs=None, fp=None)

    monkeypatch.setattr("memoria.health.urlopen", fake_urlopen)
    checker = HealthChecker(Settings(ssl_verify=True))

    checker._probe_http_endpoint(name="llm", base_url="https://llm.local")

    assert captured_kwargs.get("context") is None
