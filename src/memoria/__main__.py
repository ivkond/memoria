from __future__ import annotations

import logging
import sys

from memoria.server import create_server
from memoria.settings import Settings


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )


def main() -> None:
    settings = Settings()
    setup_logging(settings.log_level)
    server = create_server(settings=settings)
    server.run(
        transport="streamable-http",
        host=settings.host,
        port=settings.port,
        path=settings.mcp_path,
    )


if __name__ == "__main__":
    main()
