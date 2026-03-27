# Authentication and OAuth Notes

Memoria supports two authentication modes:

- `oidc`: validates bearer tokens and derives user identity from a JWT claim such as `sub`
- `legacy_header`: trusts an upstream proxy or gateway to inject a user header such as `x-user-id`

For production deployments, prefer `oidc`. Use `legacy_header` only behind a trusted boundary or during migration.

## OIDC Metadata Layout

Memoria exposes MCP-facing OAuth metadata from its own public base URL so MCP clients can discover the resource server correctly.

At the same time, browser-facing authorization, token, and JWKS endpoints still point at the configured upstream OIDC issuer, such as Keycloak. This means the advertised OAuth metadata is intentionally split across:

- the Memoria public base URL for resource discovery
- the upstream issuer for authorization, token, and JWKS endpoints

Some generic RFC 8414 clients expect the metadata `issuer` to match the upstream authorization server exactly and may reject this layout. MCP clients should follow the advertised endpoints instead.

## `/oauth/register`

`/oauth/register` is a fixed-client helper for loopback callback flows used by MCP clients. It is not full dynamic client registration and does not persist new clients back into Keycloak.

Accepted redirect URIs are limited to loopback `http` callbacks:

- `http://127.0.0.1/...`
- `http://localhost/...`
- `http://[::1]/...`

Non-loopback hosts, `https` loopback callbacks, and native custom URL schemes require a different integration path.

## Keycloak-Oriented Assumptions

Current token validation is Keycloak-oriented and expects RS256 JWKS signing keys.

For the bundled local profile:

- issuer: `http://localhost:18081/realms/memoria`
- local realm file: `deploy/keycloak/realm.json`
- included `memoria-e2e` client is intended for local test automation only

Production realm imports should remove that client or disable direct access grants.

## `legacy_header` Mode

In `legacy_header` mode, the configured header is an identity input, not authentication. Anyone who can send that header can impersonate a user unless a trusted proxy strips and rewrites it first.
