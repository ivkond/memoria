# OIDC/SSO (Keycloak) Authentication Design For Memoria

Date: 2026-03-26
Status: Approved (design phase)
Owner: Memoria maintainers

## 1. Context

Current Memoria identity scoping uses `x-user-id` from a trusted upstream proxy.
This worked for MVP but is not acceptable for direct remote MCP usage where the user configures the connection and authentication should be first-class.

We are replacing this with OIDC bearer token validation in Memoria itself, using Keycloak as the identity provider.

## 2. Goals

1. Replace `x-user-id` identity input with validated OIDC access tokens.
2. Validate JWTs locally via Keycloak JWKS (no per-request introspection).
3. Extract user identity from a token claim (`sub` by default).
4. Keep user memory isolation guarantees across all MCP tools.
5. Provide a ready local/dev environment with Keycloak in Docker Compose and preloaded test realm/users.

## 3. Non-Goals

1. Instant token revocation support (not required).
2. Full role/scope-based authorization rollout in this iteration.
3. Breaking removal of legacy header mode in the same release.

## 4. Chosen Approach

Selected option: local JWT self-validation with JWKS (recommended option 1).

Why:

1. Fits remote user MCP scenario.
2. Avoids Keycloak call on every tool invocation.
3. Simpler operations while preserving cryptographic validation and claim checks.

## 5. Target Runtime Architecture

### 5.1 Authentication Modes

Introduce explicit mode switch:

1. `MEMORIA_AUTH_MODE=oidc`
2. `MEMORIA_AUTH_MODE=legacy_header` (temporary migration fallback)

Behavior:

1. In `oidc`, identity comes only from validated bearer token claims.
2. In `legacy_header`, existing `x-user-id` behavior is preserved.

### 5.2 OIDC Middleware Pipeline

For each MCP tool request in `oidc` mode:

1. Read `Authorization` header.
2. Require `Bearer <token>` format.
3. Validate JWT signature using Keycloak JWKS.
4. Validate claims:
   1. `iss` matches configured issuer.
   2. `aud` contains configured audience/client.
   3. `exp` (and `nbf` if present) are valid for current time.
5. Read identity claim (`sub` by default).
6. Store resolved `user_id` in request/session state.
7. Tool handlers continue using `_require_tool_user_id(...)`.

### 5.3 Identity Source Rules

1. `oidc` mode: `x-user-id` is ignored completely.
2. `legacy_header` mode: current behavior unchanged.

## 6. Configuration Model

Add the following settings:

1. `MEMORIA_AUTH_MODE` (`legacy_header` or `oidc`)
2. `MEMORIA_OIDC_ISSUER_URL` (example: `http://keycloak:8080/realms/memoria`)
3. `MEMORIA_OIDC_JWKS_URL` (optional override; default from issuer metadata)
4. `MEMORIA_OIDC_AUDIENCE` (example: `memoria-mcp`)
5. `MEMORIA_OIDC_SUBJECT_CLAIM` (default: `sub`)
6. `MEMORIA_OIDC_REQUIRED_SCOPES` (optional, reserved for later authorization work)

## 7. Docker Compose And Keycloak Bootstrap

### 7.1 Compose Changes

Add `keycloak` service:

1. Image: `quay.io/keycloak/keycloak:<stable>`
2. Command: `start-dev --import-realm`
3. Host port mapping (example): `8081:8080` (to avoid collision with Memoria `8080`)
4. Realm import volume:
   `./deploy/keycloak/realm.json:/opt/keycloak/data/import/realm.json:ro`
5. Memoria service gets OIDC env vars pointing to this Keycloak realm.

### 7.2 Realm Bootstrap File

Create `deploy/keycloak/realm.json` with:

1. Realm name: `memoria`
2. Public OIDC client: `memoria-mcp`
   1. `standardFlowEnabled=true`
   2. `publicClient=true`
   3. PKCE enabled
3. Test users (for local validation and e2e), e.g. `alice`, `bob`
4. Audience mapping so access tokens include `aud=memoria-mcp`

## 8. Error Contract

In `oidc` mode:

1. Missing `Authorization` -> unauthorized error (`missing bearer token`)
2. Invalid signature/issuer/audience/time claims -> unauthorized error (`invalid token`)
3. Missing subject claim -> unauthorized error (`invalid token claims`)
4. Unexpected state mismatch during tool call -> internal auth error

The exact transport shape can follow current FastMCP error wrapping, but messages should stay stable for tests and troubleshooting.

## 9. JWKS Caching Policy

1. Cache signing keys with TTL (target: 5 minutes).
2. If token `kid` not found in cache, trigger refresh and retry validation once.
3. Fail closed:
   1. If key remains unavailable after refresh, reject token.
   2. Do not allow unsigned/unchecked fallback.

## 10. Test Strategy

### 10.1 Unit Tests

Update/add tests for:

1. Valid bearer token accepted, `sub` extracted.
2. Missing/invalid bearer header rejected.
3. Invalid signature rejected.
4. Wrong issuer rejected.
5. Wrong audience rejected.
6. Expired token rejected.
7. Missing subject claim rejected.
8. JWKS cache hit/miss and unknown `kid` refresh path.

### 10.2 E2E Tests

Replace header-based user identity tests:

1. Obtain access tokens for two users (`alice`, `bob`) from Keycloak test realm.
2. Verify memory isolation exactly as current U1/U2 tests do.
3. Verify missing bearer token path.

## 11. Migration Plan

1. Phase A: Add `AUTH_MODE` and OIDC path while keeping legacy header mode.
2. Phase B: Update docs and Docker quickstart to include Keycloak by default.
3. Phase C: Switch default mode to `oidc`.
4. Phase D: Remove `legacy_header` in a future major release.

## 12. Documentation Updates

Update:

1. `README.md`:
   1. remove `x-user-id` first-class usage from main connection example
   2. add bearer-token based MCP client example
   3. add local Keycloak quickstart notes
2. `.env.example`:
   1. include `MEMORIA_AUTH_MODE` and `MEMORIA_OIDC_*` vars
   2. keep legacy vars only if still needed during migration

## 13. Acceptance Criteria (Definition Of Done)

1. In `oidc`, all MCP tools require valid bearer token.
2. In `oidc`, `x-user-id` does not affect resolved identity.
3. Compose starts Keycloak and imports realm with test users/client.
4. Unit tests and e2e tests pass for OIDC flow.
5. README has working bearer-auth connection guidance.
6. Legacy mode still works during transition.

## 14. Risks And Mitigations

1. Risk: token audience mismatches due to Keycloak client mapper setup.
   Mitigation: explicit audience mapper in `realm.json` and unit tests for audience failure.
2. Risk: stale JWKS cache after key rotation.
   Mitigation: unknown-`kid` forced refresh path.
3. Risk: migration confusion for existing users.
   Mitigation: explicit `AUTH_MODE` and documented phased rollout.
