# Memoria

[![CI](https://github.com/ivkond/memoria/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/ivkond/memoria/actions/workflows/ci.yml)
[![Bandit](https://github.com/ivkond/memoria/actions/workflows/bandit.yml/badge.svg?branch=master)](https://github.com/ivkond/memoria/actions/workflows/bandit.yml)
[![OSV-Scanner](https://github.com/ivkond/memoria/actions/workflows/osv-scanner.yml/badge.svg?branch=master)](https://github.com/ivkond/memoria/actions/workflows/osv-scanner.yml)
[![Trivy](https://github.com/ivkond/memoria/actions/workflows/trivy.yml/badge.svg?branch=master)](https://github.com/ivkond/memoria/actions/workflows/trivy.yml)
[![SonarCloud](https://sonarcloud.io/api/project_badges/measure?project=ivkond_memoria&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=ivkond_memoria)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/ivkond/memoria/blob/master/LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://github.com/ivkond/memoria/blob/master/pyproject.toml)

The missing self-hosted memory backend for MCP clients.

Unofficial, community-driven MCP server for mem0 OSS.

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

## 🔌 Connect from an MCP Client (OIDC)

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

OAuth metadata note:
- Memoria exposes MCP-facing OAuth metadata from its own public base URL for resource discovery.
- Browser-facing authorization, token, and JWKS endpoints still point at the configured Keycloak issuer.
- Generic RFC 8414 clients that expect `issuer` to match the upstream authorization server exactly may reject this layout; MCP clients should follow the advertised endpoints instead.
- `/oauth/register` is a fixed-client helper for MCP loopback callbacks and does not persist dynamic client registration back into Keycloak.
- Redirect URIs are limited to loopback `http` callbacks (`127.0.0.1`, `localhost`, `::1`); non-loopback hosts, `https` loopback, and native custom URL schemes need a different integration path.
- Token validation is currently Keycloak-oriented and expects RS256 JWKS signing keys.

## 🛡️ Security Boundary

In `oidc` mode, identity is derived from validated JWT claims (`sub` by default).

`legacy_header` mode remains available for migration only. In this mode `x-user-id` is an identity input, not authentication, and should be used only behind a trusted auth proxy/gateway.

Local Keycloak realm note:
- `deploy/keycloak/realm.json` includes a `memoria-e2e` client with direct access grants enabled for local-test only automation.
- Production realm imports should remove that client or disable direct access grants.

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
- `MEMORIA_PUBLIC_BASE_URL` (default `http://localhost:8080`)
- `MEMORIA_AUTH_MODE` (`legacy_header` or `oidc`)
- `MEMORIA_USER_HEADER_NAME`
- `MEMORIA_OIDC_ISSUER_URL` (required in `oidc` mode; expected `iss` in access token)
- `MEMORIA_OIDC_PUBLIC_ISSUER_URL` (optional; browser-facing issuer for OAuth metadata endpoints)
- `MEMORIA_OIDC_JWKS_URL` (optional; internal JWKS URL for server-side token verification)
- `MEMORIA_OIDC_AUDIENCE` (required in `oidc` mode)
- `MEMORIA_OIDC_SUBJECT_CLAIM` (default `sub`)
- `MEMORIA_OIDC_JWKS_CACHE_TTL_SECONDS` (default `300`)
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
- `MEMORIA_MEM0_LLM_API_KEY`
- `MEMORIA_MEM0_EMBEDDER_API_KEY`

Graph mode:
- `MEMORIA_MEM0_ENABLE_GRAPH` (`true`/`false`)
- `MEMORIA_MEM0_GRAPH_PROVIDER` (`memgraph`)
- `MEMORIA_MEM0_GRAPH_URL` (example: `bolt://memgraph:7687`)
- `MEMORIA_MEM0_GRAPH_USERNAME`
- `MEMORIA_MEM0_GRAPH_PASSWORD`

## ✅ Tests

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

- [ ] Add role/scope-based authorization for MCP tools (read/write/admin separation).
- [ ] Provide production deployment presets (Docker hardening + Kubernetes Helm chart).
- [ ] Add observability package (structured logs, Prometheus metrics, tracing).
- [ ] Expand integration examples for major MCP clients and providers.

## 📄 License

MIT
