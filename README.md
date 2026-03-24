# Memoria

Unofficial, community-driven MCP server for mem0 OSS.

If you like mem0 but need it in MCP clients today, Memoria closes that gap:
- 🌐 Streamable HTTP MCP endpoint
- 👤 Per-user memory scoping for trusted internal deployments
- 🐳 Drop-in Docker setup with Qdrant
- 🕸️ Optional graph memory via Memgraph

> Why this project exists: there is no official MCP server in mem0 OSS that you can run as a standalone service in your stack. Memoria gives you that bridge now.

## ✨ What You Get

- MCP tools for storing, searching, updating, and deleting memory
- Required `x-user-id` header for per-user scoping behind a trusted auth boundary
- Ownership checks for ID-based read/update/delete operations
- Health endpoint with Qdrant, Memgraph, LLM, and embedder dependency checks
- mem0-backed memory with pluggable LLM/embedder providers
- Optional graph relations support when graph mode is enabled

## 🚀 Quickstart (Docker, Recommended)

```bash
# Copy .env.example to .env and put rotated provider keys there first
docker compose up -d --build
```

Available endpoints:
- MCP: `http://localhost:8080/mcp`
- Health: `http://localhost:8080/health`
- Memgraph Lab UI: `http://localhost:3000`

## 🐍 Quickstart (Local Python)

```bash
python -m pip install -e .[dev]
python -m memoria
```

Defaults:
- MCP: `http://0.0.0.0:8080/mcp`
- Health: `http://0.0.0.0:8080/health`

## 🔌 Connect from an MCP Client

```json
{
  "mcpServers": {
    "memoria": {
      "type": "streamable-http",
      "url": "http://localhost:8080/mcp",
      "headers": {
        "x-user-id": "employee-001"
      }
    }
  }
}
```

Without `x-user-id`, requests are rejected.

## 🛡️ Security Boundary

`x-user-id` is an identity input, not authentication.

Use Memoria only behind a trusted auth proxy or gateway that authenticates the caller and injects `x-user-id`. Direct external exposure is not a supported security model. Inside that trusted perimeter, the server enforces ownership checks for all `memory_id`-based operations so one user cannot read, update, or delete another user's memory by ID alone.

## 🧰 MCP Tools

- `add_memory`
- `search_memories`
- `get_memory`
- `get_memories`
- `update_memory`
- `delete_memory`
- `delete_all_memories`
- `list_entities`
- `delete_entities`

Notes:
- In mem0 OSS SDK, dedicated entity APIs are not exposed as separate methods.
- `list_entities` reads graph relations returned by mem0 when graph store is enabled.
- `delete_entities` is mapped to `delete_all_memories` in this server.

## 🏗️ Architecture

Memoria is intentionally simple:
- FastMCP server (`streamable-http`)
- mem0 as memory engine
- Qdrant as vector store
- Optional Memgraph for graph memory

This keeps operations transparent and makes it easy to self-host.

## ⚙️ Configuration

Core env vars:
- `MEMORIA_HOST`
- `MEMORIA_PORT`
- `MEMORIA_MCP_PATH`
- `MEMORIA_USER_HEADER_NAME`
- `MEMORIA_QDRANT_HOST`
- `MEMORIA_QDRANT_PORT`
- `MEMORIA_QDRANT_COLLECTION_NAME`

mem0/LLM/embedder:
- `MEMORIA_MEM0_LLM_PROVIDER` (`vllm` or `openai`)
- `MEMORIA_MEM0_LLM_BASE_URL`
- `MEMORIA_MEM0_LLM_MODEL`
- `MEMORIA_MEM0_EMBEDDER_PROVIDER`
- `MEMORIA_MEM0_EMBEDDER_BASE_URL`
- `MEMORIA_MEM0_EMBEDDER_MODEL`
- `MEMORIA_MEM0_API_KEY`
- `MEMORIA_MEM0_LLM_API_KEY` (optional override)
- `MEMORIA_MEM0_EMBEDDER_API_KEY` (optional override)

Graph mode:
- `MEMORIA_MEM0_ENABLE_GRAPH` (`true`/`false`)
- `MEMORIA_MEM0_GRAPH_PROVIDER` (`memgraph`)
- `MEMORIA_MEM0_GRAPH_URL` (example: `bolt://memgraph:7687`)
- `MEMORIA_MEM0_GRAPH_USERNAME`
- `MEMORIA_MEM0_GRAPH_PASSWORD`

## ✅ Tests

Unit tests:

```bash
python -m pytest -q
```

E2E tests (Docker + Testcontainers):

```bash
# PowerShell
$env:RUN_E2E='1'
python -m pytest -q tests/e2e
```

```bash
# Bash
RUN_E2E=1 python -m pytest -q tests/e2e
```

## 📍 Positioning and Scope

- This project is an unofficial MCP bridge maintained by the community.
- It is focused on practical integration and fast self-hosting.
- It does not claim affiliation with mem0.

## 🧭 TODO

- [ ] Rework authentication to OAuth-based auth flow.
- [ ] Add role/scope-based authorization for MCP tools (read/write/admin separation).
- [ ] Provide production deployment presets (Docker hardening + Kubernetes Helm chart).
- [ ] Add observability package (structured logs, Prometheus metrics, tracing).
- [ ] Expand integration examples for major MCP clients and providers.

## 📄 License

MIT
