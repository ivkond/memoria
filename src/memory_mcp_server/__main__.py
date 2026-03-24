from __future__ import annotations

from memory_mcp_server.server import create_server
from memory_mcp_server.settings import Settings


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

