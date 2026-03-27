# Memoria

[![CI](https://github.com/ivkond/memoria/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/ivkond/memoria/actions/workflows/ci.yml)
[![Bandit](https://github.com/ivkond/memoria/actions/workflows/bandit.yml/badge.svg?branch=master)](https://github.com/ivkond/memoria/actions/workflows/bandit.yml)
[![OSV-Scanner](https://github.com/ivkond/memoria/actions/workflows/osv-scanner.yml/badge.svg?branch=master)](https://github.com/ivkond/memoria/actions/workflows/osv-scanner.yml)
[![Trivy](https://github.com/ivkond/memoria/actions/workflows/trivy.yml/badge.svg?branch=master)](https://github.com/ivkond/memoria/actions/workflows/trivy.yml)
[![SonarCloud](https://sonarcloud.io/api/project_badges/measure?project=ivkond_memoria&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=ivkond_memoria)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/ivkond/memoria/blob/master/LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://github.com/ivkond/memoria/blob/master/pyproject.toml)

The missing self-hosted memory backend for MCP clients.

Community-maintained MCP server for mem0 OSS.

If you like mem0 but need it in MCP clients today, Memoria closes that gap:
- 🌐 Streamable HTTP MCP endpoint
- 👤 Per-user memory scoping for trusted internal deployments
- 🐳 Drop-in Docker setup with Qdrant
- 🕸️ Optional graph memory via Memgraph

> Why this project exists: there is no official MCP server in mem0 OSS that you can run as a standalone service in your stack. Memoria gives you that bridge now.

## ✨ What You Get

- MCP tools for storing, searching, updating, and deleting memory
- OIDC bearer token auth (Keycloak-compatible) with per-user scoping from token claims
- Ownership checks for ID-based read/update/delete operations
- Health endpoint with Qdrant, Memgraph, LLM, and embedder dependency checks
- mem0-backed memory with pluggable LLM/embedder providers
- Optional graph relations support when graph mode is enabled

## 🚀 Quickstart (Docker, Recommended)

```bash
# Copy .env.example to .env and put rotated provider keys there first
docker compose up -d --build

# Optional: start bundled Keycloak profile for local OIDC
docker compose --profile oidc up -d keycloak
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

### OIDC mode

```json
{
  "mcpServers": {
    "memoria": {
      "type": "streamable-http",
      "url": "http://localhost:8080/mcp",
      "headers": {
        "authorization": "Bearer <access_token>"
      }
    }
  }
}
```

Without a bearer token, requests are rejected.

For local Keycloak profile, issuer is `http://localhost:18081/realms/memoria`.

OAuth metadata layout, the fact that `/oauth/register` does not persist dynamic client registration, loopback redirect constraints, RS256/Keycloak assumptions, and other auth details are documented in [docs/auth.md](docs/auth.md).

### `local` mode

This is the default for local development. In local mode Memoria skips client authentication entirely and scopes all tools to a fixed configured user id (`MEMORIA_LOCAL_USER_ID`, default `local-user`).

```json
{
  "mcpServers": {
    "memoria": {
      "type": "streamable-http",
      "url": "http://localhost:8080/mcp"
    }
  }
}
```

### `stub_auth` mode

Use this only behind a trusted auth proxy or during migration. In this mode the client passes user identity via `x-user-id` instead of a bearer token.

```json
{
  "mcpServers": {
    "memoria": {
      "type": "streamable-http",
      "url": "http://localhost:8080/mcp",
      "headers": {
        "x-user-id": "alice"
      }
    }
  }
}
```

## 🛡️ Security Boundary

In `oidc` mode, identity is derived from validated JWT claims (`sub` by default).

In `local` mode, Memoria does not authenticate the client and always uses `MEMORIA_LOCAL_USER_ID`. Use it only for local development.

`stub_auth` mode remains available for migration only. In this mode `x-user-id` is an identity input, not authentication, and should be used only behind a trusted auth proxy/gateway.

Local Keycloak realm note:
- `deploy/keycloak/realm.json` includes a `memoria-e2e` client with direct access grants enabled for local-test only automation.
- Production realm imports should remove that client or disable direct access grants.

## 🧰 MCP Tools

All tools are scoped to the current user identity from the bearer token, the configured local user id, or the `x-user-id` header depending on auth mode.

| Tool | Required args | What it does | Returns |
| --- | --- | --- | --- |
| `add_memory` | `text` | Stores a new memory. If `messages` is omitted, the server wraps `text` into a single user message. | mem0 add response for the created memory item(s) |
| `search_memories` | `query` | Runs semantic search over the current user's memories. Supports `limit`, `filters`, `threshold`, and `rerank`. | mem0 search response with matching results |
| `get_memory` | `memory_id` | Returns one memory by ID if it belongs to the current user. | single memory object or `null` |
| `get_memories` | none | Lists memories for the current user. Supports `limit` and `filters`. | mem0 list response with memory items |
| `update_memory` | `memory_id`, `data` | Updates the text payload of an existing memory owned by the current user. | mem0 update response |
| `delete_memory` | `memory_id` | Deletes one memory owned by the current user. | mem0 delete response |
| `delete_all_memories` | none | Deletes all memories for the current user scope. | mem0 bulk delete response |
| `list_entities` | none | Returns graph relations from mem0 when graph mode is enabled. Supports `limit`. | `{ user_id, relations, supported, detail }` |
| `delete_entities` | none | Deletes entities for the current user. In mem0 OSS this is mapped to `delete_all_memories`. | `{ user_id, detail, result }` |

## 🏗️ Architecture

Memoria is intentionally simple:

```text
MCP client -> FastMCP server -> mem0 -> Qdrant
                                  |
                                  +-> Memgraph (optional graph memory)
```

That keeps the deployment easy to reason about and straightforward to self-host.

## ⚙️ Configuration

Start from [.env.example](.env.example). Most local setups only need auth mode, provider keys, and either the default Docker services or a reachable Qdrant/LLM/embedder stack.

### Server and auth

| Var | Default | Required | Description |
| --- | --- | --- | --- |
| `MEMORIA_HOST` | `0.0.0.0` | no | Bind host for the HTTP server |
| `MEMORIA_PORT` | `8080` | no | Bind port for the HTTP server |
| `MEMORIA_MCP_PATH` | `/mcp` | no | MCP endpoint path |
| `MEMORIA_PUBLIC_BASE_URL` | `http://localhost:8080` | no | Public base URL used in advertised MCP/OAuth metadata |
| `MEMORIA_AUTH_MODE` | `local` | no | Auth mode: `local`, `stub_auth`, or `oidc` |
| `MEMORIA_LOCAL_USER_ID` | `local-user` | no | Fixed user id used in `local` mode |
| `MEMORIA_USER_HEADER_NAME` | `x-user-id` | no | Identity header used in `stub_auth` mode |
| `MEMORIA_OIDC_ISSUER_URL` | none | in `oidc` mode | Expected token issuer and default upstream OIDC issuer |
| `MEMORIA_OIDC_PUBLIC_ISSUER_URL` | none | no | Browser-facing issuer for advertised OAuth endpoints |
| `MEMORIA_OIDC_JWKS_URL` | none | no | Optional internal JWKS URL for server-side verification |
| `MEMORIA_OIDC_AUDIENCE` | none | in `oidc` mode | Expected access token audience |
| `MEMORIA_OIDC_SUBJECT_CLAIM` | `sub` | no | Claim used as the per-user identity |
| `MEMORIA_OIDC_REQUIRED_SCOPES` | none | no | Optional space-separated scopes enforced by the verifier |
| `MEMORIA_OIDC_JWKS_CACHE_TTL_SECONDS` | `300` | no | JWKS cache TTL in seconds |
| `MEMORIA_LOG_LEVEL` | `INFO` | no | Application log level |

### Qdrant

| Var | Default | Required | Description |
| --- | --- | --- | --- |
| `MEMORIA_QDRANT_HOST` | `qdrant` | no | Qdrant host when not using a full URL |
| `MEMORIA_QDRANT_PORT` | `6333` | no | Qdrant port when not using a full URL |
| `MEMORIA_QDRANT_URL` | none | no | Full Qdrant URL; overrides host/port mode |
| `MEMORIA_QDRANT_API_KEY` | none | no | API key for managed Qdrant deployments |
| `MEMORIA_QDRANT_COLLECTION_NAME` | `mem0` | no | Collection name used by mem0 |
| `MEMORIA_QDRANT_EMBEDDING_DIMS` | `1536` | no | Embedding dimension size for the collection |
| `MEMORIA_QDRANT_ON_DISK` | `false` | no | Enables on-disk Qdrant storage mode |

### mem0, LLM, and embedder

| Var | Default | Required | Description |
| --- | --- | --- | --- |
| `MEMORIA_MEM0_VERSION` | `v1.1` | no | mem0 API/config version passed to the SDK |
| `MEMORIA_MEM0_HISTORY_DB_PATH` | `./data/mem0_history.db` | no | Local history DB path used by mem0 |
| `MEMORIA_MEM0_LLM_PROVIDER` | `vllm` | no | LLM provider passed to mem0 |
| `MEMORIA_MEM0_LLM_MODEL` | `gpt-4o-mini` | no | LLM model name |
| `MEMORIA_MEM0_LLM_BASE_URL` | empty | no | Optional base URL override for the LLM provider |
| `MEMORIA_MEM0_LLM_API_KEY` | `dummy` | no | LLM API key; local OpenAI-compatible stacks can use any non-empty value |
| `MEMORIA_MEM0_EMBEDDER_PROVIDER` | `openai` | no | Embedder provider passed to mem0 |
| `MEMORIA_MEM0_EMBEDDER_MODEL` | `text-embedding-3-small` | no | Embedder model name |
| `MEMORIA_MEM0_EMBEDDER_BASE_URL` | empty | no | Optional base URL override for the embedder provider |
| `MEMORIA_MEM0_EMBEDDER_API_KEY` | `dummy` | no | Embedder API key; local compatible stacks can use any non-empty value |

### Optional graph mode

| Var | Default | Required | Description |
| --- | --- | --- | --- |
| `MEMORIA_MEM0_ENABLE_GRAPH` | `false` | no | Enables graph memory support in mem0 |
| `MEMORIA_MEM0_GRAPH_PROVIDER` | `memgraph` | no | Graph provider name |
| `MEMORIA_MEM0_GRAPH_URL` | `bolt://memgraph:7687` | when graph enabled | Memgraph connection URL |
| `MEMORIA_MEM0_GRAPH_USERNAME` | `memgraph` | when graph enabled | Memgraph username |
| `MEMORIA_MEM0_GRAPH_PASSWORD` | `memgraph` | when graph enabled | Memgraph password |

## ✅ Quality & Tests

Quality checks:

```bash
python -m ruff check .
python -m mypy src
```

Unit tests:

```bash
python -m pytest -q tests/unit --cov=src/memoria --cov-report=term-missing
```

E2E tests (Docker + Testcontainers):

```bash
RUN_E2E=1 python -m pytest -q tests/e2e
```

<details>
<summary>PowerShell</summary>

```powershell
$env:RUN_E2E='1'
python -m pytest -q tests/e2e
```

</details>

## 📍 Positioning and Scope

- This project is community-maintained.
- It is focused on practical integration and fast self-hosting.
- It does not claim affiliation with mem0.

## 🧭 Roadmap

- Planned role/scope-based authorization for MCP tools with read/write/admin separation
- Planned production deployment presets, including Docker hardening and Kubernetes Helm charts
- Planned observability package with structured logs, Prometheus metrics, and tracing
- Planned integration examples for additional MCP clients and providers

## 📄 License

MIT
