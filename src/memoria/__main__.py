from __future__ import annotations

from memoria.server import create_server
from memoria.settings import Settings


def main() -> None:
    settings = Settings()
    server = create_server(settings=settings)
    server.run(
        transport="streamable-http",
        host=settings.host,
        port=settings.port,
        path=settings.mcp_path,
    )


if __name__ == "__main__":
    main()

