# Phase 5 security model

## Implemented now

### Authentication and JWT security

Public registration creates `HOSPITAL_STAFF` accounts only. Administrators provision other roles and manage organization memberships. Passwords are bcrypt hashes. Access tokens are signed using HS256 with an environment-provided, non-placeholder key of at least 32 characters; tokens expire after 24 hours. Identity and role are loaded from the database after token verification, so changing JWT role claims cannot grant privileges. Missing, malformed, expired, and incorrectly signed tokens are rejected with 401 responses.

### Roles and organization membership

The roles are `USER`, `HOSPITAL_STAFF`, `BLOOD_BANK_STAFF`, and `ADMIN`. A role does not establish organization membership. `hospital_memberships` and `blood_bank_memberships` each link a user to an organization with a membership type and active flag; unique constraints prevent duplicate memberships. Only administrators can grant or revoke memberships through `/api/v1/auth/users/{user_id}/hospital-memberships`, `/api/v1/auth/users/{user_id}/blood-bank-memberships`, and the corresponding membership DELETE routes. Grants are audited.

Hospital request routes require `HOSPITAL_STAFF` or `ADMIN`. A non-admin hospital staff user must have an active membership in the request's hospital to create, list, view, update, match, coordinate, orchestrate, complete, or reject. Known resources outside the caller's membership scope return 403; unknown request IDs return 404. Admins can access any hospital request. `USER` and `BLOOD_BANK_STAFF` do not inherit hospital staff rights. Legacy requests remain unassigned and are available to admins or staff with explicit active membership in the request's hospital; no records are assigned to arbitrary users.

Blood-bank membership records are modeled and admin-managed. This API currently has no public inventory/source mutation routes; future bank-side routes must require an active membership for the specific bank. Matching and inventory tools remain internal behind the MCP service boundary.

### Resource authorization and IDOR

Request and match actions first resolve the parent request, then check hospital membership before accessing or mutating a match. The fulfillment service also verifies that a match belongs to the supplied request. The request creator ID is retained for provenance, while authorization is based on current active organization membership. Membership revocation takes effect on the next request.

### A2A and MCP service authentication

The official A2A SDK and JSON-RPC handlers remain in use. Agent Cards are discoverable; `/a2a` operations require `Authorization: Bearer <SERVICE_TO_SERVICE_TOKEN>` whenever a token is configured. The official MCP Python SDK/FastMCP Streamable HTTP endpoint uses the same credential. Configured service tokens must be at least 32 characters and are compared in constant time. Production-mode services fail closed if the credential is missing or too short; local development without a configured credential remains usable. Client helpers attach the credential when present. The service token protects the private service network, not public user authorization; keep service ports private.

MCP tools are a fixed set of typed functions. Tools are discovered and invoked through the official MCP SDK; unknown tools and malformed/missing arguments are rejected. A2A routes dispatch to a fixed operation per agent and reject an explicitly supplied unsupported operation. There is no arbitrary Python function or URL execution path. Legacy compatibility REST tool routes require `ADMIN` and are not the production agent-tool path.

### Observability, input, errors, and audit logs

The public gateway does not expose `/metrics` or LLM-usage routes. OTel attributes omit request bodies, credentials, tool arguments, prompts, completions, and sensitive personal data. Operations UIs are local-development tools; shared deployments need an authenticated operations boundary.

FastAPI/Pydantic validates request shapes and enums; blood units must be positive, audit pagination is limited to 1–200 rows, notification reasons are bounded, and the distance tool validates coordinates. Unhandled public API errors return a generic response; security-sensitive coordination errors do not expose internal service details. Audit records do not include passwords, JWTs, or API keys. Audit logs are admin-only, membership grants/revocations are recorded, and request creation/status/match actions use the existing audit service.

### Secrets and CORS/HTTP policy

`.env` is ignored by Git. `.env.example` contains empty placeholders only. Production JWT and service credentials must come from a secret manager or injected environment. CORS uses explicit origins, rejects `*`, and disables credentialed cross-origin requests. No extra HTTP security-header middleware is currently implemented.

### Rate Limiting Strategy

No application rate limiter is implemented. A per-process counter would reset across workers and would not protect independent services consistently. Tests do not apply artificial limits.

| Endpoint | Threat | Recommended limit | Enforcement location |
|---|---|---|---|
| `POST /api/v1/auth/login` | Password guessing and credential stuffing | Per IP and normalized account, e.g. 5 failures per minute with progressive delay | Production API gateway/ingress; account lockout policy belongs in auth service if product requirements define it |
| `POST /api/v1/auth/register` | Account spam and resource exhaustion | Per IP, e.g. 10 registrations per hour | Production API gateway/ingress, with email verification if adopted |
| `POST /api/v1/blood-requests/{id}/coordinate` | Expensive multi-agent calls | Per user and hospital, e.g. 10/minute with a small concurrency cap | Shared production gateway, preserving retries and emergency priority policy |
| `POST /api/v1/blood-requests/{id}/orchestrate` | Expensive allocation and mutation | Per user/hospital, e.g. 5/minute and one in-flight orchestration per request | Shared gateway plus application idempotency/concurrency control |
| `POST /api/v1/nl-request` | Repeated LLM and orchestration work | Per user/IP, e.g. 10/minute and bounded text length | Shared gateway; additionally enforce provider spend limits |
| A2A and MCP private endpoints | Internal service abuse | Per-service request/concurrency budgets | Private network policy and service mesh/gateway, not public user rate limits |

The values above are deployment starting points, not active settings. Distributed limits are deferred until the production ingress/store is selected; no Redis dependency or fake distributed limiter has been added.

## Deferred deployment hardening

Use TLS/mTLS or an authenticated private service mesh; replace the shared service token with independently scoped credentials and rotation; add the production ingress and shared rate limits; protect Prometheus/Jaeger/Grafana behind authenticated operations access; and establish the production database migration, backup, and recovery procedure. Docker deployment, cloud infrastructure, frontend, and Phase 6 are out of scope.

## Test coverage

Membership tests cover granting, active/inactive status, revocation, cross-hospital access, admin override, normal-user denial, unknown organizations, and bank membership isolation. Protocol network tests cover missing/invalid/valid service credentials, A2A malformed/unsupported messages, MCP discovery, invalid tools/arguments, and valid tool calls over independent local HTTP services. Test outcomes are reported from the latest executed run; this document does not mark unrun checks as PASS.
