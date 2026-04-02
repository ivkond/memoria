from __future__ import annotations

import logging
import sys

import memoria.__main__ as main_module


def test_setup_logging_configures_basic_config(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_basic_config(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(main_module.logging, "basicConfig", fake_basic_config)

    main_module.setup_logging("warning")

    assert captured["level"] == logging.WARNING
    assert captured["format"] == "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    assert captured["datefmt"] == "%Y-%m-%d %H:%M:%S"
    assert captured["stream"] is sys.stdout


def test_main_sets_up_logging_and_runs_server(monkeypatch) -> None:
    events: dict[str, object] = {}

    class FakeSettings:
        host = "127.0.0.1"
        port = 8090
        mcp_path = "/mcp-test"
        log_level = "debug"

    class FakeServer:
        def run(self, **kwargs) -> None:
            events["run_kwargs"] = kwargs

    def fake_setup_logging(level: str) -> None:
        events["log_level"] = level

    monkeypatch.setattr(main_module, "Settings", lambda: FakeSettings())
    monkeypatch.setattr(main_module, "setup_logging", fake_setup_logging)
    monkeypatch.setattr(main_module, "create_server", lambda settings: FakeServer())

    main_module.main()

    assert events["log_level"] == "debug"
    assert events["run_kwargs"] == {
        "transport": "streamable-http",
        "host": "127.0.0.1",
        "port": 8090,
        "path": "/mcp-test",
    }
