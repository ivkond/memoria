# memory-mcp-server

Standalone MCP server built with `FastMCP` and `mem0` for on-prem memory.

## What it does

- Exposes memory tools over MCP Streamable HTTP.
- Requires `x-user-id` header on every tool call.
- Scopes all operations to that user.
- Uses `Qdrant` for vector memory and checks `Qdrant` (+ `MemGraph` when enabled) in `/health`.
- Supports optional MemGraph-based graph memory when enabled.

## Tools

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
- `list_entities` returns graph relations from `get_all` when graph mode is enabled.
- `delete_entities` is mapped to `delete_all_memories` for current `x-user-id`.
- MemGraph runtime requires `langchain-memgraph` and `rank-bm25` (included in this project).

## Run locally

```bash
python -m pip install -e .[dev]
python -m memory_mcp_server
```

Server defaults:
- MCP endpoint: `http://0.0.0.0:8080/mcp`
- Health: `http://0.0.0.0:8080/health`

## Docker compose

```bash
docker compose up -d --build
```

If MCP runs in Docker and `vLLM` runs on host machine, keep base URLs like
`http://host.docker.internal:8000/v1`. For Linux Docker Engine this project
already adds `host-gateway` mapping in compose.

## Run tests

Unit tests:

```bash
python -m pytest -q
```

E2E integration tests (Docker + Testcontainers required):

```bash
$env:RUN_E2E='1'  # PowerShell
python -m pytest -q tests/e2e
```

## Key environment variables

- `MEMORY_MCP_HOST`
- `MEMORY_MCP_PORT`
- `MEMORY_MCP_MCP_PATH`
- `MEMORY_MCP_USER_HEADER_NAME`
- `MEMORY_MCP_QDRANT_HOST`
- `MEMORY_MCP_QDRANT_PORT`
- `MEMORY_MCP_MEM0_LLM_PROVIDER` (`vllm` or `openai`)
- `MEMORY_MCP_MEM0_LLM_BASE_URL`
- `MEMORY_MCP_MEM0_LLM_MODEL`
- `MEMORY_MCP_MEM0_EMBEDDER_PROVIDER`
- `MEMORY_MCP_MEM0_EMBEDDER_BASE_URL`
- `MEMORY_MCP_MEM0_EMBEDDER_MODEL`
- `MEMORY_MCP_MEM0_LLM_API_KEY` (optional, overrides common key for LLM)
- `MEMORY_MCP_MEM0_EMBEDDER_API_KEY` (optional, overrides common key for embedder)
- `MEMORY_MCP_MEM0_API_KEY`
- `MEMORY_MCP_MEM0_ENABLE_GRAPH` (`true`/`false`)
- `MEMORY_MCP_MEM0_GRAPH_PROVIDER` (`memgraph`)
- `MEMORY_MCP_MEM0_GRAPH_URL` (example: `bolt://memgraph:7687`)
- `MEMORY_MCP_MEM0_GRAPH_USERNAME`
- `MEMORY_MCP_MEM0_GRAPH_PASSWORD`

API key behavior:
- If `MEMORY_MCP_MEM0_LLM_API_KEY` / `MEMORY_MCP_MEM0_EMBEDDER_API_KEY` are set, they are used respectively.
- Otherwise server falls back to `MEMORY_MCP_MEM0_API_KEY`.

## Enable MemGraph

Set:

- `MEMORY_MCP_MEM0_ENABLE_GRAPH=true`
- `MEMORY_MCP_MEM0_GRAPH_PROVIDER=memgraph`
- `MEMORY_MCP_MEM0_GRAPH_URL=bolt://memgraph:7687`
- `MEMORY_MCP_MEM0_GRAPH_USERNAME=memgraph`
- `MEMORY_MCP_MEM0_GRAPH_PASSWORD=memgraph`

Then restart:

```bash
docker compose up -d --build
```

## Example MCP client config

```json
{
  "mcpServers": {
    "memory": {
      "type": "streamable-http",
      "url": "http://localhost:8080/mcp",
      "headers": {
        "x-user-id": "employee-001"
      }
    }
  }
}
```
